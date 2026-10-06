# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import service as service_module
from ansible_collections.croit.ceph.plugins.modules import service_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_cluster import Cluster, disk, osd_node, service


def merged(base, **changes):
    result = dict(base)
    result.update(changes)
    return result


def run(monkeypatch, fake, check_mode=False, **params):
    monkeypatch.setattr(service_module.time, "sleep", lambda s: None)
    return run_module(monkeypatch, fake, service_module.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def cluster(**kw):
    return Cluster(
        disks=[disk(30, 2, "/dev/sda", "MON-DISK")],
        osds=[osd_node(0, 1, 13), osd_node(1, 1, 14), osd_node(2, 2, 20), osd_node(3, 2, 21, status="DESTROYED")],
        services=[
            service(1, "mon", 1),
            service(2, "mgr", 1),
            service(3, "radosgw", 1, multi=[1, 2]),
            service(4, "mds", 1),
        ],
        **kw
    )


def test_mon_full_sequence(monkeypatch):
    fake = cluster()
    spec = dict(server="node2", type="mon", mon_disk="MON-DISK", mon_ip="10.0.0.2", state="started")

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["before"] == {} and r["diff"]["after"]["server"] == 2
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    create = [c for c in fake.writes() if c.path == "/servers/2/services/mon"][0]
    assert create.body == dict(ip="10.0.0.2", diskId=30)
    assert r["service"]["type"] == "mon" and r["service"]["running"]
    assert r["task"]["state"] == "FINISHED"

    for check in (False, True):
        r = run(monkeypatch, fake, check_mode=check, **spec)
        assert not r["changed"]
        assert_only_gets(fake)

    stop = merged(spec, state="stopped")
    r = run(monkeypatch, fake, check_mode=True, **stop)
    assert r["changed"] and r["diff"]["after"]["running"] is False
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **stop)
    assert r["changed"] and not r["service"]["running"]
    r = run(monkeypatch, fake, **stop)
    assert not r["changed"]
    assert_only_gets(fake)

    absent = dict(server="node2", type="mon", state="absent", confirm_delete=True)
    r = run(monkeypatch, fake, check_mode=True, **absent)
    assert r["changed"] and r["diff"]["after"] == {}
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **absent)
    assert r["changed"] and r["service"] == {}
    r = run(monkeypatch, fake, **absent)
    assert not r["changed"]
    assert_only_gets(fake)


def test_mon_create_needs_disk_and_ip(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node2", type="mon", mon_ip="10.0.0.2")
    assert r["failed"] and "mon_disk" in r["msg"]
    assert_only_gets(fake)


def test_mds_and_rbd_mirror_create(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node2", type="mds", mds_volume="cephfs")
    assert r["changed"]
    assert [c.body for c in fake.writes()] == [dict(volume="cephfs")]
    r = run(monkeypatch, fake, server="node2", type="rbd_mirror")
    assert r["changed"]
    assert fake.writes()[0].path == "/servers/2/services/rbd-mirror"
    assert fake.writes()[0].body is None


def test_non_creatable_type_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node2", type="mgr")
    assert r["failed"] and "can only create" in r["msg"]


def test_delete_mon_and_mds_need_confirm(monkeypatch):
    fake = cluster()
    fake.services[5] = service(5, "mon", 2)
    for stype in ("mon", "mds"):
        r = run(monkeypatch, fake, server="node1", type=stype, state="absent")
        assert r["failed"] and "confirm_delete" in r["msg"]
        assert_only_gets(fake)


def test_last_mon_refusal_is_surfaced(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", type="mon", state="absent", confirm_delete=True)
    assert r["failed"] and "last monitor" in r["msg"]


def test_last_mds_warning_needs_ignore_warnings(monkeypatch):
    fake = cluster()
    original = fake.delete_service

    def guarded(call, svc):
        if int(svc) == 4 and call.query.get("ignoreWarning") != "tok":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="tok", warningText="last MDS"))
        return original(call, svc)

    fake.routes = [r for r in fake.routes if r[0] != "DELETE"]
    fake.route("DELETE", r"/services/(?P<svc>\d+)", guarded)
    r = run(monkeypatch, fake, server="node1", type="mds", state="absent", confirm_delete=True)
    assert r["failed"] and r["warning"] == "last MDS"
    assert 4 in fake.services
    r = run(monkeypatch, fake, server="node1", type="mds", state="absent", confirm_delete=True, ignore_warnings=True)
    assert r["changed"] and 4 not in fake.services


def test_multi_server_gateway_acts_on_one_node(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node2", type="radosgw", state="stopped")
    assert r["changed"]
    assert fake.writes()[0].query == dict(server="2")

    r = run(monkeypatch, fake, check_mode=True, server="node2", type="radosgw", state="absent")
    assert r["diff"]["after"]["servers"] == [1]
    r = run(monkeypatch, fake, server="node2", type="radosgw", state="absent")
    assert r["changed"] and fake.services[3]["multiServer"] == [1]
    r = run(monkeypatch, fake, server="node2", type="radosgw", state="absent")
    assert not r["changed"]


def test_ambiguous_service_needs_id(monkeypatch):
    fake = cluster()
    fake.services[6] = service(6, "mds", 1)
    r = run(monkeypatch, fake, server="node1", type="mds", state="started")
    assert r["failed"] and "service_id" in r["msg"]
    r = run(monkeypatch, fake, service_id=6, state="started")
    assert not r["changed"]


def test_start_waits_for_croitd(monkeypatch):
    fake = cluster(lag=2)
    fake.services[2]["running"] = False
    r = run(monkeypatch, fake, server="node1", type="mgr", state="started")
    assert r["changed"] and r["service"]["running"]


def test_restart_is_one_shot(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, check_mode=True, server="node1", type="mgr", state="restarted")
    assert r["changed"] and r["services"] == [dict(id=2, server=None, osd=False)]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, server="node1", type="mgr", state="restarted")
    assert r["changed"] and fake.restarted == [("restart", [dict(id=2)])]


def test_rolling_restart_osds_of_one_host(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node2", type="osd", state="rolling_restarted")
    assert r["changed"] and r["task"]["state"] == "FINISHED"
    # destroyed osd.3 is skipped
    assert fake.restarted == [("rolling", [dict(id=2, isOsd=True)])]


def test_rolling_restart_all_gateways(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, type="radosgw", state="rolling_restarted")
    assert fake.restarted == [("rolling", [dict(id=3)])]


def test_osd_type_only_for_restarts(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", type="osd", state="started")
    assert r["failed"] and "croit.ceph.osd" in r["msg"]


def test_restart_nothing_matches(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, type="smb", state="restarted")
    assert r["failed"] and "No services match" in r["msg"]


def test_unknown_server_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="ghost", type="mon")
    assert r["failed"] and "node1 (1)" in r["msg"]


def test_service_info_filters(monkeypatch):
    fake = cluster()
    r = run_module(monkeypatch, fake, service_info.main, check_mode=True, server="node2")
    assert [s["id"] for s in r["services"]] == [3]
    r = run_module(monkeypatch, fake, service_info.main, type="mon")
    assert [s["id"] for s in r["services"]] == [1]
    r = run_module(monkeypatch, fake, service_info.main, service_id=4)
    assert [s["type"] for s in r["services"]] == ["mds"]
    assert not r["changed"]
    assert_only_gets(fake)
