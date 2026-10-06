# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.croit.ceph.plugins.modules import osd as osd_module
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_cluster import Cluster, disk, osd_node


def merged(base, **changes):
    result = dict(base)
    result.update(changes)
    return result


def run(monkeypatch, fake, check_mode=False, **params):
    monkeypatch.setattr(osd_module.time, "sleep", lambda s: None)
    return run_module(monkeypatch, fake, osd_module.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def cluster(**kw):
    disks = [
        disk(10, 1, "/dev/sdb", "SER-B", wwn="0x5000c500a1"),
        disk(11, 1, "/dev/sdc", "SER-C"),
        disk(12, 1, "/dev/nvme0n1", "SER-NVME"),
        disk(13, 1, "/dev/sdd", "SER-D", role="osd", osd_id=0),
        disk(14, 1, "/dev/sde", "SER-E", role="old_osd"),
        disk(20, 2, "/dev/sdb", "SER-2B"),
    ]
    return Cluster(disks=disks, osds=[osd_node(0, 1, 13)], **kw)


def test_full_sequence(monkeypatch):
    fake = cluster()
    spec = dict(server="node1", disk="SER-B", device_class="ssd", db_disk="/dev/nvme0n1", confirm_wipe=True)

    # 1. create (check mode)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["before"] == {}
    assert r["diff"]["after"]["disk"] == 10
    assert_only_gets(fake)
    assert fake.disks[10]["osdId"] is None

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    body = [c for c in fake.writes() if c.path == "/disks/create-osds"][0].body
    assert body == dict(osds=[dict(server=1, disk=10, encrypted=False, crushDeviceClass="ssd", dbDisk=12)])
    assert r["osd"]["id"] == 1 and r["osd"]["in"] and r["osd"]["running"]
    assert r["tasks"][0]["state"] == "FINISHED"

    # 3. / 4. re-run, also in check mode
    for check in (False, True):
        r = run(monkeypatch, fake, check_mode=check, **spec)
        assert not r["changed"]
        assert_only_gets(fake)

    # 5. mark out (check mode)
    r = run(monkeypatch, fake, check_mode=True, **merged(spec, **{"in": False}))
    assert r["changed"] and r["diff"]["before"]["in"] and not r["diff"]["after"]["in"]
    assert_only_gets(fake)
    assert fake.osds[1]["reweight"] == 1.0

    # 6. mark out, 7. again
    r = run(monkeypatch, fake, **merged(spec, **{"in": False}))
    assert r["changed"] and [c.path for c in fake.writes()] == ["/crush/osd/1/out"]
    assert not r["osd"]["in"]
    r = run(monkeypatch, fake, **merged(spec, **{"in": False}))
    assert not r["changed"]
    assert_only_gets(fake)

    # 8.-10. stop in check mode, stop, stop again
    r = run(monkeypatch, fake, check_mode=True, osd_id=1, running=False)
    assert r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, osd_id=1, running=False)
    assert r["changed"] and not r["osd"]["running"]
    r = run(monkeypatch, fake, osd_id=1, running=False)
    assert not r["changed"]
    assert_only_gets(fake)


def test_create_requires_confirm_wipe(monkeypatch):
    fake = cluster()
    for check in (True, False):
        r = run(monkeypatch, fake, check_mode=check, server="node1", disk="/dev/sdb")
        assert r["failed"] and "confirm_wipe" in r["msg"]
        assert_only_gets(fake)


def test_existing_osd_needs_no_confirm(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", disk="/dev/sdd")
    assert not r["changed"] and r["osd"]["id"] == 0


@pytest.mark.parametrize("ident", ["/dev/sdb", "SER-B", "ata-SER-B", "0x5000C500A1", "10"])
def test_disk_identifiers(monkeypatch, ident):
    fake = cluster()
    r = run(monkeypatch, fake, check_mode=True, server="node1", disk=ident, confirm_wipe=True)
    assert r["changed"] and r["diff"]["after"]["disk"] == 10


def test_disk_on_other_server_not_found(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node2", disk="SER-B", confirm_wipe=True)
    assert r["failed"] and "not found" in r["msg"] and "SER-2B" in r["msg"]


def test_used_disk_is_refused(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", disk="/dev/sde", confirm_wipe=True)
    assert r["failed"] and "wipe it in croit first" in r["msg"]
    assert_only_gets(fake)


def test_create_only_mismatch_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", disk="/dev/sdd", encrypted=True)
    assert r["failed"] and "cannot be changed in place" in r["msg"]
    r = run(monkeypatch, fake, server="node1", disk="/dev/sdd", device_class="ssd")
    assert r["failed"] and "device_class" in r["msg"]


def test_osd_id_mismatch_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", disk="/dev/sdd", osd_id=5)
    assert r["failed"]


def test_unknown_osd_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, osd_id=42, running=True)
    assert r["failed"] and "does not exist" in r["msg"]


def test_replace_sequence(monkeypatch):
    fake = cluster()
    spec = dict(server="node1", disk="/dev/sdc", replace_osd=0, confirm_wipe=True)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["before"]["disk"] == 13 and r["diff"]["after"]["disk"] == 11
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **merged(spec, confirm_wipe=False))
    assert r["failed"] and "confirm_wipe" in r["msg"]

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    body = [c for c in fake.writes() if c.path == "/disks/replace-osds"][0].body
    assert body == dict(osds=[dict(osd=0, disk=11)])
    assert fake.disks[11]["osdId"] == 0

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)


def test_running_waits_for_async_start(monkeypatch):
    fake = cluster(lag=2)
    fake.osds[0]["status"] = "DOWN"
    r = run(monkeypatch, fake, osd_id=0, running=True)
    assert r["changed"] and r["osd"]["running"]
    crush_reads = [c for c in fake.calls if c.path == "/crush"]
    assert len(crush_reads) >= 3


def test_running_timeout(monkeypatch):
    fake = cluster(lag=1000)
    clock = [0.0]

    def fake_time():
        clock[0] += 1
        return clock[0]

    monkeypatch.setattr(osd_module.time, "time", fake_time)
    r = run(monkeypatch, fake, osd_id=0, running=False, wait_timeout=5)
    assert r["failed"] and "Timed out" in r["msg"]


def test_no_wait_does_not_poll(monkeypatch):
    fake = cluster(lag=1000)
    r = run(monkeypatch, fake, osd_id=0, running=False, wait=False)
    assert r["changed"]
    assert len([c for c in fake.calls if c.path == "/crush"]) == 2
