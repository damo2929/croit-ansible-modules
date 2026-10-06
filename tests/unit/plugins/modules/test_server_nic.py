# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import server_nic
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_servers import ServerCluster, nic, server


def cluster():
    return ServerCluster(
        servers=[server(1, "node1")],
        nics=[
            nic(11, 1, "eth0", "aa:bb:cc:00:00:01", ip="10.0.0.1/24"),
            nic(12, 1, "eth1", "aa:bb:cc:00:00:02"),
            nic(13, 1, "docker0", "aa:bb:cc:00:00:03", isManaged=False),
        ],
    )


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, server_nic.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()
    spec = dict(server="node1", nic="eth1", ip="192.168.0.1/24", notes="cluster net")

    # 1-2. set addresses (check, then real)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"]["ip"] == "192.168.0.1/24"
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(ip="192.168.0.1/24", notes="cluster net")
    assert r["nic"]["ip"] == "192.168.0.1/24"

    # 3-4. re-run
    assert not run(monkeypatch, fake, **spec)["changed"]
    assert_only_gets(fake)
    assert not run(monkeypatch, fake, check_mode=True, **spec)["changed"]
    assert_only_gets(fake)

    # 5-7. change: clear the address, add IPv6 (by MAC)
    update = dict(server="node1", nic="AA-BB-CC-00-00-02", ip="", ip6="fd00::1/64")
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["ip"] == "192.168.0.1/24"
    assert r["diff"]["after"]["ip"] == ""
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.writes()[0].body == dict(ip="", ip6="fd00::1/64")
    assert fake.nics[12]["ip"] is None
    assert not run(monkeypatch, fake, **update)["changed"]
    assert_only_gets(fake)

    # 8-10. delete
    absent = dict(server="node1", nic="eth1", state="absent", confirm_delete=True)
    assert run(monkeypatch, fake, check_mode=True, **absent)["changed"]
    assert_only_gets(fake)
    assert 12 in fake.nics
    r = run(monkeypatch, fake, **absent)
    assert r["changed"]
    assert 12 not in fake.nics
    assert not run(monkeypatch, fake, **absent)["changed"]
    assert_only_gets(fake)


def test_unknown_nic_cannot_be_created(monkeypatch):
    r = run(monkeypatch, cluster(), server="node1", nic="eth9", ip="1.2.3.4/24")
    assert r["failed"]
    assert "server_bond" in r["msg"]


def test_management_ip_protected(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", nic="eth0", ip="10.0.0.99/24")
    assert r["failed"]
    assert "management IP" in r["msg"]
    r = run(monkeypatch, fake, server="node1", nic="eth0", ip="", check_mode=True)
    assert r["failed"]
    # a prefix-only change keeps the address
    r = run(monkeypatch, fake, server="node1", nic="eth0", ip="10.0.0.1/16")
    assert r["changed"]
    r = run(monkeypatch, fake, server="node1", nic="eth0", ip="10.0.0.99/24", allow_management_ip_change=True)
    assert r["changed"]


def test_management_nic_delete_protected(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", nic="eth0", state="absent", confirm_delete=True)
    assert r["failed"]
    assert 11 in fake.nics


def test_delete_requires_confirmation(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", nic="eth1", state="absent")
    assert r["failed"]
    assert 12 in fake.nics


def test_unmanaged_nic_only_notes(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", nic="docker0", ip="1.2.3.4/24")
    assert r["failed"]
    assert "only notes" in r["msg"]
    r = run(monkeypatch, fake, server="node1", nic="docker0", notes="ignore")
    assert r["changed"]


def test_new_mac_compared_normalised(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", nic="eth1", new_mac="AA:BB:CC:00:00:02")
    assert not r["changed"]
    r = run(monkeypatch, fake, server="node1", nic="eth1", new_mac="aa:bb:cc:00:00:99")
    assert r["changed"]
    assert fake.writes()[0].body == dict(mac="aa:bb:cc:00:00:99")


def test_ambiguous_name(monkeypatch):
    fake = ServerCluster(
        servers=[server(1, "node1")],
        nics=[nic(11, 1, "eth0", "aa:bb:cc:00:00:01"), nic(12, 1, "eth0", "aa:bb:cc:00:00:02")],
    )
    r = run(monkeypatch, fake, server="node1", nic="eth0", notes="x")
    assert r["failed"]
    assert "use the MAC" in r["msg"]
