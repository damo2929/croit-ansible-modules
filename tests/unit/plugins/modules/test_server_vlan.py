# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

from ansible_collections.croit.ceph.plugins.modules import server_vlan
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_servers import ServerCluster, nic, server


def cluster():
    return ServerCluster(
        servers=[server(1, "node1")],
        nics=[
            nic(11, 1, "eth0", "aa:bb:cc:00:00:01", ip="10.0.0.1/24"),
            nic(12, 1, "bond0", "aa:bb:cc:00:00:02", type="bond"),
        ],
    )


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, server_vlan.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()
    spec = dict(server="node1", nic="bond0", vlan=110, ip="10.110.0.1/24")

    # 1-2. create
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"] == dict(vlan=110, ip="10.110.0.1/24", ip6="")
    assert_only_gets(fake)
    assert fake.nics[12]["vlans"] == []
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(vlan=110, ip="10.110.0.1/24")
    assert r["vlan"]["vlan"] == 110

    # 3-4. re-run
    assert not run(monkeypatch, fake, **spec)["changed"]
    assert_only_gets(fake)
    assert not run(monkeypatch, fake, check_mode=True, **spec)["changed"]
    assert_only_gets(fake)

    # 5-7. update
    update = dict(spec)
    update.update(ip="10.110.0.2/24", ip6="fd00:110::1/64")
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["ip"] == "10.110.0.1/24"
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.writes()[0].body == dict(ip="10.110.0.2/24", ip6="fd00:110::1/64")
    assert not run(monkeypatch, fake, **update)["changed"]
    assert_only_gets(fake)

    # 8-10. delete
    absent = dict(server="node1", nic="bond0", vlan=110, state="absent", confirm_delete=True)
    assert run(monkeypatch, fake, check_mode=True, **absent)["changed"]
    assert_only_gets(fake)
    assert len(fake.nics[12]["vlans"]) == 1
    assert run(monkeypatch, fake, **absent)["changed"]
    assert fake.nics[12]["vlans"] == []
    assert not run(monkeypatch, fake, **absent)["changed"]
    assert_only_gets(fake)


def test_unset_ip_left_alone(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, server="node1", nic="bond0", vlan=110, ip="10.110.0.1/24")
    r = run(monkeypatch, fake, server="node1", nic="bond0", vlan=110)
    assert not r["changed"]


def test_vlan_range(monkeypatch):
    r = run(monkeypatch, cluster(), server="node1", nic="bond0", vlan=5000)
    assert r["failed"]


def test_unknown_parent(monkeypatch):
    r = run(monkeypatch, cluster(), server="node1", nic="bond9", vlan=10)
    assert r["failed"]
    assert "bond0" in r["msg"]


def test_delete_requires_confirmation(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, server="node1", nic="bond0", vlan=110)
    r = run(monkeypatch, fake, server="node1", nic="bond0", vlan=110, state="absent")
    assert r["failed"]
    assert len(fake.nics[12]["vlans"]) == 1


def test_management_ip_on_vlan_protected(monkeypatch):
    fake = cluster()
    fake.servers[1]["ip"] = "10.110.0.1"
    run(monkeypatch, fake, server="node1", nic="bond0", vlan=110, ip="10.110.0.1/24")
    r = run(monkeypatch, fake, server="node1", nic="bond0", vlan=110, ip="")
    assert r["failed"]
    assert "management IP" in r["msg"]
    r = run(monkeypatch, fake, server="node1", nic="bond0", vlan=110, state="absent", confirm_delete=True)
    assert r["failed"]
    r = run(monkeypatch, fake, server="node1", nic="bond0", vlan=110, state="absent", confirm_delete=True, allow_management_ip_change=True)
    assert r["changed"]


def test_ip_conflict_warning(monkeypatch):
    fake = cluster()
    original = fake.create_vlan

    def create(call, sid, nid):
        if call.query.get("ignoreWarning") != "tok":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="tok", warningText="IP conflicts"))
        return original(call, sid, nid)

    fake.routes.insert(0, ("POST", re.compile(r"^/servers/(?P<sid>\d+)/nics/(?P<nid>\d+)/vlans$"), create))
    r = run(monkeypatch, fake, server="node1", nic="bond0", vlan=110, ip="10.0.0.1/24")
    assert r["failed"]
    assert r["warning"] == "IP conflicts"
    r = run(monkeypatch, fake, server="node1", nic="bond0", vlan=110, ip="10.0.0.1/24", ignore_warnings=True)
    assert r["changed"]
