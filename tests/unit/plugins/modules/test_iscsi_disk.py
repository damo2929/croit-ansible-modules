# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import iscsi_disk, iscsi_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_iscsi import MIB, IscsiCluster

GIB = 1024 * MIB


def cluster():
    fake = IscsiCluster(gateway=True)
    fake.images["iscsi/ds1"] = GIB
    fake.disks["iscsi/ds1"] = "wwn-ds1"
    fake.clients["iqn.esx01"] = dict(username="esx01-user", password="secret-123456", group=None, own=["iscsi/ds1"])
    return fake


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, iscsi_disk.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    # Disks are exported by mapping (iscsi_client/iscsi_group), so steps 1-4 check an exported disk.
    fake = cluster()
    spec = dict(pool="iscsi", image="ds1", size="1G")

    # 1. / 2. / 3. / 4. present at its size: nothing to do
    for check in (True, False, False, True):
        r = run(monkeypatch, fake, check_mode=check, **spec)
        assert not r["changed"] and r["disk"]["size"] == GIB
        assert_only_gets(fake)

    # 5. grow in check mode
    r = run(monkeypatch, fake, check_mode=True, pool="iscsi", image="ds1", size="2G")
    assert r["changed"] and r["diff"]["before"]["size"] == GIB and r["diff"]["after"]["size"] == 2 * GIB
    assert_only_gets(fake)
    assert fake.images["iscsi/ds1"] == GIB

    # 6. grow (size sent in MB)
    r = run(monkeypatch, fake, pool="iscsi", image="ds1", size="2G")
    assert r["changed"] and fake.writes()[0].body == dict(size=2048)
    assert r["disk"]["size"] == 2 * GIB

    # 7. grow again
    r = run(monkeypatch, fake, pool="iscsi", image="ds1", size="2G")
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. unexport in check mode
    r = run(monkeypatch, fake, check_mode=True, wwn="WWN-DS1", state="absent")
    assert r["changed"] and r["diff"]["after"] == {}
    assert_only_gets(fake)

    # 9. unexport keeps the image
    r = run(monkeypatch, fake, wwn="wwn-ds1", state="absent")
    assert r["changed"] and r["task"]["state"] == "FINISHED"
    assert fake.writes()[0].body == dict(pool="iscsi", image="ds1", deleteData=False)
    assert "iscsi/ds1" not in fake.disks and "iscsi/ds1" in fake.images

    # 10. unexport again
    r = run(monkeypatch, fake, wwn="wwn-ds1", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_shrink_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, check_mode=True, pool="iscsi", image="ds1", size="512M")
    assert r["failed"] and "cannot shrink" in r["msg"]


def test_size_rounded_up_to_mib(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, check_mode=True, pool="iscsi", image="ds1", size=str(GIB + 1))
    assert r["diff"]["after"]["size"] == GIB + MIB


def test_not_exported_fails_with_hint(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, pool="iscsi", image="other")
    assert r["failed"] and "croit.ceph.iscsi_client" in r["msg"]


def test_delete_image_requires_confirmation(monkeypatch):
    fake = cluster()
    for check in (True, False):
        r = run(monkeypatch, fake, check_mode=check, pool="iscsi", image="ds1", state="absent", delete_image=True)
        assert r["failed"] and "confirm_delete" in r["msg"]
        assert_only_gets(fake)
    r = run(monkeypatch, fake, pool="iscsi", image="ds1", state="absent", delete_image=True, confirm_delete=True)
    assert r["changed"] and fake.writes()[0].body["deleteData"] is True
    assert "iscsi/ds1" not in fake.images


def test_delete_image_with_present_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, pool="iscsi", image="ds1", delete_image=True)
    assert r["failed"]


def test_info_masks_passwords(monkeypatch):
    fake = cluster()
    r = run_module(monkeypatch, fake, iscsi_info.main, check_mode=True, gather=["gateways", "servers", "disks", "groups", "hosts", "config"])
    assert not r["changed"] and fake.writes() == []
    assert r["gateways"][0]["serviceId"] == 7
    assert r["disks"][0]["hosts"] == ["iqn.esx01"]
    assert "secret-123456" not in repr(r)
    assert r["hosts"][0]["password"] == "********"
    assert r["config"]["7"]["clients"][0]["password"] == "********"
    r = run_module(monkeypatch, fake, iscsi_info.main, gather=["hosts"], show_secrets=True)
    assert r["hosts"][0]["password"] == "secret-123456"
    assert set(r) >= set(["hosts"]) and "gateways" not in r
