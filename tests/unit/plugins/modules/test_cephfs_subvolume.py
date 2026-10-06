# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import cephfs_subvolume as subvolume_module
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

GIB = 1024 ** 3


class SubvolumeCluster(FakeCroit):
    """Fake croit with subvolumes keyed by (volume, group, name); None = default."""

    def __init__(self, subvolumes=None):
        super(SubvolumeCluster, self).__init__()
        self.subvolumes = dict(subvolumes or {})
        self.route("GET", "/cephfs/subvolumes", self.list_subvolumes)
        self.route("GET", "/cephfs/subvolumes/(?P<name>[^/]+)", self.info)
        self.route("POST", "/cephfs/subvolumes/(?P<name>[^/]+)", self.create)
        self.route("POST", "/cephfs/subvolumes/(?P<name>[^/]+)/resize", self.resize)
        self.route("DELETE", "/cephfs/subvolumes/(?P<name>[^/]+)", self.delete)

    @staticmethod
    def key(call, name):
        return (call.query.get("volume"), call.query.get("groupName"), name)

    def list_subvolumes(self, call):
        where = (call.query.get("volume"), call.query.get("groupName"))
        return 200, [dict(name=k[2]) for k in self.subvolumes if k[:2] == where]

    def info(self, call, name):
        key = self.key(call, name)
        if key not in self.subvolumes:
            return 404, dict(code=404, message="no such subvolume")
        return 200, copy.deepcopy(self.subvolumes[key])

    def create(self, call, name):
        body = call.body
        group = call.query.get("groupName") or "_nogroup"
        self.subvolumes[self.key(call, name)] = dict(
            path="/volumes/%s/%s/uuid" % (group, name),
            uid=body.get("uid", 0),
            gid=body.get("gid", 0),
            mode=0o40000 | int(body.get("mode", "755"), 8),
            dataPool=body.get("poolLayout", "cephfs.data"),
            poolNamespace="fsvolumens_%s" % name if body.get("namespaceIsolated") else None,
            quotaMaxBytes=body.get("size"),
            bytesUsed=0,
            state="complete",
            type="subvolume",
        )
        return 204, None

    def resize(self, call, name):
        self.subvolumes[self.key(call, name)]["quotaMaxBytes"] = call.body.get("newSize")
        return 204, None

    def delete(self, call, name):
        key = self.key(call, name)
        if call.query.get("retainSnapshots") == "true":
            self.subvolumes[key] = dict(state="snapshot-retained")
        else:
            del self.subvolumes[key]
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, subvolume_module.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = SubvolumeCluster()
    ident = dict(volume="fs1", group="csi", name="pvc-1")
    spec = dict(ident, size="100G", namespace_isolated=True)
    key = ("fs1", "csi", "pvc-1")

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["after"]["size"] == 100 * GIB
    assert_only_gets(fake)
    assert key not in fake.subvolumes

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    write = fake.writes()[0]
    assert write.query == dict(volume="fs1", groupName="csi")
    assert write.body == dict(size=100 * GIB, namespaceIsolated=True)
    assert r["subvolume"]["poolNamespace"] == "fsvolumens_pvc-1"

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
    update["size"] = "200G"
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert (r["diff"]["before"]["size"], r["diff"]["after"]["size"]) == (100 * GIB, 200 * GIB)
    assert_only_gets(fake)
    assert fake.subvolumes[key]["quotaMaxBytes"] == 100 * GIB

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.writes()[0].path == "/cephfs/subvolumes/pvc-1/resize"
    assert fake.writes()[0].body == dict(newSize=200 * GIB)

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, state="absent", confirm_delete=True, **ident)
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert key in fake.subvolumes

    # 9. delete
    r = run(monkeypatch, fake, state="absent", confirm_delete=True, **ident)
    assert r["changed"]
    assert fake.writes()[0].query == dict(volume="fs1", groupName="csi")
    assert key not in fake.subvolumes

    # 10. delete again
    r = run(monkeypatch, fake, state="absent", confirm_delete=True, **ident)
    assert not r["changed"]
    assert_only_gets(fake)


def existing(**overrides):
    info = dict(
        path="/volumes/_nogroup/sv/uuid",
        uid=0,
        gid=0,
        mode=0o40755,
        dataPool="cephfs.data",
        poolNamespace=None,
        quotaMaxBytes=None,
        bytesUsed=50 * GIB,
        state="complete",
        type="subvolume",
    )
    info.update(overrides)
    return {(None, None, "sv"): info}


def test_unset_options_are_left_alone(monkeypatch):
    fake = SubvolumeCluster(existing(quotaMaxBytes=80 * GIB))
    r = run(monkeypatch, fake, name="sv")
    assert not r["changed"]
    assert_only_gets(fake)


def test_refuses_to_shrink_below_used(monkeypatch):
    fake = SubvolumeCluster(existing(quotaMaxBytes=80 * GIB))
    r = run(monkeypatch, fake, name="sv", size="10G")
    assert r["failed"]
    assert "already uses" in r["msg"]
    assert_only_gets(fake)


def test_remove_quota(monkeypatch):
    fake = SubvolumeCluster(existing(quotaMaxBytes=80 * GIB))
    r = run(monkeypatch, fake, name="sv", size="unlimited")
    assert r["changed"]
    assert fake.writes()[0].body == {}


def test_namespace_isolation_is_create_only(monkeypatch):
    fake = SubvolumeCluster(existing())
    r = run(monkeypatch, fake, name="sv", namespace_isolated=True)
    assert r["failed"]
    assert "namespace_isolated" in r["msg"]
    r = run(monkeypatch, fake, name="sv", namespace_isolated=False, mode="755")
    assert not r["changed"]


def test_delete_requires_confirmation(monkeypatch):
    fake = SubvolumeCluster(existing())
    r = run(monkeypatch, fake, name="sv", state="absent")
    assert r["failed"]
    assert_only_gets(fake)


def test_retain_snapshots_counts_as_absent(monkeypatch):
    fake = SubvolumeCluster(existing())
    r = run(monkeypatch, fake, name="sv", state="absent", confirm_delete=True, retain_snapshots=True)
    assert r["changed"]
    assert fake.writes()[0].query == dict(retainSnapshots="true")
    assert fake.subvolumes[(None, None, "sv")]["state"] == "snapshot-retained"
    r = run(monkeypatch, fake, name="sv", state="absent", confirm_delete=True, retain_snapshots=True)
    assert not r["changed"]
