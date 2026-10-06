# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import iscsi_group
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_iscsi import MIB, IscsiCluster

ESX1 = "iqn.1998-01.com.vmware:esx01"
ESX2 = "iqn.1998-01.com.vmware:esx02"


def cluster():
    fake = IscsiCluster(gateway=True)
    for iqn in (ESX1, ESX2):
        fake.clients[iqn] = dict(username="user-" + iqn[-5:], password="secret-123456", group=None, own=[])
    fake.images["iscsi/ds1"] = MIB
    return fake


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, iscsi_group.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()
    spec = dict(name="esx", members=[ESX1], disks=[dict(pool="iscsi", image="ds1")])

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["after"] == dict(members=[ESX1], disks=["iscsi/ds1"])
    assert_only_gets(fake)
    assert "esx" not in fake.groups

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert [(c.method, c.path.rsplit("/", 1)[-1]) for c in fake.writes()] == [("PUT", "esx"), ("PUT", "hosts"), ("PUT", "disks")]
    assert r["group"]["members"] == [ESX1]

    # 3. / 4. re-run
    for check in (False, True):
        r = run(monkeypatch, fake, check_mode=check, **spec)
        assert not r["changed"]
        assert_only_gets(fake)

    # 5. update in check mode: swap members (exclusive), new disk
    update = dict(name="esx", members=[ESX2], disks=[dict(pool="iscsi", image="ds1"), dict(pool="iscsi", image="ds2", size="1G")],
                  exclusive=True, ignore_warnings=True)
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"] and r["diff"]["after"] == dict(members=[ESX2], disks=["iscsi/ds1", "iscsi/ds2"])
    assert_only_gets(fake)

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.groups["esx"]["members"] == [ESX2]
    assert sorted(fake.groups["esx"]["luns"]) == ["iscsi/ds1", "iscsi/ds2"]

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, name="esx", state="absent")
    assert r["changed"] and r["diff"]["after"] == {}
    assert_only_gets(fake)

    # 9. delete (croit warns first)
    r = run(monkeypatch, fake, name="esx", state="absent")
    assert r["failed"] and "ignore_warnings" in r["msg"]
    r = run(monkeypatch, fake, name="esx", state="absent", ignore_warnings=True)
    assert r["changed"] and "esx" not in fake.groups
    assert "iscsi/ds2" in fake.images

    # 10. delete again
    r = run(monkeypatch, fake, name="esx", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_non_exclusive_keeps_others(monkeypatch):
    fake = cluster()
    fake.groups["esx"] = dict(members=[ESX1], luns=[])
    fake.clients[ESX1]["group"] = "esx"
    r = run(monkeypatch, fake, name="esx", members=[ESX2])
    assert r["changed"] and sorted(fake.groups["esx"]["members"]) == [ESX1, ESX2]


def test_unknown_member_fails_before_writes(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, check_mode=True, name="esx", members=["iqn.nope"])
    assert r["failed"] and "croit.ceph.iscsi_client" in r["msg"]
    assert_only_gets(fake)


def test_member_with_own_mapping_is_refused(monkeypatch):
    fake = cluster()
    fake.clients[ESX1]["own"] = ["iscsi/ds1"]
    fake.disks["iscsi/ds1"] = "wwn-1"
    r = run(monkeypatch, fake, name="esx", members=[ESX1])
    assert r["failed"] and "mappings of its own" in r["msg"]
