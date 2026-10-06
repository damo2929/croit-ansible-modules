# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import server_bond
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_servers import ServerCluster, nic, server


def cluster():
    return ServerCluster(
        servers=[server(1, "node1")],
        nics=[
            nic(11, 1, "eth0", "aa:bb:cc:00:00:01", ip="10.0.0.1/24"),
            nic(12, 1, "eth1", "aa:bb:cc:00:00:02"),
            nic(13, 1, "eth2", "aa:bb:cc:00:00:03"),
            nic(14, 1, "eth3", "aa:bb:cc:00:00:04"),
        ],
    )


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, server_bond.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], fake.writes()


def bond_of(fake, name="bond0"):
    return next(n for n in fake.nics.values() if n["name"] == name)


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()
    spec = dict(server="node1", name="bond0", members=["eth2", "eth1"])

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"] == dict(members=["eth1", "eth2"], mode="lacp", primary=None)
    assert_only_gets(fake)

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(name="bond0", nics=[12, 13], activePassive=False, primary=None)
    assert r["bond"]["name"] == "bond0"

    # 3-4. re-run (member order does not matter)
    reordered = dict(spec)
    reordered["members"] = ["eth1", "eth2"]
    assert not run(monkeypatch, fake, **reordered)["changed"]
    assert_only_gets(fake)
    assert not run(monkeypatch, fake, check_mode=True, **spec)["changed"]
    assert_only_gets(fake)

    # 5-7. switch to active/passive with three members and a primary
    update = dict(server="node1", name="bond0", members=["eth1", "eth2", "eth3"], mode="active_passive", primary="eth3")
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["mode"] == "lacp"
    assert r["diff"]["after"] == dict(members=["eth1", "eth2", "eth3"], mode="active_passive", primary="eth3")
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    bond = bond_of(fake)
    assert fake.writes()[0].body == dict(bond=dict(nics=[12, 13, 14], activePassive=True, primary=14))
    assert bond["bondType"] == "active_passive"
    assert not run(monkeypatch, fake, **update)["changed"]
    assert_only_gets(fake)

    # 8-10. delete
    absent = dict(server="node1", name="bond0", state="absent", confirm_delete=True)
    assert run(monkeypatch, fake, check_mode=True, **absent)["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **absent)
    assert r["changed"]
    assert not any(n["name"] == "bond0" for n in fake.nics.values())
    assert fake.nics[12]["bond"] is None
    assert not run(monkeypatch, fake, **absent)["changed"]
    assert_only_gets(fake)


def test_create_requires_members(monkeypatch):
    r = run(monkeypatch, cluster(), server="node1", name="bond0")
    assert r["failed"]
    assert "members is required" in r["msg"]


def test_unknown_member_fails(monkeypatch):
    r = run(monkeypatch, cluster(), server="node1", name="bond0", members=["eth1", "eth9"])
    assert r["failed"]
    assert "eth9" in r["msg"]


def test_primary_needs_active_passive_and_membership(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", name="bond0", members=["eth1", "eth2"], primary="eth1")
    assert r["failed"]
    assert "active_passive" in r["msg"]
    r = run(monkeypatch, fake, server="node1", name="bond0", members=["eth1", "eth2"], mode="active_passive", primary="eth3")
    assert r["failed"]
    assert "not a member" in r["msg"]
    assert_only_gets(fake)


def test_not_a_bond(monkeypatch):
    r = run(monkeypatch, cluster(), server="node1", name="eth1", members=["eth2"])
    assert r["failed"]
    assert "not a bond" in r["msg"]


def test_delete_guards(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, server="node1", name="bond0", members=["eth1", "eth2"])
    r = run(monkeypatch, fake, server="node1", name="bond0", state="absent")
    assert r["failed"]
    bond_of(fake)["ip"] = "10.0.0.1/24"
    r = run(monkeypatch, fake, server="node1", name="bond0", state="absent", confirm_delete=True)
    assert r["failed"]
    assert "management IP" in r["msg"]
    r = run(monkeypatch, fake, server="node1", name="bond0", state="absent", confirm_delete=True, allow_management_ip_change=True)
    assert r["changed"]


def test_only_mode_change(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, server="node1", name="bond0", members=["eth1", "eth2"])
    r = run(monkeypatch, fake, server="node1", name="bond0", mode="active_passive")
    assert r["changed"]
    assert fake.writes()[0].body == dict(bond=dict(activePassive=True))
