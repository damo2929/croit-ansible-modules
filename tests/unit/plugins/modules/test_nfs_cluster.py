# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import nfs_cluster, nfs_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_nfs import NfsCroit, assert_only_gets


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, nfs_cluster.main, check_mode=check_mode, **params)


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


IFACES = [dict(server="node1", nic="eth1"), dict(server="node2", nic="eth1")]


def test_full_idempotency_sequence(monkeypatch):
    fake = NfsCroit()
    spec = dict(name="nfs-prod", servers=["node1", "node2"], implementation="croit_nfs")

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["after"]["servers"] == ["node1", "node2"]
    assert_only_gets(fake)
    assert not fake.clusters

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["cluster"]["description"] == "nfs-prod"
    assert r["cluster"]["implementation"] == "croit_nfs"
    assert r["task"]["state"] == "FINISHED"
    post = [c for c in fake.writes() if c.method == "POST"][0]
    assert post.body == dict(description="nfs-prod", servers=[1, 2], exports=[], implementation="croit_nfs")

    # 3. re-run
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode: add a server and virtual IPs
    update = merged(spec, servers=["node1", "node2", "3"], vips=["10.0.0.250/24"], vip_interfaces=IFACES + [dict(server="node3", nic="eth1", vlan=50)])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["vips"] == []
    assert r["diff"]["after"]["vips"] == ["10.0.0.250/24"]
    assert r["diff"]["after"]["servers"] == ["node1", "node2", "node3"]
    assert dict(server="node3", nic="eth1", vlan=50) in r["diff"]["after"]["vip_interfaces"]
    assert_only_gets(fake)

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    writes = fake.writes()
    assert [(c.method, c.path.rsplit("/", 1)[-1]) for c in writes] == [("PATCH", str(r["cluster"]["serviceId"])), ("PUT", "ha")]
    assert writes[0].body == dict(servers=[1, 2, 3])
    assert writes[1].body == dict(
        vips=["10.0.0.250/24"],
        interfaces=[dict(server=1, nic=11, vlan=None), dict(server=2, nic=21, vlan=None), dict(server=3, nic=31, vlan=350)],
    )

    # 7. update again (VIP spelled differently, interfaces reordered)
    again = merged(update, vips=["10.0.0.250/24 "], vip_interfaces=list(reversed(update["vip_interfaces"])))
    r = run(monkeypatch, fake, **again)
    assert not r["changed"], r.get("diff")
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, name="nfs-prod", state="absent", confirm_delete=True)
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert fake.clusters

    # 9. delete (confirm_delete also confirms croit's gateway warning)
    r = run(monkeypatch, fake, name="nfs-prod", state="absent", confirm_delete=True)
    assert r["changed"]
    assert [c.query.get("ignoreWarning") for c in fake.writes()] == [None, "confirm-gw"]
    assert not fake.clusters

    # 10. delete again
    r = run(monkeypatch, fake, name="nfs-prod", state="absent", confirm_delete=True)
    assert not r["changed"]
    assert_only_gets(fake)


def test_delete_requires_confirmation_even_in_check_mode(monkeypatch):
    fake = NfsCroit()
    fake.add_cluster("nfs", [1, 2])
    for check in (True, False):
        r = run(monkeypatch, fake, check_mode=check, name="nfs", state="absent")
        assert r["failed"] and "confirm_delete" in r["msg"]
        assert_only_gets(fake)
    assert fake.clusters


def test_implementation_switch_needs_confirm_action(monkeypatch):
    fake = NfsCroit()
    sid = fake.add_cluster("nfs", [1, 2])
    r = run(monkeypatch, fake, check_mode=True, name="nfs", implementation="croit_nfs")
    assert r["failed"] and "confirm_action" in r["msg"]
    r = run(monkeypatch, fake, name="nfs", implementation="croit_nfs", confirm_action=True, vip_reconciliation="keep")
    assert r["changed"]
    assert fake.writes()[0].body == dict(implementation="croit_nfs", vipReconciliation="keep")
    assert fake.clusters[sid]["implementation"] == "croit_nfs"
    r = run(monkeypatch, fake, name="nfs", implementation="croit_nfs")
    assert not r["changed"]


def test_vips_refused_for_ganesha(monkeypatch):
    fake = NfsCroit()
    fake.add_cluster("nfs", [1, 2])
    r = run(monkeypatch, fake, name="nfs", vips=["10.0.0.250/24"], vip_interfaces=IFACES)
    assert r["failed"] and "ha_group" in r["msg"]
    r = run(monkeypatch, fake, name="new", servers=["node1"], vips=["10.0.0.250/24"])
    assert r["failed"]
    assert_only_gets(fake)


def test_vips_need_two_members(monkeypatch):
    fake = NfsCroit()
    fake.add_cluster("solo", [1], implementation="croit_nfs")
    r = run(monkeypatch, fake, name="solo", vips=["10.0.0.250/24"], vip_interfaces=[dict(server="node1", nic="eth1")])
    assert r["failed"] and "at least 2 servers" in r["msg"]


def test_empty_vips_removes_ha(monkeypatch):
    fake = NfsCroit()
    sid = fake.add_cluster("nfs", [1, 2], "croit_nfs", vips=["10.0.0.250/24"], interfaces=[dict(server=1, nic=11), dict(server=2, nic=21)])
    r = run(monkeypatch, fake, name="nfs", vips=[])
    assert r["changed"]
    assert [(c.method, c.path.endswith("/ha")) for c in fake.writes()] == [("DELETE", True)]
    assert fake.clusters[sid]["vips"] == []
    r = run(monkeypatch, fake, name="nfs", vips=[])
    assert not r["changed"]


def test_unset_options_leave_cluster_alone(monkeypatch):
    fake = NfsCroit()
    fake.add_cluster("nfs", [1, 2, 3])
    r = run(monkeypatch, fake, name="nfs")
    assert not r["changed"]
    assert_only_gets(fake)


def test_unknown_interface_fails(monkeypatch):
    fake = NfsCroit()
    fake.add_cluster("nfs", [1, 2], "croit_nfs")
    r = run(monkeypatch, fake, name="nfs", vips=["10.0.0.250"], vip_interfaces=[dict(server="node1", nic="eth9")])
    assert r["failed"] and "eth9" in r["msg"]
    r = run(monkeypatch, fake, name="nfs", vips=["10.0.0.250"], vip_interfaces=[dict(server="node1", nic="eth1", vlan=99)])
    assert r["failed"] and "VLAN 99" in r["msg"]


def test_create_requires_servers(monkeypatch):
    r = run(monkeypatch, NfsCroit(), name="nfs")
    assert r["failed"] and "servers is required" in r["msg"]


def test_duplicate_names_fail(monkeypatch):
    fake = NfsCroit()
    fake.add_cluster("nfs", [1])
    fake.add_cluster("nfs", [2])
    r = run(monkeypatch, fake, name="nfs")
    assert r["failed"]


def test_nfs_info(monkeypatch):
    fake = NfsCroit()
    a = fake.add_cluster("a", [1, 2], "croit_nfs", vips=["10.0.0.250/24"])
    fake.add_cluster("b", [3])
    fake.clusters[a]["exports"].append(dict(id=9, serviceId=a, nfsPath="/x", path="/x", access=[], protocols=dict(nfs3=False, nfs4=True)))
    r = run_module(monkeypatch, fake, nfs_info.main, check_mode=True)
    assert not r["changed"]
    assert [c["name"] for c in r["clusters"]] == ["a", "b"]
    assert [e["id"] for e in r["clusters"][0]["exports"]] == [9]
    assert [s["hostname"] for s in r["clusters"][0]["servers"]] == ["node1", "node2"]
    assert "ha" not in r["clusters"][0]
    r = run_module(monkeypatch, fake, nfs_info.main, name="a", ha=True)
    assert len(r["clusters"]) == 1
    assert r["clusters"][0]["ha"]["vips"] == ["10.0.0.250/24"]
    assert_only_gets(fake)
