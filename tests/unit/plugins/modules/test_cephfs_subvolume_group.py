# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import re

import pytest

from ansible_collections.croit.ceph.plugins.modules import cephfs_subvolume_group as group_module
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

GIB = 1024 ** 3


class GroupCluster(FakeCroit):
    """Fake croit with subvolume groups per volume (None = croit's own volume)."""

    def __init__(self, groups=None):
        super(GroupCluster, self).__init__()
        self.groups = {}
        for (volume, name), info in (groups or {}).items():
            self.groups[(volume, name)] = info
        self.route("GET", "/cephfs/subvolume-groups", self.list_groups)
        self.route("GET", "/cephfs/subvolume-groups/(?P<name>[^/]+)", self.info)
        self.route("POST", "/cephfs/subvolume-groups/(?P<name>[^/]+)", self.create)
        self.route("POST", "/cephfs/subvolume-groups/(?P<name>[^/]+)/resize", self.resize)
        self.route("DELETE", "/cephfs/subvolume-groups/(?P<name>[^/]+)", self.delete)

    def list_groups(self, call):
        volume = call.query.get("volume")
        return 200, [dict(name=n) for (v, n) in self.groups if v == volume]

    def info(self, call, name):
        key = (call.query.get("volume"), name)
        if key not in self.groups:
            return 404, dict(code=404, message="no such group")
        return 200, copy.deepcopy(self.groups[key])

    def create(self, call, name):
        body = call.body
        self.groups[(call.query.get("volume"), name)] = dict(
            uid=body.get("uid", 0),
            gid=body.get("gid", 0),
            mode=0o40000 | int(body.get("mode", "755"), 8),
            dataPool=body.get("poolLayout", "cephfs.data"),
            quotaMaxBytes=body.get("size"),
            bytesUsed=0,
            monAddrs=[],
        )
        return 204, None

    def resize(self, call, name):
        self.groups[(call.query.get("volume"), name)]["quotaMaxBytes"] = call.body.get("newSize")
        return 204, None

    def delete(self, call, name):
        del self.groups[(call.query.get("volume"), name)]
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, group_module.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = GroupCluster()
    spec = dict(volume="fs1", name="csi", size="10G", mode="750", uid=1000)

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["after"]["size"] == 10 * GIB
    assert r["diff"]["after"]["mode"] == "0750"
    assert_only_gets(fake)
    assert not fake.groups

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    write = fake.writes()[0]
    assert write.query == dict(volume="fs1")
    assert write.body == dict(size=10 * GIB, mode="750", uid=1000)
    assert r["subvolume_group"]["quotaMaxBytes"] == 10 * GIB

    # 3. re-run
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode
    update = dict(spec)
    update["size"] = "20G"
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert (r["diff"]["before"]["size"], r["diff"]["after"]["size"]) == (10 * GIB, 20 * GIB)
    assert_only_gets(fake)
    assert fake.groups[("fs1", "csi")]["quotaMaxBytes"] == 10 * GIB

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.writes()[0].path == "/cephfs/subvolume-groups/csi/resize"
    assert fake.writes()[0].body == dict(newSize=20 * GIB)

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, volume="fs1", name="csi", state="absent", confirm_delete=True)
    assert r["changed"]
    assert_only_gets(fake)
    assert ("fs1", "csi") in fake.groups

    # 9. delete
    r = run(monkeypatch, fake, volume="fs1", name="csi", state="absent", confirm_delete=True)
    assert r["changed"]
    assert fake.writes()[0].method == "DELETE"
    assert not fake.groups

    # 10. delete again
    r = run(monkeypatch, fake, volume="fs1", name="csi", state="absent", confirm_delete=True)
    assert not r["changed"]
    assert_only_gets(fake)


def existing(**overrides):
    info = dict(uid=0, gid=0, mode=0o40755, dataPool="cephfs.data", quotaMaxBytes=None, bytesUsed=5 * GIB, monAddrs=[])
    info.update(overrides)
    return {(None, "csi"): info}


def test_default_volume_omits_query(monkeypatch):
    fake = GroupCluster(existing())
    r = run(monkeypatch, fake, name="csi")
    assert not r["changed"]
    assert all("volume" not in c.query for c in fake.calls)


def test_same_name_in_other_volume_is_not_found(monkeypatch):
    fake = GroupCluster(existing())
    r = run(monkeypatch, fake, check_mode=True, volume="other", name="csi")
    assert r["changed"]


@pytest.mark.parametrize("value", ["unlimited", "0", "inf"])
def test_remove_quota(monkeypatch, value):
    fake = GroupCluster(existing(quotaMaxBytes=10 * GIB))
    r = run(monkeypatch, fake, name="csi", size=value)
    assert r["changed"]
    assert fake.writes()[0].body == {}
    r = run(monkeypatch, fake, name="csi", size=value)
    assert not r["changed"]


def test_refuses_to_shrink_below_used(monkeypatch):
    fake = GroupCluster(existing(quotaMaxBytes=10 * GIB))
    r = run(monkeypatch, fake, check_mode=True, name="csi", size="1G")
    assert r["failed"]
    assert "already uses" in r["msg"]
    assert_only_gets(fake)


def test_create_only_field_mismatch_fails(monkeypatch):
    fake = GroupCluster(existing())
    r = run(monkeypatch, fake, name="csi", mode="700")
    assert r["failed"]
    assert "only be set when the group is created" in r["msg"]
    r = run(monkeypatch, fake, name="csi", mode="0755", uid=0, pool_layout="cephfs.data")
    assert not r["changed"]


def test_invalid_mode(monkeypatch):
    fake = GroupCluster(existing())
    r = run(monkeypatch, fake, name="csi", mode="rwx")
    assert r["failed"]
    assert fake.calls == []


def test_delete_requires_confirmation(monkeypatch):
    fake = GroupCluster(existing())
    r = run(monkeypatch, fake, name="csi", state="absent")
    assert r["failed"]
    assert_only_gets(fake)


def test_delete_of_non_empty_group_surfaces_error(monkeypatch):
    fake = GroupCluster(existing())
    fake.routes.insert(
        0,
        ("DELETE", re.compile("^/cephfs/subvolume-groups/csi$"), lambda call: (400, dict(code=400, message="group not empty"))),
    )
    r = run(monkeypatch, fake, name="csi", state="absent", confirm_delete=True)
    assert r["failed"]
    assert "group not empty" in r["msg"]
