# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

from ansible_collections.croit.ceph.plugins.modules import pool_qos
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_rbd import MIB, RbdCluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, pool_qos.main, check_mode=check_mode, **params)


def test_full_idempotency_sequence(monkeypatch):
    """set = create, change = update, removal (null / exclusive) = delete."""
    fake = RbdCluster()
    spec = dict(pool="rbd", limits=dict(rbd_qos_iops_limit=2000, rbd_qos_bps_limit="200M"))

    # 1-2. set in check mode, then for real
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"] == dict(rbd_qos_iops_limit=2000, rbd_qos_bps_limit=200 * MIB)
    assert fake.writes() == []
    assert fake.pool_qos["rbd"] == {}
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.pool_qos["rbd"] == dict(rbd_qos_iops_limit=2000, rbd_qos_bps_limit=200 * MIB)

    # 3-4. re-run, and in check mode
    for check in (False, True):
        r = run(monkeypatch, fake, check_mode=check, **spec)
        assert not r["changed"]
        assert fake.writes() == []

    # 5-7. update in check mode, update, update again
    update = dict(pool="rbd", limits=dict(rbd_qos_iops_limit=3000))
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["rbd_qos_iops_limit"] == 2000
    assert r["diff"]["after"]["rbd_qos_iops_limit"] == 3000
    assert fake.writes() == []
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.writes()[0].body == [dict(command="rbd_qos_iops_limit", limit=3000)]
    assert fake.pool_qos["rbd"]["rbd_qos_bps_limit"] == 200 * MIB
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert fake.writes() == []

    # 8-10. remove everything in check mode, for real, and again
    clear = dict(pool="rbd", exclusive=True)
    r = run(monkeypatch, fake, check_mode=True, **clear)
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert fake.writes() == []
    r = run(monkeypatch, fake, **clear)
    assert r["changed"]
    assert fake.pool_qos["rbd"] == {}
    r = run(monkeypatch, fake, **clear)
    assert not r["changed"]
    assert fake.writes() == []


def test_null_removes_one_limit(monkeypatch):
    fake = RbdCluster()
    fake.pool_qos["rbd"] = dict(rbd_qos_iops_limit=1, rbd_qos_bps_limit=2)
    r = run(monkeypatch, fake, pool="rbd", limits=dict(rbd_qos_bps_limit=None))
    assert r["changed"]
    assert fake.pool_qos["rbd"] == dict(rbd_qos_iops_limit=1)


def test_exclusive_keeps_listed(monkeypatch):
    fake = RbdCluster()
    fake.pool_qos["rbd"] = dict(rbd_qos_iops_limit=1, rbd_qos_bps_limit=2)
    r = run(monkeypatch, fake, pool="rbd", limits=dict(rbd_qos_iops_limit=1), exclusive=True)
    assert r["changed"]
    assert fake.pool_qos["rbd"] == dict(rbd_qos_iops_limit=1)


def test_unknown_key_and_missing_pool(monkeypatch):
    fake = RbdCluster()
    r = run(monkeypatch, fake, pool="rbd", limits=dict(iops=5))
    assert r["failed"]
    assert "rbd_qos_iops_limit" in r["msg"]
    r = run(monkeypatch, fake, pool="nope", limits=dict(rbd_qos_iops_limit=5))
    assert r["failed"]
    assert "does not exist" in r["msg"]


def test_rejected_limit_fails(monkeypatch):
    fake = RbdCluster()
    fake.routes.insert(
        0,
        (
            "POST",
            re.compile("^/pools/rbd/qos$"),
            lambda call: (200, [dict(command="rbd_qos_iops_limit", success=False, errorMessage="rbd said no")]),
        ),
    )
    r = run(monkeypatch, fake, pool="rbd", limits=dict(rbd_qos_iops_limit=5))
    assert r["failed"]
    assert "rbd said no" in r["msg"]


def test_invalid_value(monkeypatch):
    fake = RbdCluster()
    r = run(monkeypatch, fake, pool="rbd", limits=dict(rbd_qos_bps_limit="fast"))
    assert r["failed"]
