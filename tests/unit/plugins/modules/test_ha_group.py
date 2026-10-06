# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import re

from ansible_collections.croit.ceph.plugins.modules import ha_group
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

SERVERS = [dict(id=1, hostname="gw1"), dict(id=2, hostname="gw2"), dict(id=3, hostname="rgw1"), dict(id=4, hostname="rgw2")]


def nics_of(server_id):
    base = server_id * 10
    return [
        dict(id=base + 1, server=server_id, name="eth0", linuxName="eth0", vlans=[]),
        dict(id=base + 2, server=server_id, name="bond0", linuxName="bond0", vlans=[dict(id=base + 50, nic=base + 2, vlan=50)]),
    ]


class HaCluster(FakeCroit):
    def __init__(self, groups=None):
        super(HaCluster, self).__init__()
        self.groups = dict((g["id"], g) for g in (groups or []))
        self.next_id = 100
        self.serve_tasks()
        self.reply("GET", "/servers", 200, SERVERS)
        self.route("GET", r"/servers/(?P<sid>\d+)/nics", lambda call, sid: (200, nics_of(int(sid))))
        self.route("GET", "/servers/ha-groups", lambda call: (200, [copy.deepcopy(g) for g in self.groups.values()]))
        self.route("POST", "/servers/ha-groups", self.create)
        self.route("PUT", r"/servers/ha-groups/(?P<gid>\d+)", self.put)
        self.route("DELETE", r"/servers/ha-groups/(?P<gid>\d+)", self.delete)

    def stored(self, body, gid):
        group = dict(
            id=gid,
            description=body["description"],
            service=body["service"],
            backend=body.get("backend", "keepalived"),
            vips=list(body.get("vips") or []),
            virtualIp=(body.get("vips") or [""])[0],
            servers=[dict(server=m["server"], nic=m["nic"], vlan=m.get("vlan"), runsService=True) for m in body["servers"]],
            backendServers=list(body.get("backendServers") or []),
            haproxy=body.get("haproxy", False),
            haproxyPort=body.get("haproxyPort", 443),
            proxyMode=body.get("proxyMode", "tcp"),
            failback=body.get("failback", False),
            failoverTime=body.get("failoverTime", 0),
            failbackTime=body.get("failbackTime", 0),
            evictNfsClientsOnFailback=body.get("evictNfsClientsOnFailback", False),
            tuning=dict(body.get("tuning") or {}),
        )
        self.groups[gid] = group

    def create(self, call):
        self.next_id += 1
        self.stored(call.body, self.next_id)
        return 200, self.new_task("Create HA group", call.body["description"])

    def put(self, call, gid):
        self.stored(call.body, int(gid))
        return 200, self.new_task("Update HA group", call.body["description"])

    def delete(self, call, gid):
        del self.groups[int(gid)]
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, ha_group.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], fake.writes()


SPEC = dict(
    name="s3",
    service="rgw",
    backend="keepalived",
    vips=["10.0.0.100"],
    servers=[dict(server="gw1", nic="bond0"), dict(server="gw2", nic="bond0", vlan=50)],
    haproxy=True,
    backend_servers=["rgw1", "rgw2"],
)


def test_full_idempotency_sequence(monkeypatch):
    fake = HaCluster()

    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert r["changed"]
    assert r["diff"]["after"]["servers"] == [dict(server="gw1", nic="bond0"), dict(server="gw2", nic="bond0", vlan=50)]
    assert r["diff"]["after"]["backend_servers"] == ["rgw1", "rgw2"]
    assert_only_gets(fake)
    assert not fake.groups

    r = run(monkeypatch, fake, **SPEC)
    assert r["changed"]
    assert r["task"]["state"] == "FINISHED"
    group = r["ha_group"]
    assert group["servers"][1]["vlan"] == 70  # VLAN record id of tag 50 on gw2/bond0
    assert group["backendServers"] == [3, 4]

    r = run(monkeypatch, fake, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    update = dict(SPEC)
    update.update(failback=True, failback_time=30, tuning=dict(balance="leastconn"))
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["failback"] is False
    assert r["diff"]["after"]["failback"] is True
    assert r["diff"]["after"]["tuning"]["balance"] == "leastconn"
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    put = [c for c in fake.writes() if c.method == "PUT"][0].body
    # full replace: unchanged fields are carried over from the current group
    assert put["vips"] == ["10.0.0.100"]
    assert put["backendServers"] == [3, 4]
    assert put["failback"] is True and put["tuning"] == dict(balance="leastconn")

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, name="s3", state="absent")
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert fake.groups

    r = run(monkeypatch, fake, name="s3", state="absent")
    assert r["changed"]
    assert not fake.groups

    r = run(monkeypatch, fake, name="s3", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def existing(**overrides):
    group = dict(
        id=7,
        description="nfs",
        service="nfs",
        backend="keepalived",
        vips=["192.168.1.10"],
        servers=[dict(server=1, nic=11, vlan=None)],
        backendServers=[],
        haproxy=False,
        haproxyPort=443,
        proxyMode="tcp",
        failback=False,
        failoverTime=0,
        failbackTime=0,
        evictNfsClientsOnFailback=False,
        tuning={},
    )
    group.update(overrides)
    return group


def test_unset_options_left_alone(monkeypatch):
    fake = HaCluster([existing()])
    r = run(monkeypatch, fake, name="nfs")
    assert not r["changed"]


def test_vips_compared_as_normalised_set(monkeypatch):
    fake = HaCluster([existing(backend="keepafloatd", vips=["10.0.0.2", "10.0.0.1"])])
    r = run(monkeypatch, fake, name="nfs", vips=[" 10.0.0.1", "10.0.0.2"])
    assert not r["changed"]


def test_member_by_nic_id_and_server_id(monkeypatch):
    fake = HaCluster([existing()])
    r = run(monkeypatch, fake, name="nfs", servers=[dict(server="1", nic="11")])
    assert not r["changed"]


def test_unknown_nic_fails(monkeypatch):
    fake = HaCluster([existing()])
    r = run(monkeypatch, fake, name="nfs", servers=[dict(server="gw1", nic="eth9")])
    assert r["failed"]
    assert "bond0" in r["msg"]


def test_unknown_vlan_fails(monkeypatch):
    fake = HaCluster([existing()])
    r = run(monkeypatch, fake, name="nfs", servers=[dict(server="gw1", nic="eth0", vlan=99)])
    assert r["failed"]


def test_unknown_server_fails(monkeypatch):
    fake = HaCluster([existing()])
    r = run(monkeypatch, fake, name="nfs", servers=[dict(server="ghost", nic="eth0")])
    assert r["failed"]
    assert "gw1 (1)" in r["msg"]


def test_backend_is_immutable(monkeypatch):
    fake = HaCluster([existing()])
    r = run(monkeypatch, fake, check_mode=True, name="nfs", backend="keepafloatd")
    assert r["failed"]
    assert_only_gets(fake)


def test_keepafloatd_members_cannot_change(monkeypatch):
    fake = HaCluster([existing(backend="keepafloatd")])
    r = run(monkeypatch, fake, name="nfs", servers=[dict(server="gw2", nic="eth0")])
    assert r["failed"]
    assert "recreate" in r["msg"]


def test_create_requires_service_and_servers(monkeypatch):
    fake = HaCluster()
    r = run(monkeypatch, fake, name="new", vips=["10.0.0.1"])
    assert r["failed"]
    assert_only_gets(fake)


def test_duplicate_names_fail(monkeypatch):
    fake = HaCluster([existing(), existing(id=8)])
    r = run(monkeypatch, fake, name="nfs")
    assert r["failed"]


def test_warning_needs_ignore_warnings(monkeypatch):
    fake = HaCluster([existing()])
    fake.routes.insert(
        0,
        (
            "PUT",
            re.compile(r"^/servers/ha-groups/7$"),
            lambda call, **kw: (400, dict(code=400, message="w", ignorableWarning=dict(token="t", warningText="RGW moves")))
            if call.query.get("ignoreWarning") != "t"
            else fake.put(call, "7"),
        ),
    )
    r = run(monkeypatch, fake, name="nfs", failback=True)
    assert r["failed"] and r["warning"] == "RGW moves"
    r = run(monkeypatch, fake, name="nfs", failback=True, ignore_warnings=True)
    assert r["changed"]
    assert fake.groups[7]["failback"] is True
