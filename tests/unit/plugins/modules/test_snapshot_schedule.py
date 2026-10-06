# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import re

from ansible_collections.croit.ceph.plugins.modules import snapshot_schedule
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module


class ScheduleCluster(FakeCroit):
    """Fake croit holding CephFS and RBD snapshot schedules."""

    def __init__(self, cephfs=None, rbd=None):
        super(ScheduleCluster, self).__init__()
        self.schedules = dict(cephfs=list(cephfs or []), rbd=list(rbd or []))
        self.next_id = 100
        for kind in ("cephfs", "rbd"):
            self.route("GET", "/snapshot-schedule/%s" % kind, self.lister(kind))
            self.route("POST", "/snapshot-schedule/%s" % kind, self.creator(kind))
            self.route("PATCH", r"/snapshot-schedule/%s/(?P<sid>\d+)" % kind, self.patcher(kind))
            self.route("DELETE", r"/snapshot-schedule/%s/(?P<sid>\d+)" % kind, self.deleter(kind))

    def lister(self, kind):
        return lambda call: (200, copy.deepcopy(self.schedules[kind]))

    def creator(self, kind):
        def create(call):
            body = call.body
            self.next_id += 1
            schedule = dict(
                id=self.next_id,
                cron=body["cron"],
                enabled=True,
                snapshotPrefix=body["snapshotPrefix"],
                maxSnapshots=body["maxSnapshots"],
                paths=body["paths"],
                failedSnapshots=[],
            )
            if kind == "cephfs":
                schedule["volume"] = body.get("volume") or "cephfs"
            self.schedules[kind].append(schedule)
            return 204, None

        return create

    def find(self, kind, sid):
        return [s for s in self.schedules[kind] if s["id"] == int(sid)][0]

    def patcher(self, kind):
        def patch(call, sid):
            self.find(kind, sid).update(call.body)
            return 204, None

        return patch

    def deleter(self, kind):
        def delete(call, sid):
            self.schedules[kind] = [s for s in self.schedules[kind] if s["id"] != int(sid)]
            return 200, True

        return delete


def merged(base, **changes):
    result = dict(base)
    result.update(changes)
    return result


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, snapshot_schedule.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def cephfs_schedule(**overrides):
    s = dict(
        id=1,
        cron="0 * * * *",
        enabled=True,
        snapshotPrefix="hourly",
        maxSnapshots=24,
        paths=["/projects"],
        pathsFormatted="/projects",
        failedSnapshots=[],
        volume="cephfs",
    )
    s.update(overrides)
    return s


def test_full_idempotency_sequence_cephfs(monkeypatch):
    fake = ScheduleCluster()
    spec = dict(type="cephfs", snapshot_prefix="hourly", volume="cephfs", cron="0 * * * *", max_snapshots=24, paths=["/projects", "/home/"])

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["after"]["paths"] == ["/home", "/projects"]
    assert_only_gets(fake)
    assert fake.schedules["cephfs"] == []

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(
        cron="0 * * * *", snapshotPrefix="hourly", maxSnapshots=24, paths=["/home", "/projects"], volume="cephfs"
    )
    assert r["schedule"]["id"] == 101

    # 3. re-run (paths in another order / trailing slash)
    r = run(monkeypatch, fake, **merged(spec, paths=["/home", "/projects/"]))
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode
    update = dict(spec)
    update.update(max_snapshots=48, enabled=False)
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["max_snapshots"] == 24
    assert r["diff"]["after"]["max_snapshots"] == 48
    assert r["diff"]["after"]["enabled"] is False
    assert_only_gets(fake)

    # 6. update: only the changed fields, addressed by id
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    patch = fake.writes()[0]
    assert patch.path == "/snapshot-schedule/cephfs/101"
    assert patch.body == dict(maxSnapshots=48, enabled=False)

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    absent = dict(type="cephfs", snapshot_prefix="hourly", state="absent")
    r = run(monkeypatch, fake, check_mode=True, **absent)
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert len(fake.schedules["cephfs"]) == 1

    # 9. delete
    r = run(monkeypatch, fake, **absent)
    assert r["changed"]
    assert fake.writes()[0].path == "/snapshot-schedule/cephfs/101"
    assert fake.schedules["cephfs"] == []

    # 10. delete again
    r = run(monkeypatch, fake, **absent)
    assert not r["changed"]
    assert_only_gets(fake)


def test_full_idempotency_sequence_rbd(monkeypatch):
    fake = ScheduleCluster()
    spec = dict(
        type="rbd",
        snapshot_prefix="nightly",
        cron="30 2 * * *",
        max_snapshots=7,
        rbd_paths=[dict(pool="vms"), dict(pool="db", image="pg")],
    )

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body["paths"] == [dict(pool="db", rbd="pg"), dict(pool="vms")]

    r = run(monkeypatch, fake, **merged(spec, rbd_paths=[dict(pool="db", image="pg"), dict(pool="vms")]))
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    update = merged(spec, rbd_paths=[dict(pool="vms", namespace="tenant1")])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["after"]["rbd_paths"] == [dict(pool="vms", namespace="tenant1", image=None)]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.writes()[0].body == dict(paths=[dict(pool="vms", namespace="tenant1")])

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    absent = dict(type="rbd", snapshot_prefix="nightly", state="absent")
    r = run(monkeypatch, fake, check_mode=True, **absent)
    assert r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **absent)
    assert r["changed"]
    assert fake.schedules["rbd"] == []

    r = run(monkeypatch, fake, **absent)
    assert not r["changed"]
    assert_only_gets(fake)


def test_create_disabled_patches_after_create(monkeypatch):
    fake = ScheduleCluster()
    r = run(monkeypatch, fake, type="cephfs", snapshot_prefix="p", cron="0 0 * * *", max_snapshots=3, paths=["/a"], enabled=False)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST", "PATCH"]
    assert fake.writes()[1].body == dict(enabled=False)
    assert fake.schedules["cephfs"][0]["enabled"] is False


def test_create_needs_required_fields(monkeypatch):
    fake = ScheduleCluster()
    r = run(monkeypatch, fake, check_mode=True, type="rbd", snapshot_prefix="x", cron="0 0 * * *")
    assert r["failed"]
    assert "max_snapshots" in r["msg"] and "rbd_paths" in r["msg"]


def test_unset_options_left_alone(monkeypatch):
    fake = ScheduleCluster(cephfs=[cephfs_schedule()])
    r = run(monkeypatch, fake, type="cephfs", snapshot_prefix="hourly", cron="0 * * * *")
    assert not r["changed"]
    assert_only_gets(fake)


def test_ambiguous_prefix_fails(monkeypatch):
    fake = ScheduleCluster(cephfs=[cephfs_schedule(), cephfs_schedule(id=2, volume="other")])
    r = run(monkeypatch, fake, type="cephfs", snapshot_prefix="hourly", max_snapshots=5)
    assert r["failed"]
    assert "set volume" in r["msg"]
    r = run(monkeypatch, fake, type="cephfs", snapshot_prefix="hourly", volume="other", max_snapshots=5)
    assert r["changed"]
    assert fake.writes()[0].path == "/snapshot-schedule/cephfs/2"


def test_volume_scopes_identity(monkeypatch):
    fake = ScheduleCluster(cephfs=[cephfs_schedule()])
    r = run(monkeypatch, fake, check_mode=True, type="cephfs", snapshot_prefix="hourly", volume="other", cron="0 * * * *", max_snapshots=1, paths=["/"])
    assert r["changed"]
    assert r["diff"]["before"] == {}


def test_type_specific_options(monkeypatch):
    fake = ScheduleCluster()
    r = run(monkeypatch, fake, type="rbd", snapshot_prefix="x", paths=["/a"])
    assert r["failed"]
    r = run(monkeypatch, fake, type="cephfs", snapshot_prefix="x", rbd_paths=[dict(pool="p")])
    assert r["failed"]
    assert fake.calls == []


def test_max_snapshots_range(monkeypatch):
    fake = ScheduleCluster()
    r = run(monkeypatch, fake, type="cephfs", snapshot_prefix="x", max_snapshots=101)
    assert r["failed"]


def test_missing_rbd_target_warning(monkeypatch):
    fake = ScheduleCluster()
    original = [h for m, p, h in fake.routes if m == "POST" and p.pattern == "^/snapshot-schedule/rbd$"][0]
    fake.routes.insert(
        0,
        (
            "POST",
            re.compile("^/snapshot-schedule/rbd$"),
            lambda call: (400, dict(code=400, message="w", ignorableWarning=dict(token="t", warningText="does not exist yet")))
            if call.query.get("ignoreWarning") != "t"
            else original(call),
        ),
    )
    spec = dict(type="rbd", snapshot_prefix="n", cron="0 0 * * *", max_snapshots=1, rbd_paths=[dict(pool="future")])
    r = run(monkeypatch, fake, **spec)
    assert r["failed"]
    assert r["warning"] == "does not exist yet"
    r = run(monkeypatch, fake, ignore_warnings=True, **spec)
    assert r["changed"]
    assert len(fake.schedules["rbd"]) == 1
