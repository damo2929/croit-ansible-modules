# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import rgw_service
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_rgw import RgwCluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, rgw_service.main, check_mode=check_mode, **params)


def servers_with_gateway(fake):
    return sorted(s["server"] for s in fake.services)


def test_full_idempotency_sequence(monkeypatch):
    fake = RgwCluster(gateways_on=[1])
    spec = dict(servers=["node1", "node2"], ha_groups=["s3-vip"])

    # 1. add (check mode)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and fake.writes() == []
    assert r["diff"]["before"]["servers"] == ["node1"]
    assert r["diff"]["after"]["servers"] == ["node1", "node2"]
    # 2. add
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    post = [c for c in fake.writes() if c.method == "POST"][0]
    assert post.body == dict(serverIds=[2], haGroupIds=[7])
    assert servers_with_gateway(fake) == [1, 2]
    # 3./4. again
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"] and fake.writes() == []
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"] and fake.writes() == []
    # 5. config change (check mode)
    update = dict(servers=["node1", "node2"], port=8080, dns_name="s3.example.com")
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"] and fake.writes() == []
    assert r["diff"]["after"]["config"]["node2"] == dict(port=8080, dns_name="s3.example.com")
    assert r["diff"]["before"]["config"]["node2"] == dict(port=None, dns_name=None)
    # 6. config change: only changed fields, one PATCH per gateway
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    patches = [c for c in fake.writes() if c.method == "PATCH"]
    assert len(patches) == 2
    assert patches[0].body == dict(port=8080, rgwDnsName="s3.example.com")
    assert r["config"]["node1"]["port"] == 8080
    # 7. again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"] and fake.writes() == []
    # 8. remove (check mode)
    r = run(monkeypatch, fake, check_mode=True, servers=["node2"], state="absent")
    assert r["changed"] and fake.writes() == []
    assert servers_with_gateway(fake) == [1, 2]
    # 9. remove
    r = run(monkeypatch, fake, servers=["node2"], state="absent")
    assert r["changed"]
    assert servers_with_gateway(fake) == [1]
    # 10. remove again
    r = run(monkeypatch, fake, servers=["node2"], state="absent")
    assert not r["changed"] and fake.writes() == []


def test_new_gateway_gets_config_in_same_run(monkeypatch):
    fake = RgwCluster(gateways_on=[1])
    r = run(monkeypatch, fake, servers=["node3"], port=7480)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST", "PATCH"]
    gateway = [s for s in fake.services if s["server"] == 3][0]
    assert fake.configs[gateway["id"]]["port"] == 7480
    r = run(monkeypatch, fake, servers=["node3"], port=7480)
    assert not r["changed"]


def test_exclusive_removes_unlisted(monkeypatch):
    fake = RgwCluster(gateways_on=[1, 2, 3])
    r = run(monkeypatch, fake, servers=["node1"], exclusive=True)
    assert r["changed"]
    assert servers_with_gateway(fake) == [1]
    assert r["diff"]["after"]["servers"] == ["node1"]


def test_removing_last_gateway_needs_warning_confirmation(monkeypatch):
    fake = RgwCluster(gateways_on=[1])
    r = run(monkeypatch, fake, servers=["node1"], state="absent")
    assert r["failed"] and r["warning"] == "removes every gateway"
    assert servers_with_gateway(fake) == [1]
    r = run(monkeypatch, fake, servers=["node1"], state="absent", ignore_warnings=True)
    assert r["changed"] and fake.services == []


def test_multi_server_gateway_removed_per_server(monkeypatch):
    fake = RgwCluster()
    fake.services = [dict(id=60, type="radosgw", server=None, multiServer=[1, 2], running=True)]
    fake.configs[60] = {}
    fake.routes = [rt for rt in fake.routes if not (rt[0] == "DELETE")]
    fake.route("DELETE", r"/services/(?P<sid>\d+)", lambda call, sid: (200, fake.new_task("rm")))
    r = run(monkeypatch, fake, servers=["node2"], state="absent")
    assert r["changed"]
    assert fake.writes()[0].query == dict(server="2")


def test_unknown_ha_group_fails_before_writes(monkeypatch):
    fake = RgwCluster(gateways_on=[1])
    r = run(monkeypatch, fake, servers=["node2"], ha_groups=["nope"])
    assert r["failed"] and "s3-vip (7)" in r["msg"]
    assert fake.writes() == []


def test_ha_groups_ignored_when_nothing_added(monkeypatch):
    fake = RgwCluster(gateways_on=[1])
    r = run(monkeypatch, fake, servers=["node1"], ha_groups=["nope"])
    assert not r.get("failed") and not r["changed"]
