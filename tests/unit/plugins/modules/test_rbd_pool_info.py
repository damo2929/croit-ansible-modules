# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for croit.ceph.pool_info and croit.ceph.rbd_info."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import pool_info, rbd_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_rbd import MIB, RbdCluster


def pools_cluster():
    fake = FakeCroit()
    fake.reply("GET", "/pools", 200, [dict(name="a", poolId=1), dict(name="b", poolId=2)])
    fake.reply("GET", "/pools/a/details", 200, dict(pg_num=32))
    fake.reply("GET", "/pools/a/compression", 200, dict(algorithm="None", mode="None"))
    return fake


def test_pool_info_all(monkeypatch):
    fake = pools_cluster()
    r = run_module(monkeypatch, fake, pool_info.main, check_mode=True)
    assert not r["changed"]
    assert [p["name"] for p in r["pools"]] == ["a", "b"]
    assert len(fake.calls) == 1


def test_pool_info_one_with_details(monkeypatch):
    fake = pools_cluster()
    r = run_module(monkeypatch, fake, pool_info.main, name="a", details=True)
    assert r["pools"] == [dict(name="a", poolId=1, details=dict(pg_num=32), compression=dict(algorithm="None", mode="None"))]


def test_pool_info_unknown(monkeypatch):
    fake = pools_cluster()
    r = run_module(monkeypatch, fake, pool_info.main, name="zzz")
    assert r["pools"] == []
    assert not r.get("failed")


def rbd_cluster():
    fake = RbdCluster(pools=("rbd", "other"))
    fake.add_image("rbd", "a", MIB, snaps=[dict(id=1, name="s", protect=False)])
    fake.add_image("rbd", "b", 2 * MIB, namespace="t")
    fake.add_image("other", "c", 3 * MIB)
    return fake


def test_rbd_info_pool_filter_batched(monkeypatch):
    fake = rbd_cluster()
    r = run_module(monkeypatch, fake, rbd_info.main, check_mode=True, pool="rbd")
    assert not r["changed"]
    assert sorted(i["name"] for i in r["images"]) == ["a", "b"]
    infos = [c for c in fake.calls if c.path == "/rbds/rbd-infos"]
    assert len(infos) == 1
    assert sorted(infos[0].query["image"]) == ["rbd/a", "rbd/t/b"]


def test_rbd_info_default_namespace_only(monkeypatch):
    fake = rbd_cluster()
    r = run_module(monkeypatch, fake, rbd_info.main, pool="rbd", namespace="")
    assert [i["name"] for i in r["images"]] == ["a"]


def test_rbd_info_one_image_has_snapshots(monkeypatch):
    fake = rbd_cluster()
    r = run_module(monkeypatch, fake, rbd_info.main, pool="rbd", name="a")
    assert r["images"][0]["snaps"] == [dict(id=1, name="s", protect=False)]


def test_rbd_info_names_only(monkeypatch):
    fake = rbd_cluster()
    r = run_module(monkeypatch, fake, rbd_info.main, details=False)
    assert len(r["images"]) == 3
    assert len(fake.calls) == 1


def test_rbd_info_name_requires_pool(monkeypatch):
    fake = rbd_cluster()
    r = run_module(monkeypatch, fake, rbd_info.main, name="a")
    assert r["failed"]


def test_rbd_info_missing_image(monkeypatch):
    fake = rbd_cluster()
    r = run_module(monkeypatch, fake, rbd_info.main, pool="rbd", name="zzz")
    assert r["images"] == []
