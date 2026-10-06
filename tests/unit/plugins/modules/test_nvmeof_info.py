# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import nvmeof_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_nvmeof import NvmeofCluster

KEY = "DHHC-1:00:c2VjcmV0:"


def cluster():
    fake = NvmeofCluster()
    g1 = fake.seed_gateway("gw1", server_ids=(1,))
    g2 = fake.seed_gateway("gw2", server_ids=(2,))
    fake.seed_subsystem(g1, "nqn.a")
    fake.seed_subsystem(g2, "nqn.b")
    fake.hosts[90] = dict(id=90, gatewayId=g1, nqn="nqn.host", sharedKey=KEY, subsystems=[], disks=[])
    fake.ceph_clusters["croit"] = dict(name="croit", clientId="admin")
    return fake


def test_everything_is_read_only(monkeypatch):
    fake = cluster()
    r = run_module(monkeypatch, fake, nvmeof_info.main, check_mode=True)
    assert not r["changed"]
    assert fake.writes() == []
    assert len(r["gateways"]) == 2 and len(r["subsystems"]) == 2
    assert set(r) >= set(["gateways", "services", "listeners", "subsystems", "disks", "hosts", "ceph_clusters"])


def test_filter_by_gateway(monkeypatch):
    fake = cluster()
    r = run_module(monkeypatch, fake, nvmeof_info.main, gateway="gw2", gather=["subsystems", "services", "ceph_clusters"])
    assert [s["nqn"] for s in r["subsystems"]] == ["nqn.b"]
    assert [s["serverHostname"] for s in r["services"]] == ["nvme2"]
    assert len(r["ceph_clusters"]) == 1
    assert "gateways" not in r


def test_keys_masked_unless_asked(monkeypatch):
    fake = cluster()
    r = run_module(monkeypatch, fake, nvmeof_info.main, gather=["hosts"])
    assert r["hosts"][0]["sharedKey"] == "********"
    assert KEY not in repr(r)
    r = run_module(monkeypatch, fake, nvmeof_info.main, gather=["hosts"], show_secrets=True)
    assert r["hosts"][0]["sharedKey"] == KEY


def test_unknown_gateway_fails(monkeypatch):
    fake = cluster()
    r = run_module(monkeypatch, fake, nvmeof_info.main, gateway="nope")
    assert r["failed"] and "gw1 (" in r["msg"]
