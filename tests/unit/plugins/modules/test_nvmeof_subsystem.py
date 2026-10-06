# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils import basic

from ansible_collections.croit.ceph.plugins.modules import nvmeof_subsystem
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_nvmeof import NvmeofCluster

NQN = "nqn.2016-06.io.spdk:ds1"
ESXI1 = "nqn.2014-08.org.nvmexpress:uuid:esxi-01"
ESXI2 = "nqn.2014-08.org.nvmexpress:uuid:esxi-02"


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, nvmeof_subsystem.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def cluster():
    fake = NvmeofCluster()
    gid = fake.seed_gateway("gw")
    for pool, image in (("rbd", "vm1"), ("rbd", "vm2")):
        did = fake.next_id()
        fake.disks[did] = dict(id=did, gatewayId=gid, pool=pool, image=image, cluster="croit", size=1, blockSize=512, subsystemNqns=[], hosts=[])
    for nqn in (ESXI1, ESXI2):
        hid = fake.next_id()
        fake.hosts[hid] = dict(id=hid, gatewayId=gid, nqn=nqn, sharedKey=None, subsystems=[], disks=[])
    return fake


def subsystem(fake, nqn=NQN):
    return next((s for s in fake.subsystems.values() if s["nqn"] == nqn), None)


SPEC = dict(
    gateway="gw",
    nqn=NQN,
    max_namespaces=64,
    ana_states=[dict(service="nvme1", state="optimized"), dict(service="nvme2", state="non_optimized")],
    disks=["rbd/vm1"],
    hosts=[ESXI1],
)


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["before"] == {}
    assert r["diff"]["after"]["disks"] == ["rbd/vm1"]
    assert r["diff"]["after"]["ana_states"] == dict(nvme1="optimized", nvme2="non_optimized")
    assert_only_gets(fake)
    assert subsystem(fake) is None

    # 2. create, then settings and attachments
    r = run(monkeypatch, fake, **SPEC)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST", "PATCH", "POST", "POST"]
    sub = subsystem(fake)
    assert sub["maxNamespaces"] == 64
    assert len(sub["disks"]) == 1 and len(sub["hosts"]) == 1
    assert r["subsystem"]["nqn"] == NQN
    assert r["tasks"][-1]["state"] == "FINISHED"

    # 3. re-run
    r = run(monkeypatch, fake, **SPEC)
    assert not r["changed"], r["diff"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode: add a disk and a host, swap the ANA states
    update = merged(
        SPEC,
        disks=["rbd/vm1", "rbd/vm2"],
        hosts=[ESXI1, ESXI2],
        ana_states=[dict(service="nvme2", state="optimized")],
    )
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["after"]["disks"] == ["rbd/vm1", "rbd/vm2"]
    assert r["diff"]["after"]["hosts"] == sorted([ESXI1, ESXI2])
    assert r["diff"]["after"]["ana_states"] == dict(nvme2="optimized")
    assert_only_gets(fake)

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    sub = subsystem(fake)
    assert len(sub["disks"]) == 2 and len(sub["hosts"]) == 2
    assert sub["anaStates"] == [dict(serviceId=fake.service_on("nvme2")["serviceId"], anaState="optimized")]

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, gateway="gw", nqn=NQN, state="absent", confirm_delete=True)
    assert r["changed"] and r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert subsystem(fake) is not None

    # 9. delete
    r = run(monkeypatch, fake, gateway="gw", nqn=NQN, state="absent", confirm_delete=True)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["DELETE"]
    assert subsystem(fake) is None

    # 10. delete again
    r = run(monkeypatch, fake, gateway="gw", nqn=NQN, state="absent", confirm_delete=True)
    assert not r["changed"]
    assert_only_gets(fake)


def test_listed_items_are_additive_without_exclusive(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", nqn=NQN, disks=["rbd/vm1", "rbd/vm2"], hosts=[ESXI1, ESXI2])
    r = run(monkeypatch, fake, gateway="gw", nqn=NQN, disks=["rbd/vm1"], hosts=[ESXI1])
    assert not r["changed"]
    assert_only_gets(fake)


def test_exclusive_detaches_unlisted(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", nqn=NQN, disks=["rbd/vm1", "rbd/vm2"], hosts=[ESXI1, ESXI2])
    r = run(monkeypatch, fake, check_mode=True, gateway="gw", nqn=NQN, hosts=[ESXI1], exclusive=True)
    assert r["changed"] and r["diff"]["after"]["hosts"] == [ESXI1]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, gateway="gw", nqn=NQN, hosts=[ESXI1], exclusive=True)
    assert r["changed"]
    assert [c.path.rsplit("/", 1)[1] for c in fake.writes()] == ["detach-hosts"]
    # disks were not listed, so they stay attached
    assert len(subsystem(fake)["disks"]) == 2
    r = run(monkeypatch, fake, gateway="gw", nqn=NQN, hosts=[ESXI1], exclusive=True)
    assert not r["changed"]


def test_delete_requires_confirmation(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", nqn=NQN)
    for check_mode in (True, False):
        r = run(monkeypatch, fake, check_mode=check_mode, gateway="gw", nqn=NQN, state="absent")
        assert r["failed"] and "confirm_delete" in r["msg"]
        assert_only_gets(fake)


def test_unknown_disk_host_service_fail(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, gateway="gw", nqn=NQN, disks=["rbd/ghost"])
    assert r["failed"] and "nvmeof_disk" in r["msg"] and "rbd/vm1" in r["msg"]
    r = run(monkeypatch, fake, gateway="gw", nqn=NQN, hosts=["nqn.ghost"])
    assert r["failed"] and "nvmeof_host" in r["msg"]
    r = run(monkeypatch, fake, gateway="gw", nqn=NQN, ana_states=[dict(service="ghost", state="optimized")])
    assert r["failed"] and "nvme1" in r["msg"]
    assert_only_gets(fake)


def test_only_one_optimized(monkeypatch):
    fake = cluster()
    r = run(
        monkeypatch,
        fake,
        gateway="gw",
        nqn=NQN,
        ana_states=[dict(service="nvme1", state="optimized"), dict(service="nvme2", state="optimized")],
    )
    assert r["failed"] and "one service" in r["msg"]


def test_unknown_gateway_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, gateway="nope", nqn=NQN)
    assert r["failed"] and "gw (" in r["msg"]


def test_disk_by_id_and_gateway_by_id(monkeypatch):
    fake = cluster()
    gid = next(iter(fake.gateways))
    did = next(d["id"] for d in fake.disks.values() if d["image"] == "vm2")
    r = run(monkeypatch, fake, gateway=str(gid), nqn=NQN, disks=[str(did)])
    assert r["changed"]
    assert subsystem(fake)["disks"] == [did]


def test_no_wait_skips_follow_ups_with_warning(monkeypatch):
    fake = cluster()
    warnings = []
    monkeypatch.setattr(basic.AnsibleModule, "warn", lambda self, msg: warnings.append(msg))
    r = run(monkeypatch, fake, gateway="gw", nqn=NQN, max_namespaces=8, wait=False)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST"]
    assert any("wait=false" in w for w in warnings)
