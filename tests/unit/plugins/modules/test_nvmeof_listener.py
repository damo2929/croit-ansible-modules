# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import nvmeof_listener
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_nvmeof import NvmeofCluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, nvmeof_listener.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def listeners(fake, hostname="nvme1"):
    return fake.service_on(hostname)["listeners"]


SPEC = dict(gateway="gw", service="nvme1", nic="eth0", vlan=50, port=4420)


def test_full_idempotency_sequence(monkeypatch):
    fake = NvmeofCluster()
    fake.seed_gateway("gw")

    # 1. add in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert r["changed"] and r["diff"]["after"] == dict(nic="eth0", vlan=50, type="tcp", port=4420, secure=False)
    assert_only_gets(fake)
    assert listeners(fake) == []

    # 2. add
    r = run(monkeypatch, fake, **SPEC)
    assert r["changed"]
    assert fake.writes()[0].body == dict(type="TCP", nicId=11, port=4420, vlanId=111)
    assert r["listener"]["vlan"] == 50

    # 3. again
    r = run(monkeypatch, fake, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. again in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. enable TLS in check mode
    update = merged(SPEC, secure=True)
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"] and r["diff"]["before"]["secure"] is False and r["diff"]["after"]["secure"] is True
    assert_only_gets(fake)

    # 6. enable TLS
    r = run(monkeypatch, fake, **update)
    assert r["changed"] and [c.method for c in fake.writes()] == ["PATCH"]
    assert fake.writes()[0].body == dict(secure=True)
    assert listeners(fake)[0]["secure"] is True

    # 7. again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. remove in check mode
    r = run(monkeypatch, fake, check_mode=True, state="absent", **SPEC)
    assert r["changed"]
    assert_only_gets(fake)
    assert len(listeners(fake)) == 1

    # 9. remove
    r = run(monkeypatch, fake, state="absent", **SPEC)
    assert r["changed"] and [c.method for c in fake.writes()] == ["DELETE"]
    assert listeners(fake) == []

    # 10. remove again
    r = run(monkeypatch, fake, state="absent", **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)


def test_port_is_part_of_the_identity(monkeypatch):
    fake = NvmeofCluster()
    fake.seed_gateway("gw")
    run(monkeypatch, fake, **SPEC)
    r = run(monkeypatch, fake, **merged(SPEC, port=4421))
    assert r["changed"] and [c.method for c in fake.writes()] == ["POST"]
    assert sorted(lst["port"] for lst in listeners(fake)) == [4420, 4421]


def test_nic_by_mac_and_service_by_name(monkeypatch):
    fake = NvmeofCluster()
    fake.seed_gateway("gw")
    name = fake.service_on("nvme2")["name"]
    r = run(monkeypatch, fake, gateway="gw", service=name, nic="AA-BB-CC-00-02-00", port=4420, type="rdma")
    assert r["changed"]
    assert fake.writes()[0].body == dict(type="RDMA", nicId=21, port=4420)


def test_unknown_vlan_nic_service_fail(monkeypatch):
    fake = NvmeofCluster()
    fake.seed_gateway("gw")
    r = run(monkeypatch, fake, **merged(SPEC, vlan=99))
    assert r["failed"] and "no VLAN 99" in r["msg"]
    r = run(monkeypatch, fake, **merged(SPEC, nic="eth9"))
    assert r["failed"] and "eth0" in r["msg"]
    r = run(monkeypatch, fake, **merged(SPEC, service="ghost"))
    assert r["failed"] and "nvme1" in r["msg"]
    assert_only_gets(fake)
