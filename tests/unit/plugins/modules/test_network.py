# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

import pytest

from ansible_collections.croit.ceph.plugins.modules import network as network_module
from ansible_collections.croit.ceph.plugins.modules import network_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module


class NetworkCluster(FakeCroit):
    """Fake croit holding networks; PUT replaces the row like croit does."""

    def __init__(self, networks=None):
        super(NetworkCluster, self).__init__()
        self.networks = dict((n["id"], n) for n in (networks or []))
        self.next_id = 20
        self.route("GET", "/networks", lambda call: (200, [copy.deepcopy(n) for n in self.networks.values()]))
        self.route("POST", "/networks", self.create)
        self.route("PUT", r"/networks/(?P<nid>\d+)", self.replace)
        self.route("DELETE", r"/networks/(?P<nid>\d+)", self.delete)

    @staticmethod
    def row(nid, body, old_type=None):
        return dict(
            id=nid,
            ip=body["ip"],
            netmask=body["netmask"],
            type=body.get("type") or old_type or "other",
            description=body.get("description") or "",
            gateway=body.get("gateway"),
            mtu=body.get("mtu"),
            poolStart=body.get("poolStart"),
            poolEnd=body.get("poolEnd"),
        )

    def create(self, call):
        self.next_id += 1
        self.networks[self.next_id] = self.row(self.next_id, call.body)
        return 200, copy.deepcopy(self.networks[self.next_id])

    def replace(self, call, nid):
        nid = int(nid)
        self.networks[nid] = self.row(nid, call.body, self.networks[nid]["type"])
        return 204, None

    def delete(self, call, nid):
        del self.networks[int(nid)]
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, network_module.main, check_mode=check_mode, **params)


def only_gets(fake):
    assert fake.writes() == [], fake.writes()


def existing(**kw):
    row = dict(
        id=5,
        ip="10.10.0.0",
        netmask=24,
        type="ceph_public",
        description="",
        gateway=None,
        mtu=None,
        poolStart=None,
        poolEnd=None,
    )
    row.update(kw)
    return row


def test_full_idempotency_sequence(monkeypatch):
    fake = NetworkCluster([existing()])
    spec = dict(cidr="10.20.0.0/24", type="croit", gateway="10.20.0.1", mtu=9000)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["before"] == {}
    assert r["diff"]["after"]["mtu"] == 9000
    only_gets(fake)
    assert len(fake.networks) == 1

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["network"]["type"] == "croit"
    body = fake.writes()[0].body
    assert body["ip"] == "10.20.0.0" and body["netmask"] == 24 and body["mtu"] == 9000

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    only_gets(fake)

    update = dict(spec)
    update.update(dhcp_pool_start="10.20.0.100", dhcp_pool_end="10.20.0.200")
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["dhcp_pool_start"] is None
    assert r["diff"]["after"]["dhcp_pool_end"] == "10.20.0.200"
    only_gets(fake)

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    put = fake.writes()[0]
    assert put.method == "PUT"
    # The full config is sent: settings not in this task are kept.
    assert put.body["type"] == "croit" and put.body["gateway"] == "10.20.0.1" and put.body["mtu"] == 9000
    assert r["network"]["poolStart"] == "10.20.0.100"

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, cidr="10.20.0.0/24", state="absent")
    assert r["changed"]
    only_gets(fake)

    r = run(monkeypatch, fake, cidr="10.20.0.0/24", state="absent")
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["DELETE"]
    assert len(fake.networks) == 1

    r = run(monkeypatch, fake, cidr="10.20.0.0/24", state="absent")
    assert not r["changed"]
    only_gets(fake)


def test_host_address_names_the_same_network(monkeypatch):
    fake = NetworkCluster([existing(ip="10.10.0.7")])
    r = run(monkeypatch, fake, cidr="10.10.0.1/24", type="ceph_public")
    assert not r["changed"]


def test_update_keeps_stored_address(monkeypatch):
    fake = NetworkCluster([existing(ip="10.10.0.7")])
    run(monkeypatch, fake, cidr="10.10.0.0/24", description="x")
    assert fake.writes()[0].body["ip"] == "10.10.0.7"


def test_default_mtu_and_empty_description(monkeypatch):
    fake = NetworkCluster([existing()])
    r = run(monkeypatch, fake, cidr="10.10.0.0/24", mtu=1500, description="")
    assert not r["changed"]


def test_ipv6_canonicalised(monkeypatch):
    fake = NetworkCluster([existing(ip="fd00:0:0:0::", netmask=64, gateway="fd00::0:1")])
    r = run(monkeypatch, fake, cidr="fd00::/64", gateway="fd00::1")
    assert not r["changed"]


def test_empty_gateway_removes_it(monkeypatch):
    fake = NetworkCluster([existing(gateway="10.10.0.1")])
    r = run(monkeypatch, fake, cidr="10.10.0.0/24", gateway="")
    assert r["changed"]
    assert fake.writes()[0].body["gateway"] is None


def test_unset_options_left_alone(monkeypatch):
    fake = NetworkCluster([existing(gateway="10.10.0.1", mtu=9000)])
    r = run(monkeypatch, fake, cidr="10.10.0.0/24")
    assert not r["changed"]


@pytest.mark.parametrize(
    "params,msg",
    [
        (dict(gateway="10.99.0.1"), "not inside"),
        (dict(dhcp_pool_start="10.10.0.10", dhcp_pool_end=""), "both"),
        (dict(gateway="nope"), "gateway"),
        (dict(mtu=0), "mtu"),
    ],
)
def test_validation(monkeypatch, params, msg):
    fake = NetworkCluster([existing()])
    r = run(monkeypatch, fake, cidr="10.10.0.0/24", **params)
    assert r["failed"] and msg in r["msg"]
    only_gets(fake)


@pytest.mark.parametrize("cidr", ["10.10.0.0", "not-a-net"])
def test_bad_cidr(monkeypatch, cidr):
    r = run(monkeypatch, NetworkCluster(), cidr=cidr)
    assert r["failed"]


def test_pool_requires_both(monkeypatch):
    r = run(monkeypatch, NetworkCluster(), cidr="10.0.0.0/24", dhcp_pool_start="10.0.0.5")
    assert r["failed"]


def test_croit_refusal_surfaces(monkeypatch):
    fake = NetworkCluster()
    fake.routes = [rt for rt in fake.routes if rt[0] != "POST"]
    fake.reply("POST", "/networks", 400, dict(code=400, message="overlaps network 10.0.0.0/16"))
    r = run(monkeypatch, fake, cidr="10.0.1.0/24")
    assert r["failed"] and "overlaps" in r["msg"]


def test_network_info_filters(monkeypatch):
    fake = NetworkCluster([existing(), existing(id=6, ip="192.168.0.0", netmask=16, type="croit")])
    r = run_module(monkeypatch, fake, network_info.main, check_mode=True)
    assert [n["cidr"] for n in r["networks"]] == ["10.10.0.0/24", "192.168.0.0/16"]
    r = run_module(monkeypatch, fake, network_info.main, type="croit")
    assert [n["id"] for n in r["networks"]] == [6]
    r = run_module(monkeypatch, fake, network_info.main, cidr="10.10.0.9/24")
    assert [n["id"] for n in r["networks"]] == [5]
    assert not r["changed"]
    only_gets(fake)
