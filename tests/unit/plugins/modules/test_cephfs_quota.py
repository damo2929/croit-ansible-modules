# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import re

from ansible_collections.croit.ceph.plugins.modules import cephfs_quota as quota_module
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

GIB = 1024 ** 3
POOLS = ["cephfs.data", "cephfs.ec"]


class QuotaCluster(FakeCroit):
    """Fake croit with per-directory quotas and layouts (keyed by volume, path)."""

    def __init__(self, quotas=None, layouts=None):
        super(QuotaCluster, self).__init__()
        self.quotas = dict(quotas or {})
        self.layouts = dict(layouts or {})
        self.route("GET", "/cephfs/quota", self.get_quota)
        self.route("PUT", "/cephfs/quota", self.put_quota)
        self.route("GET", "/cephfs/layout", self.get_layout)
        self.route("PUT", "/cephfs/layout", self.put_layout)
        self.reply("GET", "/cephfs/layout/pools", 200, POOLS)

    def get_quota(self, call):
        key = (call.query.get("volume"), call.query["dir"])
        return 200, copy.deepcopy(self.quotas.get(key, dict(maxBytes=None, maxFiles=None)))

    def put_quota(self, call):
        key = (call.query.get("volume"), call.query["dir"])
        body = call.body
        self.quotas[key] = dict(
            maxBytes=body["maxBytes"] if (body.get("maxBytes") or 0) > 0 else None,
            maxFiles=body["maxFiles"] if (body.get("maxFiles") or 0) > 0 else None,
        )
        return 204, None

    def get_layout(self, call):
        key = (call.query.get("volume"), call.query["path"])
        return 200, copy.deepcopy(self.layouts.get(key, dict(pool=None, namespace=None)))

    def put_layout(self, call):
        self.layouts[(call.query.get("volume"), call.query["path"])] = dict(call.body)
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, quota_module.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    """Set / change / unset instead of create / update / delete."""
    fake = QuotaCluster()
    where = dict(volume="fs1", path="/projects/a")
    key = ("fs1", "/projects/a")
    spec = dict(where, max_bytes="10G", max_files=1000)

    # 1. set in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["before"] == dict(max_bytes=0, max_files=0)
    assert r["diff"]["after"] == dict(max_bytes=10 * GIB, max_files=1000)
    assert_only_gets(fake)
    assert key not in fake.quotas

    # 2. set
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    write = fake.writes()[0]
    assert write.query == dict(dir="/projects/a", volume="fs1")
    assert write.body == dict(maxBytes=10 * GIB, maxFiles=1000)
    assert r["quota"] == dict(maxBytes=10 * GIB, maxFiles=1000)

    # 3. re-run
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. change in check mode (only max_bytes: max_files is left alone)
    change = dict(where, max_bytes="20G")
    r = run(monkeypatch, fake, check_mode=True, **change)
    assert r["changed"]
    assert r["diff"]["after"] == dict(max_bytes=20 * GIB, max_files=1000)
    assert_only_gets(fake)

    # 6. change: the untouched limit is sent along so it is kept
    r = run(monkeypatch, fake, **change)
    assert r["changed"]
    assert fake.writes()[0].body == dict(maxBytes=20 * GIB, maxFiles=1000)

    # 7. change again
    r = run(monkeypatch, fake, **change)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. unset in check mode
    r = run(monkeypatch, fake, check_mode=True, state="absent", **where)
    assert r["changed"]
    assert r["diff"]["after"] == dict(max_bytes=0, max_files=0)
    assert_only_gets(fake)
    assert fake.quotas[key]["maxBytes"] == 20 * GIB

    # 9. unset
    r = run(monkeypatch, fake, state="absent", **where)
    assert r["changed"]
    assert fake.writes()[0].body == dict(maxBytes=None, maxFiles=None)

    # 10. unset again
    r = run(monkeypatch, fake, state="absent", **where)
    assert not r["changed"]
    assert_only_gets(fake)


def test_unlimited_word_removes_one_limit(monkeypatch):
    fake = QuotaCluster(quotas={(None, "/a"): dict(maxBytes=GIB, maxFiles=10)})
    r = run(monkeypatch, fake, path="/a", max_bytes="unlimited")
    assert r["changed"]
    assert fake.writes()[0].body == dict(maxBytes=None, maxFiles=10)


def test_layout_is_only_read_when_managed(monkeypatch):
    fake = QuotaCluster()
    run(monkeypatch, fake, path="/a", max_files=5)
    assert not any(c.path.startswith("/cephfs/layout") for c in fake.calls)


def test_layout_set_and_idempotent(monkeypatch):
    fake = QuotaCluster()
    r = run(monkeypatch, fake, check_mode=True, path="/archive", layout_pool="cephfs.ec")
    assert r["changed"]
    assert r["diff"]["after"]["layout_pool"] == "cephfs.ec"
    assert_only_gets(fake)

    r = run(monkeypatch, fake, path="/archive", layout_pool="cephfs.ec")
    assert r["changed"]
    assert [c.path for c in fake.writes()] == ["/cephfs/layout"]
    assert fake.writes()[0].body == dict(pool="cephfs.ec", namespace=None)
    assert fake.writes()[0].query == dict(path="/archive")

    r = run(monkeypatch, fake, path="/archive", layout_pool="cephfs.ec")
    assert not r["changed"]
    assert_only_gets(fake)


def test_layout_back_to_inherit(monkeypatch):
    fake = QuotaCluster(layouts={(None, "/archive"): dict(pool="cephfs.ec", namespace="ns")})
    r = run(monkeypatch, fake, path="/archive", layout_pool="", layout_namespace="")
    assert r["changed"]
    assert fake.writes()[0].body == dict(pool=None, namespace=None)
    r = run(monkeypatch, fake, path="/archive", layout_pool="", layout_namespace="")
    assert not r["changed"]


def test_layout_pool_must_be_eligible(monkeypatch):
    fake = QuotaCluster()
    r = run(monkeypatch, fake, path="/archive", layout_pool="rbd")
    assert r["failed"]
    assert "cephfs.data, cephfs.ec" in r["msg"]
    assert_only_gets(fake)


def test_absent_does_not_take_limits(monkeypatch):
    fake = QuotaCluster()
    r = run(monkeypatch, fake, path="/a", state="absent", max_files=3)
    assert r["failed"]
    assert fake.calls == []


def test_relative_path_rejected(monkeypatch):
    fake = QuotaCluster()
    r = run(monkeypatch, fake, path="a/b", max_files=3)
    assert r["failed"]
    assert fake.calls == []


def test_croit_error_surfaces(monkeypatch):
    fake = QuotaCluster()
    fake.routes.insert(0, ("PUT", re.compile("^/cephfs/quota$"), lambda call: (400, dict(code=400, message="root cannot be limited"))))
    r = run(monkeypatch, fake, path="/", max_files=3)
    assert r["failed"]
    assert "root cannot be limited" in r["msg"]
