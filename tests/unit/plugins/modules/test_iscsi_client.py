# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import iscsi_client
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_iscsi import MIB, IscsiCluster

INIT = "iqn.1998-01.com.vmware:esx01"
SECRET = "chap-secret-12"
NEW_SECRET = "chap-secret-34"


def merged(base, **changes):
    result = dict(base)
    result.update(changes)
    return result


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, iscsi_client.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def assert_no_secret(r):
    assert SECRET not in repr(r) and NEW_SECRET not in repr(r)


def test_full_idempotency_sequence(monkeypatch):
    fake = IscsiCluster(gateway=True)
    spec = dict(iqn=INIT, chap_username="esx01-user", chap_password=SECRET, disks=[dict(pool="iscsi", image="ds1", size="1G")])

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["after"]["disks"] == ["iscsi/ds1"]
    assert_only_gets(fake)
    assert_no_secret(r)
    assert INIT not in fake.clients

    # 2. create: initiator, then its disk (image created with 1024 MB)
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["PUT", "PUT"]
    assert fake.writes()[1].body == [dict(pool="iscsi", name="ds1", size=1024)]
    assert fake.images["iscsi/ds1"] == 1024 * MIB
    assert r["client"]["password"] == "********"
    assert_no_secret(r)

    # 3. / 4. re-run
    for check in (False, True):
        r = run(monkeypatch, fake, check_mode=check, **spec)
        assert not r["changed"]
        assert_only_gets(fake)

    # 5. update in check mode: new password, second disk, exclusive drops ds1
    update = merged(spec, chap_password=NEW_SECRET, disks=[dict(pool="iscsi", image="ds2", size="2G")], exclusive=True)
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["after"]["chap_password"] == "******** (changed)"
    assert r["diff"]["after"]["disks"] == ["iscsi/ds2"]
    assert_only_gets(fake)
    assert_no_secret(r)

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["PATCH", "DELETE", "PUT"]
    assert fake.writes()[0].body == dict(password=NEW_SECRET)
    assert fake.clients[INIT]["own"] == ["iscsi/ds2"]
    assert "iscsi/ds1" in fake.images, "unmapping must never delete the image"

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, iqn=INIT, state="absent")
    assert r["changed"] and r["diff"]["after"] == {}
    assert_only_gets(fake)

    # 9. delete
    r = run(monkeypatch, fake, iqn=INIT, state="absent")
    assert r["changed"] and INIT not in fake.clients
    assert "iscsi/ds2" in fake.images

    # 10. delete again
    r = run(monkeypatch, fake, iqn=INIT, state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_create_requires_chap(monkeypatch):
    fake = IscsiCluster(gateway=True)
    r = run(monkeypatch, fake, iqn=INIT)
    assert r["failed"] and "chap_username and chap_password" in r["msg"]


def test_chap_length_validated_before_writes(monkeypatch):
    fake = IscsiCluster(gateway=True)
    r = run(monkeypatch, fake, iqn=INIT, chap_username="short", chap_password=SECRET)
    assert r["failed"] and "8 to 64" in r["msg"]
    r = run(monkeypatch, fake, iqn=INIT, chap_username="long-enough", chap_password="tooshort")
    assert r["failed"] and "12 to 16" in r["msg"]
    assert_only_gets(fake)


def test_masked_password_uses_update_password(monkeypatch):
    fake = IscsiCluster(gateway=True, masked_passwords=True)
    fake.clients[INIT] = dict(username="esx01-user", password=SECRET, group=None, own=[])
    r = run(monkeypatch, fake, iqn=INIT, chap_password=NEW_SECRET)
    assert not r["changed"]
    r = run(monkeypatch, fake, iqn=INIT, chap_password=NEW_SECRET, update_password="always")
    assert r["changed"] and fake.clients[INIT]["password"] == NEW_SECRET
    assert_no_secret(r)


def test_group_membership(monkeypatch):
    fake = IscsiCluster(gateway=True)
    fake.groups["esx"] = dict(members=[], luns=["iscsi/shared"])
    fake.images["iscsi/shared"] = MIB
    fake.disks["iscsi/shared"] = "wwn-shared"
    fake.clients[INIT] = dict(username="esx01-user", password=SECRET, group=None, own=[])

    r = run(monkeypatch, fake, iqn=INIT, group="esx")
    assert r["changed"] and fake.clients[INIT]["group"] == "esx"
    # group luns are not counted as the initiator's own, so exclusive leaves them alone
    r = run(monkeypatch, fake, iqn=INIT, group="esx", disks=[], exclusive=True)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, iqn=INIT, group="")
    assert r["failed"] and "ignore_warnings" in r["msg"]
    r = run(monkeypatch, fake, iqn=INIT, group="", ignore_warnings=True)
    assert r["changed"] and fake.clients[INIT]["group"] is None


def test_unknown_group_fails(monkeypatch):
    fake = IscsiCluster(gateway=True)
    r = run(monkeypatch, fake, check_mode=True, iqn=INIT, chap_username="esx01-user", chap_password=SECRET, group="nope")
    assert r["failed"] and "does not exist" in r["msg"]


def test_no_gateway_fails(monkeypatch):
    fake = IscsiCluster()
    r = run(monkeypatch, fake, iqn=INIT)
    assert r["failed"] and "croit.ceph.iscsi_gateway" in r["msg"]
