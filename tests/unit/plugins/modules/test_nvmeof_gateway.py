# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

from ansible_collections.croit.ceph.plugins.modules import nvmeof_gateway
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_nvmeof import NvmeofCluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, nvmeof_gateway.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


SPEC = dict(
    name="nvme-prod",
    description="datastores",
    transport_defaults=[dict(type="tcp", max_io_qpairs_per_ctrlr=127)],
    services=[dict(server="nvme1", nr_hugepages=2048), dict(server="nvme2", nr_hugepages=2048, ana_state="non_optimized")],
)


def gateway(fake, name="nvme-prod"):
    return next((g for g in fake.gateways.values() if g["name"] == name), None)


def test_full_idempotency_sequence(monkeypatch):
    fake = NvmeofCluster()

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["after"]["gateway"]["transport_defaults"]["tcp"]["max_io_qpairs_per_ctrlr"] == 127
    assert set(r["diff"]["after"]["services"]) == set(["nvme1", "nvme2"])
    assert_only_gets(fake)
    assert not fake.gateways

    # 2. create: one POST with both services, then the ana_state follow-up
    r = run(monkeypatch, fake, **SPEC)
    assert r["changed"]
    posts = [c for c in fake.writes() if c.method == "POST"]
    assert len(posts) == 1 and len(posts[0].body["services"]) == 2
    assert posts[0].body["transportDefaults"] == [dict(type="TCP", maxIoQpairsPerCtrlr=127)]
    assert "anaState" not in posts[0].body["services"][1]
    assert r["gateway"]["name"] == "nvme-prod"
    states = dict((s["serverHostname"], s["anaState"]) for s in r["services"])
    assert states == dict(nvme1="optimized", nvme2="non_optimized")
    assert r["task"]["state"] == "FINISHED"

    # 3. re-run: no change, no writes
    r = run(monkeypatch, fake, **SPEC)
    assert not r["changed"], r["diff"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode
    update = merged(SPEC, force_secure=True, services=[dict(server="nvme1", nr_hugepages=4096, description="primary")])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["gateway"]["force_secure"] is False
    assert r["diff"]["after"]["gateway"]["force_secure"] is True
    assert r["diff"]["after"]["services"]["nvme1"] == dict(nr_hugepages=4096, description="primary")
    assert_only_gets(fake)
    assert gateway(fake)["forceSecure"] is False

    # 6. update: only the changed fields are sent
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    patches = [c for c in fake.writes() if c.method == "PATCH"]
    assert patches[0].body == dict(forceSecure=True)
    assert patches[1].body == dict(nrHugepages=4096, description="primary")
    assert len(patches) == 2

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, name="nvme-prod", state="absent", confirm_delete=True)
    assert r["changed"]
    assert r["diff"]["after"]["gateway"] == {}
    assert_only_gets(fake)
    assert gateway(fake) is not None

    # 9. delete
    r = run(monkeypatch, fake, name="nvme-prod", state="absent", confirm_delete=True)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["DELETE"]
    assert gateway(fake) is None

    # 10. delete again
    r = run(monkeypatch, fake, name="nvme-prod", state="absent", confirm_delete=True)
    assert not r["changed"]
    assert_only_gets(fake)


def test_delete_requires_confirmation(monkeypatch):
    fake = NvmeofCluster()
    run(monkeypatch, fake, name="gw")
    for check_mode in (True, False):
        r = run(monkeypatch, fake, check_mode=check_mode, name="gw", state="absent")
        assert r["failed"] and "confirm_delete" in r["msg"]
        assert_only_gets(fake)
    assert gateway(fake, "gw") is not None


def test_delete_confirms_croit_warning(monkeypatch):
    fake = NvmeofCluster()
    run(monkeypatch, fake, name="gw")
    gid = gateway(fake, "gw")["gatewayId"]
    original = fake.delete_gateway

    def warn_first(call, gid):
        if call.query.get("ignoreWarning") != "tok":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="tok", warningText="hosts are connected"))
        return original(call, gid)

    fake.routes.insert(0, ("DELETE", re.compile(r"^/gateways/nvmeof/(?P<gid>%d)$" % gid), warn_first))
    r = run(monkeypatch, fake, name="gw", state="absent", confirm_delete=True)
    assert r["changed"] and not r.get("failed")
    assert gateway(fake, "gw") is None


def test_unset_options_left_alone(monkeypatch):
    fake = NvmeofCluster()
    run(monkeypatch, fake, **SPEC)
    r = run(monkeypatch, fake, name="nvme-prod")
    assert not r["changed"]
    assert_only_gets(fake)


def test_transport_defaults_are_a_complete_list(monkeypatch):
    fake = NvmeofCluster()
    run(monkeypatch, fake, **SPEC)
    r = run(monkeypatch, fake, name="nvme-prod", transport_defaults=[])
    assert r["changed"]
    assert fake.writes()[0].body == dict(transportDefaults=[])
    assert gateway(fake)["transportDefaults"] == []


def test_duplicate_fabric_fails(monkeypatch):
    fake = NvmeofCluster()
    r = run(monkeypatch, fake, name="gw", transport_defaults=[dict(type="tcp"), dict(type="tcp", io_unit_size=8192)])
    assert r["failed"] and "more than once" in r["msg"]
    assert_only_gets(fake)


def test_new_service_on_existing_gateway(monkeypatch):
    fake = NvmeofCluster()
    run(monkeypatch, fake, name="gw", services=[dict(server="nvme1")])
    r = run(monkeypatch, fake, name="gw", services=[dict(server="nvme2", ana_state="inaccessible")])
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST", "PATCH"]
    svc = next(s for s in fake.services.values() if s["serverHostname"] == "nvme2")
    assert svc["anaState"] == "inaccessible"
    r = run(monkeypatch, fake, name="gw", services=[dict(server="nvme2", ana_state="inaccessible")])
    assert not r["changed"]


def test_unknown_server_fails(monkeypatch):
    fake = NvmeofCluster()
    r = run(monkeypatch, fake, name="gw", services=[dict(server="ghost")])
    assert r["failed"] and "nvme1 (1)" in r["msg"]


def test_duplicate_gateway_names_fail(monkeypatch):
    fake = NvmeofCluster()
    fake.gateways[90] = dict(gatewayId=90, name="dup", description="", forceSecure=False, transportDefaults=[], hints=[])
    fake.gateways[91] = dict(gatewayId=91, name="dup", description="", forceSecure=False, transportDefaults=[], hints=[])
    r = run(monkeypatch, fake, name="dup")
    assert r["failed"] and "numeric id" in r["msg"]


def test_ceph_clusters(monkeypatch):
    fake = NvmeofCluster()
    clusters = [dict(name="ceph-nvmeof", client_id="nvmeof")]
    r = run(monkeypatch, fake, check_mode=True, name="gw", ceph_clusters=clusters)
    assert r["changed"]
    assert r["diff"]["after"]["ceph_clusters"] == {"ceph-nvmeof": "nvmeof"}
    assert_only_gets(fake)

    r = run(monkeypatch, fake, name="gw", ceph_clusters=clusters)
    assert [c.path for c in fake.writes()][0] == "/gateways/nvmeof/ceph-clusters"
    assert fake.ceph_clusters["ceph-nvmeof"]["clientId"] == "nvmeof"

    r = run(monkeypatch, fake, name="gw", ceph_clusters=clusters)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, name="gw", ceph_clusters=[dict(name="ceph-nvmeof", client_id="other")])
    assert r["failed"] and "cannot be changed" in r["msg"]

    r = run(monkeypatch, fake, name="gw", ceph_clusters=[dict(name="ceph-nvmeof", state="absent")])
    assert r["changed"]
    assert "ceph-nvmeof" not in fake.ceph_clusters
    r = run(monkeypatch, fake, name="gw", ceph_clusters=[dict(name="ceph-nvmeof", state="absent")])
    assert not r["changed"]


def test_reconfigure_is_a_one_shot_action(monkeypatch):
    fake = NvmeofCluster()
    run(monkeypatch, fake, name="gw")
    r = run(monkeypatch, fake, check_mode=True, name="gw", reconfigure=True)
    assert r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, name="gw", reconfigure=True, reconfigure_from_scratch=True)
    assert r["changed"]
    call = fake.writes()[0]
    assert call.path.endswith("/reconfigure") and call.query == dict(fromScratch="true")
    r = run(monkeypatch, fake, name="gw", reconfigure=True, state="absent", confirm_delete=True)
    assert r["failed"]


def test_paginated_lists_are_unwrapped(monkeypatch):
    fake = NvmeofCluster()
    run(monkeypatch, fake, name="gw")
    r = run(monkeypatch, fake, name="gw")
    assert r["gateway"]["name"] == "gw"
