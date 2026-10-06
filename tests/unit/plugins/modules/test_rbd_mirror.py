# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import rbd_mirror
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

PEER_ID = "0f8b8f2e-1111-4c4c-9d9d-123456789abc"


class MirrorCluster(FakeCroit):
    def __init__(self):
        super(MirrorCluster, self).__init__()
        self.mode = "disabled"
        self.site = None
        self.peers = []
        self.schedules = []
        self.images = dict(
            vm1=dict(name="vm1", features=["LAYERING"], mirrorInfo=dict(imageMirrorMode="disabled", mirrorState="disabled", primary=None)),
        )
        self.serve_tasks()
        self.route("GET", "/pools/rbd/rbd-mirror", self.get_info)
        self.route("GET", "/pools/ec/rbd-mirror", lambda call: (404, dict(code=404, message="erasure coded")))
        self.route("PATCH", "/pools/rbd/rbd-mirror", self.patch_mode)
        self.route("PATCH", "/pools/rbd/rbd-mirror/token", self.patch_site)
        self.route("GET", "/pools/rbd/rbd-mirror/token", lambda call: (200, "BOOTSTRAP-SECRET"))
        self.route("POST", "/pools/rbd/rbd-mirror/peers", self.add_peer)
        self.route("PATCH", "/pools/rbd/rbd-mirror/peers/(?P<pid>[^/]+)", self.patch_peer)
        self.route("DELETE", "/pools/rbd/rbd-mirror/peers/(?P<pid>[^/]+)", self.delete_peer)
        self.route("GET", "/pools/rbd-mirror/schedules", lambda call: (200, copy.deepcopy(self.schedules)))
        self.route("POST", "/pools/rbd-mirror/schedules", self.add_schedule)
        self.route("DELETE", "/pools/rbd-mirror/schedules", self.delete_schedule)
        self.route("GET", "/pools/rbd/rbds/(?P<rbd>[^/]+)", self.get_image)
        self.route("PATCH", "/pools/rbd/rbds/(?P<rbd>[^/]+)/rbd-mirror", self.patch_image)

    def get_info(self, call):
        return 200, dict(pool="rbd", namespace=None, poolMirrorMode=self.mode, siteName=self.site, peers=copy.deepcopy(self.peers))

    def patch_mode(self, call):
        if call.body["poolMirrorMode"] == "disabled" and call.query.get("ignoreWarning") != "t":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="t", warningText="peers go away"))
        self.mode = call.body["poolMirrorMode"]
        if self.mode == "disabled":
            self.peers = []
        return 200, self.new_task("Mirror mode")

    def patch_site(self, call):
        assert self.mode != "disabled"
        self.site = call.body["siteName"]
        return 204, None

    def add_peer(self, call):
        assert call.body["peerToken"] == "PEER-TOKEN"
        self.peers = [dict(id=PEER_ID, siteName=call.body["siteName"], clientName="client.rbd-mirror-peer", direction=call.body.get("direction", "rx-tx"))]
        return 200, self.new_task("Add peer")

    def patch_peer(self, call, pid):
        self.peers[0].update(call.body)
        return 200, self.new_task("Update peer")

    def delete_peer(self, call, pid):
        self.peers = [x for x in self.peers if x["id"] != pid]
        return 200, self.new_task("Delete peer")

    def add_schedule(self, call):
        self.schedules.append(dict(call.body, rbd=None))
        return 204, None

    def delete_schedule(self, call):
        key = (call.body["interval"], call.body.get("startTime"))
        self.schedules = [s for s in self.schedules if (s["interval"], s.get("startTime")) != key]
        return 204, None

    def get_image(self, call, rbd):
        if rbd not in self.images:
            return 404, dict(code=404, message="no image")
        return 200, copy.deepcopy(self.images[rbd])

    def patch_image(self, call, rbd):
        image = self.images[rbd]
        if call.body.get("journaling"):
            image["features"].append("JOURNALING")
        if "imageMirrorMode" in call.body:
            image["mirrorInfo"]["imageMirrorMode"] = call.body["imageMirrorMode"]
            image["mirrorInfo"]["primary"] = True
        if "primary" in call.body:
            image["mirrorInfo"]["primary"] = call.body["primary"]
        return 200, self.new_task("Image mirroring")


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, rbd_mirror.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], fake.writes()


SPEC = dict(
    pool="rbd",
    mode="image",
    site_name="primary",
    peer=dict(site_name="backup", token="PEER-TOKEN", direction="tx-only"),
    schedules=[dict(interval="1h")],
    images=[dict(name="vm1", mode="snapshot")],
)


def test_full_idempotency_sequence(monkeypatch):
    fake = MirrorCluster()

    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert r["changed"]
    assert r["diff"]["after"]["mode"] == "image"
    assert r["diff"]["after"]["peers"] == ["backup (tx-only)"]
    assert "PEER-TOKEN" not in repr(r)
    assert_only_gets(fake)
    assert fake.mode == "disabled"

    r = run(monkeypatch, fake, **SPEC)
    assert r["changed"]
    assert [c.method + " " + c.path for c in fake.writes()][0] == "PATCH /pools/rbd/rbd-mirror"
    assert fake.mode == "image" and fake.site == "primary"
    assert fake.peers[0]["direction"] == "tx-only"
    assert fake.schedules == [dict(pool="rbd", namespace=None, interval="1h", startTime=None, rbd=None)]
    assert fake.images["vm1"]["mirrorInfo"]["imageMirrorMode"] == "snapshot"
    assert "PEER-TOKEN" not in repr(r)

    r = run(monkeypatch, fake, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert not r["changed"]

    update = dict(pool="rbd", peer=dict(site_name="backup", direction="rx-tx"), schedules=[dict(interval="30m")], purge_schedules=True,
                  images=[dict(name="vm1", primary=False)])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["schedules"] == ["1h"] and r["diff"]["after"]["schedules"] == ["30m"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.peers[0]["direction"] == "rx-tx"
    assert [s["interval"] for s in fake.schedules] == ["30m"]
    assert fake.images["vm1"]["mirrorInfo"]["primary"] is False

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    off = dict(pool="rbd", mode="disabled", images=[dict(name="vm1", mode="disabled")])
    r = run(monkeypatch, fake, check_mode=True, **off)
    assert r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, ignore_warnings=True, **off)
    assert r["changed"]
    # image disabled before the pool
    assert [c.path for c in fake.writes() if not c.query.get("ignoreWarning")][0] == "/pools/rbd/rbds/vm1/rbd-mirror"
    assert fake.mode == "disabled" and not fake.peers

    r = run(monkeypatch, fake, **off)
    assert not r["changed"]
    assert_only_gets(fake)


def test_disable_needs_ignore_warnings(monkeypatch):
    fake = MirrorCluster()
    fake.mode = "pool"
    r = run(monkeypatch, fake, pool="rbd", mode="disabled")
    assert r["failed"] and r["warning"] == "peers go away"


def test_journal_mode_enables_journaling(monkeypatch):
    fake = MirrorCluster()
    fake.mode = "image"
    r = run(monkeypatch, fake, pool="rbd", images=[dict(name="vm1", mode="journal")])
    assert r["changed"]
    assert fake.writes()[0].body == dict(imageMirrorMode="journal", journaling=True)


def test_image_mode_needs_image_pool(monkeypatch):
    fake = MirrorCluster()
    fake.mode = "pool"
    r = run(monkeypatch, fake, pool="rbd", images=[dict(name="vm1", mode="snapshot")])
    assert r["failed"]
    assert_only_gets(fake)


def test_new_peer_needs_token(monkeypatch):
    fake = MirrorCluster()
    fake.mode = "image"
    r = run(monkeypatch, fake, pool="rbd", peer=dict(site_name="backup"))
    assert r["failed"] and "token" in r["msg"]


def test_peer_absent(monkeypatch):
    fake = MirrorCluster()
    fake.mode = "image"
    fake.peers = [dict(id=PEER_ID, siteName="backup", clientName="c", direction="rx-tx")]
    r = run(monkeypatch, fake, pool="rbd", peer=dict(site_name="backup", state="absent"))
    assert r["changed"] and not fake.peers
    r = run(monkeypatch, fake, pool="rbd", peer=dict(site_name="backup", state="absent"))
    assert not r["changed"]


def test_schedules_without_purge_are_additive(monkeypatch):
    fake = MirrorCluster()
    fake.mode = "image"
    fake.schedules = [dict(pool="rbd", namespace=None, rbd=None, interval="1d", startTime="02:00:00"),
                      dict(pool="other", namespace=None, rbd=None, interval="1h", startTime=None)]
    r = run(monkeypatch, fake, pool="rbd", schedules=[dict(interval="1d", start_time="02:00:00")])
    assert not r["changed"]
    r = run(monkeypatch, fake, pool="rbd", schedules=[], purge_schedules=True)
    assert r["changed"]
    assert [s["pool"] for s in fake.schedules] == ["other"]


def test_return_token_not_in_check_mode(monkeypatch):
    fake = MirrorCluster()
    fake.mode = "image"
    r = run(monkeypatch, fake, check_mode=True, pool="rbd", return_token=True)
    assert "bootstrap_token" not in r
    r = run(monkeypatch, fake, pool="rbd", return_token=True)
    assert r["bootstrap_token"] == "BOOTSTRAP-SECRET"
    assert not r["changed"]


def test_unmirrorable_pool_fails(monkeypatch):
    r = run(monkeypatch, MirrorCluster(), pool="ec", mode="pool")
    assert r["failed"]


def test_site_name_needs_enabled_mirroring(monkeypatch):
    fake = MirrorCluster()
    r = run(monkeypatch, fake, pool="rbd", site_name="x")
    assert r["failed"]
