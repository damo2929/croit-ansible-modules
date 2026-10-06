# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import cluster_info, task_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module


def info_cluster():
    fake = FakeCroit()
    fake.reply("GET", "/status", 200, dict(state="RUNNING"))
    fake.reply("GET", "/status/croit-version", 200, "v2508.1.squid")
    fake.reply("GET", "/cluster/status", 200, dict(health="HEALTH_OK"))
    fake.reply("GET", "/cluster/releases", 200, [dict(release="squid", count=3)])
    fake.reply("GET", "/license", 200, dict(valid=True))
    fake.reply("GET", "/tasks/active", 200, [dict(id=1, state="RUNNING")])
    fake.reply("GET", "/tasks/status", 200, [dict(id=2, state="FINISHED", output="x")])
    return fake


def test_cluster_info_all(monkeypatch):
    fake = info_cluster()
    r = run_module(monkeypatch, fake, cluster_info.main, check_mode=True)
    assert not r["changed"]
    assert r["version"] == "v2508.1.squid"
    assert r["status"] == dict(health="HEALTH_OK")
    assert set(r) >= set(["backend", "version", "status", "releases", "license"])
    assert fake.writes() == []


def test_cluster_info_subset(monkeypatch):
    fake = info_cluster()
    r = run_module(monkeypatch, fake, cluster_info.main, gather=["version"])
    assert "status" not in r
    assert len(fake.calls) == 1


def test_task_info_active(monkeypatch):
    fake = info_cluster()
    r = run_module(monkeypatch, fake, task_info.main)
    assert r["tasks"] == [dict(id=1, state="RUNNING")]
    assert not r["changed"]


def test_task_info_by_id(monkeypatch):
    fake = info_cluster()
    r = run_module(monkeypatch, fake, task_info.main, task_ids=[2])
    assert r["tasks"][0]["id"] == 2
    assert fake.calls[0].query == dict(taskIds="2")
