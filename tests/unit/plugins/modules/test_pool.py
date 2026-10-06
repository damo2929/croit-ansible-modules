# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import re

import pytest

from ansible_collections.croit.ceph.plugins.modules import pool as pool_module
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

RULES = [dict(id=0, name="replicated_rule", type="replicated", steps=[]), dict(id=1, name="ssd", type="replicated", steps=[])]
DEFAULT_COMPRESSION = dict(algorithm="None", mode="None", minBlobSize=None, maxBlobSize=None, requiredRatio=None)


class PoolCluster(FakeCroit):
    """Fake croit holding pools, applying creates, patches and deletes."""

    def __init__(self, pools=None):
        super(PoolCluster, self).__init__()
        self.pools = dict((p["name"], p) for p in (pools or []))
        self.compression = dict((name, dict(DEFAULT_COMPRESSION)) for name in self.pools)
        self.next_id = 10
        self.serve_tasks()
        self.reply("GET", "/crush/rules", 200, RULES)
        self.route("GET", "/pools", lambda call: (200, [copy.deepcopy(p) for p in self.pools.values()]))
        self.route("POST", "/pools", self.create)
        self.route("PATCH", "/pools/(?P<name>[^/]+)", self.patch)
        self.route("DELETE", "/pools/(?P<name>[^/]+)", self.delete)
        self.route("GET", "/pools/(?P<name>[^/]+)/compression", self.get_compression)

    def create(self, call):
        body = call.body
        ec = bool(body.get("erasureCoding"))
        k, m = body.get("dataChunks", 4), body.get("parityChunks", 2)
        self.next_id += 1
        self.pools[body["name"]] = dict(
            name=body["name"],
            poolId=self.next_id,
            application=body.get("application"),
            description=body.get("description") or "",
            erasureCoding=ec,
            dataChunks=k if ec else None,
            parityChunks=m if ec else None,
            size=k + m if ec else body.get("size", 3),
            minSize=k + 1 if ec else body.get("minSize", 2),
            pgNum=body.get("pgNum", 128),
            crushRule=body.get("crushRule", 0),
            fastRead=body.get("fastRead", False),
            quotaMaxBytes=body.get("quotaMaxBytes", 0),
            quotaMaxObjects=body.get("quotaMaxObjects", 0),
            deleteProtected=True,
        )
        comp = dict(DEFAULT_COMPRESSION)
        comp.update(body.get("compression") or {})
        self.compression[body["name"]] = comp
        return 200, self.new_task("Create pool", body["name"])

    def patch(self, call, name):
        pool = self.pools[name]
        body = dict(call.body)
        if body.pop("unprotect", None):
            pool["deleteProtected"] = False
        if "compression" in body:
            self.compression[name].update(body.pop("compression"))
        pool.update(body)
        return 204, None

    def delete(self, call, name):
        pool = self.pools[name]
        if pool["deleteProtected"]:
            return 400, dict(code=400, message="pool is protected")
        assert call.body["poolId"] == pool["poolId"]
        assert call.body["thisWillDeleteData"] == pool_module.DELETE_CONFIRMATION
        del self.pools[name]
        return 204, None

    def get_compression(self, call, name):
        return 200, copy.deepcopy(self.compression[name])


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, pool_module.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "check mode or no-op run wrote: %r" % fake.writes()


# The standard idempotency sequence (DESIGN.md section 4) ---------------------


def test_full_idempotency_sequence(monkeypatch):
    fake = PoolCluster()
    spec = dict(name="rbd", application="rbd", size=3, min_size=2, crush_rule="ssd", description="VMs")

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["before"] == {}
    assert r["diff"]["after"]["crush_rule"] == 1
    assert_only_gets(fake)
    assert "rbd" not in fake.pools

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["pool"]["name"] == "rbd"
    assert r["task"]["state"] == "FINISHED"
    assert fake.pools["rbd"]["crushRule"] == 1

    # 3. re-run: no change, no writes
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode
    update = dict(spec)
    update.update(size=4, quota_max_bytes="1T")
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["size"] == 3
    assert r["diff"]["after"]["size"] == 4
    assert r["diff"]["after"]["quota_max_bytes"] == 1024 ** 4
    assert_only_gets(fake)
    assert fake.pools["rbd"]["size"] == 3

    # 6. update: only changed fields are sent
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    patch = [c for c in fake.writes() if c.method == "PATCH"]
    assert len(patch) == 1
    assert patch[0].body == dict(size=4, quotaMaxBytes=1024 ** 4)
    assert r["pool"]["size"] == 4

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, name="rbd", state="absent", confirm_delete=True)
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert "rbd" in fake.pools

    # 9. delete: lifts the protection, then deletes
    r = run(monkeypatch, fake, name="rbd", state="absent", confirm_delete=True)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["PATCH", "DELETE"]
    assert "rbd" not in fake.pools

    # 10. delete again
    r = run(monkeypatch, fake, name="rbd", state="absent", confirm_delete=True)
    assert not r["changed"]
    assert_only_gets(fake)


# Behaviour details -----------------------------------------------------------


def existing(**overrides):
    pool = dict(
        name="rbd",
        poolId=3,
        application="rbd",
        description="",
        erasureCoding=False,
        dataChunks=None,
        parityChunks=None,
        size=3,
        minSize=2,
        pgNum=128,
        crushRule=0,
        fastRead=False,
        quotaMaxBytes=0,
        quotaMaxObjects=0,
        deleteProtected=True,
    )
    pool.update(overrides)
    return pool


def test_unset_options_are_left_alone(monkeypatch):
    fake = PoolCluster([existing(size=5, pgNum=256)])
    r = run(monkeypatch, fake, name="rbd")
    assert not r["changed"]
    assert_only_gets(fake)


def test_crush_rule_by_id(monkeypatch):
    fake = PoolCluster([existing(crushRule=1)])
    r = run(monkeypatch, fake, name="rbd", crush_rule="1")
    assert not r["changed"]


def test_unknown_crush_rule_fails(monkeypatch):
    fake = PoolCluster([existing()])
    r = run(monkeypatch, fake, name="rbd", crush_rule="nope")
    assert r["failed"]
    assert "replicated_rule (0)" in r["msg"]


def test_empty_description_matches_unset(monkeypatch):
    fake = PoolCluster([existing(description=None)])
    r = run(monkeypatch, fake, name="rbd", description="")
    assert not r["changed"]


def test_immutable_field_fails_instead_of_recreating(monkeypatch):
    fake = PoolCluster([existing()])
    r = run(monkeypatch, fake, check_mode=True, name="rbd", erasure_coding=True)
    assert r["failed"]
    assert "cannot be changed" in r["msg"]
    assert_only_gets(fake)


def test_size_rejected_on_erasure_coded_pool(monkeypatch):
    fake = PoolCluster([existing(erasureCoding=True, dataChunks=4, parityChunks=2, size=6)])
    r = run(monkeypatch, fake, name="rbd", size=3)
    assert r["failed"]


def test_ec_only_options_rejected_on_replicated_create(monkeypatch):
    fake = PoolCluster()
    r = run(monkeypatch, fake, name="new", data_chunks=4)
    assert r["failed"]
    assert_only_gets(fake)


def test_ec_create_sends_profile(monkeypatch):
    fake = PoolCluster()
    r = run(
        monkeypatch,
        fake,
        name="data",
        application="rgw",
        erasure_coding=True,
        data_chunks=8,
        parity_chunks=3,
        device_class="hdd",
    )
    assert r["changed"]
    body = fake.writes()[0].body
    assert body["erasureCoding"] is True
    assert (body["dataChunks"], body["parityChunks"], body["deviceClass"]) == (8, 3, "hdd")
    assert "size" not in body
    # create-only device_class is not compared afterwards
    r = run(monkeypatch, fake, name="data", erasure_coding=True, data_chunks=8, parity_chunks=3, device_class="ssd")
    assert not r["changed"]


def test_compression_idempotent_and_merged(monkeypatch):
    fake = PoolCluster([existing()])
    fake.compression["rbd"] = dict(DEFAULT_COMPRESSION, algorithm="LZ4", mode="Passive")
    r = run(monkeypatch, fake, name="rbd", compression=dict(mode="aggressive"))
    assert r["changed"]
    body = fake.writes()[0].body
    assert body == dict(compression=dict(DEFAULT_COMPRESSION, algorithm="LZ4", mode="Aggressive"))
    assert r["diff"]["before"]["compression"] == dict(mode="Passive")
    assert r["diff"]["after"]["compression"] == dict(mode="Aggressive")
    r = run(monkeypatch, fake, name="rbd", compression=dict(mode="aggressive", algorithm="lz4"))
    assert not r["changed"]
    assert_only_gets(fake)


def test_delete_requires_confirmation(monkeypatch):
    fake = PoolCluster([existing()])
    r = run(monkeypatch, fake, name="rbd", state="absent")
    assert r["failed"]
    assert "confirm_delete" in r["msg"]
    assert "rbd" in fake.pools


def test_unprotected_pool_is_deleted_without_patch(monkeypatch):
    fake = PoolCluster([existing(deleteProtected=False)])
    r = run(monkeypatch, fake, name="rbd", state="absent", confirm_delete=True)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["DELETE"]


def test_failed_create_task_fails_module(monkeypatch):
    fake = PoolCluster()
    fake.routes = [r for r in fake.routes if not (r[0] == "POST")]
    fake.route("POST", "/pools", lambda call: (200, fake.new_task("Create pool", "x", state="FAILED", output="ceph said no")))
    r = run(monkeypatch, fake, name="x")
    assert r["failed"]
    assert "ceph said no" in r["msg"]


def test_no_wait_returns_running_task(monkeypatch):
    fake = PoolCluster()
    fake.routes = [r for r in fake.routes if not (r[0] == "POST")]
    fake.route("POST", "/pools", lambda call: (200, fake.new_task("Create pool", "x", state="RUNNING")))
    r = run(monkeypatch, fake, name="x", wait=False)
    assert r["changed"]
    assert r["task"]["state"] == "RUNNING"
    assert not any(c.path.startswith("/tasks") for c in fake.calls)


def test_application_change_warning(monkeypatch):
    fake = PoolCluster([existing()])
    fake.routes.insert(
        0,
        (
            "PATCH",
            re.compile("^/pools/rbd$"),
            lambda call, **kw: (400, dict(code=400, message="w", ignorableWarning=dict(token="t", warningText="metadata goes")))
            if call.query.get("ignoreWarning") != "t"
            else fake.patch(call, "rbd"),
        ),
    )
    r = run(monkeypatch, fake, name="rbd", application="cephfs")
    assert r["failed"]
    assert r["warning"] == "metadata goes"
    assert fake.pools["rbd"]["application"] == "rbd"

    r = run(monkeypatch, fake, name="rbd", application="cephfs", ignore_warnings=True)
    assert r["changed"]
    assert fake.pools["rbd"]["application"] == "cephfs"


@pytest.mark.parametrize("value", ["lots", "1.5"])
def test_invalid_quota(monkeypatch, value):
    fake = PoolCluster([existing()])
    r = run(monkeypatch, fake, name="rbd", quota_max_bytes=value)
    assert r["failed"]
    assert "quota_max_bytes" in r["msg"]


def test_token_is_not_logged(monkeypatch):
    fake = PoolCluster([existing()])
    r = run(monkeypatch, fake, name="rbd")
    assert "secret-token" not in repr(r)
