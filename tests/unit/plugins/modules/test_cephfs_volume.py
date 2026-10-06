# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import re

from ansible_collections.croit.ceph.plugins.modules import cephfs_volume
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

WARN_DELETE = dict(code=400, message="w", ignorableWarning=dict(token="del", warningText="Irreversible deletion"))
WARN_MDS = dict(code=400, message="w", ignorableWarning=dict(token="mds", warningText="MDS count"))


class VolumeCluster(FakeCroit):
    """Fake croit with CephFS volumes; deletes and max_mds changes answer croit's warnings."""

    def __init__(self, volumes=None):
        super(VolumeCluster, self).__init__()
        self.volumes = dict((v["name"], v) for v in (volumes or []))
        self.serve_tasks()
        self.route("GET", "/cephfs/volumes", lambda call: (200, [copy.deepcopy(v) for v in self.volumes.values()]))
        self.route("POST", "/cephfs/volumes/(?P<name>[^/]+)", self.create)
        self.route("PATCH", "/cephfs/volumes/(?P<name>[^/]+)", self.patch)
        self.route("DELETE", "/cephfs/volumes/(?P<name>[^/]+)", self.delete)

    def create(self, call, name):
        assert call.body is None
        self.volumes[name] = dict(
            name=name,
            id=len(self.volumes) + 1,
            maxMds=1,
            allowStandbyReplay=True,
            metadataPool="cephfs.%s.meta" % name,
            dataPools=["cephfs.%s.data" % name],
            isDefault=False,
        )
        return 200, self.new_task("Create CephFS", name)

    def patch(self, call, name):
        if "maxMds" in call.body and call.query.get("ignoreWarning") != "mds":
            return 400, WARN_MDS
        self.volumes[name].update(call.body)
        return 200, self.new_task("Update CephFS", name)

    def delete(self, call, name):
        if call.query.get("ignoreWarning") != "del":
            return 400, WARN_DELETE
        del self.volumes[name]
        return 200, self.new_task("Delete CephFS", name)


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, cephfs_volume.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = VolumeCluster()
    spec = dict(name="fs1", allow_standby_replay=False)

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"] == dict(before={}, after=dict(max_mds=None, allow_standby_replay=False))
    assert_only_gets(fake)
    assert "fs1" not in fake.volumes

    # 2. create: croit's defaults are corrected with a follow-up PATCH
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST", "PATCH"]
    assert fake.writes()[1].body == dict(allowStandbyReplay=False)
    assert r["volume"]["allowStandbyReplay"] is False
    assert r["task"]["state"] == "FINISHED"

    # 3. re-run
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode
    update = dict(spec, max_mds=2, ignore_warnings=True)
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["max_mds"] == 1
    assert r["diff"]["after"]["max_mds"] == 2
    assert_only_gets(fake)
    assert fake.volumes["fs1"]["maxMds"] == 1

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert [c.body for c in fake.writes()] == [dict(maxMds=2), dict(maxMds=2)]  # warning, then confirmed
    assert r["volume"]["maxMds"] == 2

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, name="fs1", state="absent", confirm_delete=True)
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert "fs1" in fake.volumes

    # 9. delete: confirm_delete confirms croit's irreversible-deletion warning
    r = run(monkeypatch, fake, name="fs1", state="absent", confirm_delete=True)
    assert r["changed"]
    assert [c.query.get("ignoreWarning") for c in fake.writes()] == [None, "del"]
    assert "fs1" not in fake.volumes

    # 10. delete again
    r = run(monkeypatch, fake, name="fs1", state="absent", confirm_delete=True)
    assert not r["changed"]
    assert_only_gets(fake)


def existing(**overrides):
    volume = dict(
        name="fs1",
        id=1,
        maxMds=1,
        allowStandbyReplay=True,
        metadataPool="m",
        dataPools=["d"],
        isDefault=False,
    )
    volume.update(overrides)
    return volume


def test_create_with_croit_defaults_needs_no_patch(monkeypatch):
    fake = VolumeCluster()
    r = run(monkeypatch, fake, name="fs1")
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST"]


def test_unset_options_are_left_alone(monkeypatch):
    fake = VolumeCluster([existing(maxMds=3)])
    r = run(monkeypatch, fake, name="fs1")
    assert not r["changed"]
    assert_only_gets(fake)


def test_max_mds_warning_fails_without_ignore_warnings(monkeypatch):
    fake = VolumeCluster([existing()])
    r = run(monkeypatch, fake, name="fs1", max_mds=2)
    assert r["failed"]
    assert r["warning"] == "MDS count"
    assert fake.volumes["fs1"]["maxMds"] == 1


def test_delete_requires_confirmation(monkeypatch):
    fake = VolumeCluster([existing()])
    r = run(monkeypatch, fake, name="fs1", state="absent")
    assert r["failed"]
    assert "confirm_delete" in r["msg"]
    assert_only_gets(fake)


def test_delete_refused_by_croit_fails(monkeypatch):
    fake = VolumeCluster([existing(isDefault=True)])
    fake.routes.insert(
        0, ("DELETE", re.compile("^/cephfs/volumes/fs1$"), lambda call: (409, dict(code=409, message="default filesystem")))
    )
    r = run(monkeypatch, fake, name="fs1", state="absent", confirm_delete=True)
    assert r["failed"]
    assert "default filesystem" in r["msg"]
    assert "fs1" in fake.volumes


def test_invalid_max_mds(monkeypatch):
    fake = VolumeCluster([existing()])
    r = run(monkeypatch, fake, name="fs1", max_mds=0)
    assert r["failed"]
    assert fake.calls == []


def test_no_wait_skips_follow_up_patch(monkeypatch):
    fake = VolumeCluster()
    r = run(monkeypatch, fake, name="fs1", allow_standby_replay=False, wait=False)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST"]
    assert r["task"]["id"]
