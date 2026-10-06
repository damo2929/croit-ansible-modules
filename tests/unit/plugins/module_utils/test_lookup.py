# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.croit.ceph.plugins.module_utils.lookup import (
    find_nic,
    find_one,
    find_server,
    normalise_mac,
    require_disk,
    require_server,
    resolve_interface,
)
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

SERVERS = [dict(id=1, hostname="node1"), dict(id=2, hostname="node2"), dict(id=3, hostname="1")]


def fake():
    f = FakeCroit()
    f.reply("GET", "/servers", 200, SERVERS)
    return f


def _run(monkeypatch, body):
    def main():
        m = CroitModule(dict())
        m.exit(**body(m))

    return run_module(monkeypatch, fake(), main)


def test_find_one_duplicates():
    with pytest.raises(ValueError):
        find_one([dict(a=1), dict(a=1)], "thing", "a", 1)
    assert find_one([dict(a=1)], "thing", "a", 2) is None


@pytest.mark.parametrize("server,expected", [("node2", 2), (2, 2), ("2", 2), ("1", 3), ("nope", None)])
def test_find_server(monkeypatch, server, expected):
    r = _run(monkeypatch, lambda m: dict(found=(find_server(m, server) or {}).get("id")))
    assert r["found"] == expected


def test_require_server_fails_with_known_list(monkeypatch):
    r = _run(monkeypatch, lambda m: dict(s=require_server(m, "ghost")))
    assert r["failed"]
    assert "node1 (1)" in r["msg"]


DISKS = [
    dict(id=10, path="/dev/sda", serial="SER-A", wwn="0x5000AA"),
    dict(id=11, path="/dev/sdb", serial="SER-B", serials=dict(by_id="ALT-B"), wwns=dict(w="0x5000BB")),
]
NICS = [
    dict(id=1, name="eth0", linuxName="enp1s0", mac="AA:BB:CC:DD:EE:01"),
    dict(id=2, name="eth1", linuxName="enp2s0", mac="aa-bb-cc-dd-ee-02"),
]


@pytest.mark.parametrize("value,expected", [("/dev/sdb", 11), ("SER-A", 10), ("ALT-B", 11), ("0x5000aa", 10), ("0X5000BB", 11), ("10", 10)])
def test_require_disk(monkeypatch, value, expected):
    r = _run(monkeypatch, lambda m: dict(id=require_disk(m, DISKS, value)["id"]))
    assert r["id"] == expected


def test_require_disk_missing_lists_disks(monkeypatch):
    r = _run(monkeypatch, lambda m: dict(d=require_disk(m, DISKS, "/dev/sdz", what="mon_disk")))
    assert r["failed"]
    assert "mon_disk" in r["msg"] and "SER-B" in r["msg"]


def test_normalise_mac():
    assert normalise_mac("AA:BB:CC:DD:EE:01") == normalise_mac("aa-bb-cc-dd-ee-01") == "aabbccddee01"
    assert normalise_mac(None) == ""


@pytest.mark.parametrize("ident,expected", [("eth0", 1), ("enp2s0", 2), ("aabb.ccdd.ee02", 2), ("eth9", None)])
def test_find_nic(monkeypatch, ident, expected):
    r = _run(monkeypatch, lambda m: dict(id=(find_nic(m, NICS, ident) or {}).get("id")))
    assert r["id"] == expected


VNICS = [dict(id=7, name="eth0", linuxName="enp1s0", mac="aa:bb:cc:dd:ee:07", vlans=[dict(id=70, vlan=100)])]


@pytest.mark.parametrize("nic,vlan,expected", [("eth0", None, (2, 7, None)), ("7", 100, (2, 7, 70)), ("aa-bb-cc-dd-ee-07", None, (2, 7, None))])
def test_resolve_interface(monkeypatch, nic, vlan, expected):
    def body(m):
        server, found, vlan_id = resolve_interface(m, "node2", nic, vlan, nics=VNICS)
        return dict(r=[server["id"], found["id"], vlan_id])

    assert tuple(_run(monkeypatch, body)["r"]) == expected


@pytest.mark.parametrize("nic,vlan,message", [("eth9", None, "no interface"), ("eth0", 200, "no VLAN 200")])
def test_resolve_interface_errors(monkeypatch, nic, vlan, message):
    r = _run(monkeypatch, lambda m: dict(r=resolve_interface(m, "node2", nic, vlan, nics=VNICS)))
    assert r["failed"] and message in r["msg"]
