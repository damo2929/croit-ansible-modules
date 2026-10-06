# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import rgw_bootstrap
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_rgw import RgwCluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, rgw_bootstrap.main, check_mode=check_mode, **params)


def test_bootstrap_sequence(monkeypatch):
    fake = RgwCluster()
    spec = dict(servers=["node1", "2"], zone="dc1", realm="r1")

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and fake.writes() == []
    assert r["diff"]["after"]["servers"] == ["node1", "node2"]
    assert fake.services == []

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.bootstrap_body == dict(serverIds=[1, 2], zone="dc1", realm="r1")
    assert len(r["gateways"]) == 2
    assert r["task"]["state"] == "FINISHED"

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"] and fake.writes() == []

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"] and fake.writes() == []


def test_already_bootstrapped_ignores_servers(monkeypatch):
    fake = RgwCluster(gateways_on=[3])
    r = run(monkeypatch, fake, servers=["node1"])
    assert not r["changed"]
    assert fake.writes() == []


def test_zone_mismatch_fails(monkeypatch):
    fake = RgwCluster(gateways_on=[1])
    fake.configs[fake.services[0]["id"]]["zone"] = "other"
    r = run(monkeypatch, fake, check_mode=True, servers=["node1"], zone="dc1")
    assert r["failed"] and "other" in r["msg"]


def test_inherited_zone_is_not_a_mismatch(monkeypatch):
    fake = RgwCluster(gateways_on=[1])
    r = run(monkeypatch, fake, servers=["node1"], zone="dc1")
    assert not r.get("failed") and not r["changed"]


def test_secondary_refuses_bootstrap(monkeypatch):
    fake = RgwCluster(multisite=dict(enabled=True, type="SECONDARY", readonly=True, metrics={}))
    r = run(monkeypatch, fake, servers=["node1"])
    assert r["failed"] and "rgw_service" in r["msg"]
    assert fake.writes() == []


def test_unknown_server_fails(monkeypatch):
    fake = RgwCluster()
    r = run(monkeypatch, fake, servers=["ghost"])
    assert r["failed"] and "node1 (1)" in r["msg"]


def test_empty_servers_fails(monkeypatch):
    r = run(monkeypatch, RgwCluster(), servers=[])
    assert r["failed"]


def test_failed_task_fails(monkeypatch):
    fake = RgwCluster()
    fake.routes = [rt for rt in fake.routes if rt[0] != "POST"]
    fake.route("POST", "/s3/bootstrap", lambda call: (200, fake.new_task("Bootstrap S3", state="FAILED", output="no pools")))
    r = run(monkeypatch, fake, servers=["node1"])
    assert r["failed"] and "no pools" in r["msg"]
