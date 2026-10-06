# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

import pytest

from ansible_collections.croit.ceph.plugins.modules import ipmi
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

SERVERS = [dict(id=1, hostname="node1"), dict(id=2, hostname="node2")]


class IpmiCluster(FakeCroit):
    def __init__(self, devices=None):
        super(IpmiCluster, self).__init__()
        self.devices = dict((d["id"], d) for d in (devices or []))
        self.actions = []
        self.next_id = 50
        self.serve_tasks()
        self.reply("GET", "/servers", 200, SERVERS)
        self.route("GET", "/ipmi", lambda call: (200, [copy.deepcopy(d) for d in self.devices.values()]))
        self.route("GET", "/ipmi/poll-state", self.poll)
        self.route("POST", "/ipmi/add", self.add)
        self.route("DELETE", r"/ipmi/(?P<did>\d+)", self.delete)
        self.route("POST", r"/ipmi/(?P<did>\d+)/(?P<action>[a-z-]+)", self.act)

    def poll(self, call):
        ids = call.query["ipmiIds"]
        ids = ids if isinstance(ids, list) else [ids]
        return 200, dict((i, dict(state=self.devices[int(i)].get("state"), warnings=[])) for i in ids)

    def add(self, call):
        self.next_id += 1
        self.devices[self.next_id] = dict(id=self.next_id, ip=call.body["ip"], mac="aa", warnings=[], server=None, state=dict(power=False))
        return 204, None

    def delete(self, call, did):
        del self.devices[int(did)]
        return 204, None

    def act(self, call, did, action):
        self.actions.append((int(did), action, call.body))
        device = self.devices[int(did)]
        if action == "power-on":
            device["state"]["power"] = True
        elif action == "power-off":
            device["state"]["power"] = False
        if action == "initialize":
            return 200, self.new_task("Initialize IPMI")
        return 204, None


def device(did=7, server=1, power=True):
    return dict(id=did, ip="10.0.0.%d" % did, mac="m", warnings=[], server=dict(id=server, hostname="node%d" % server), state=dict(power=power))


def run(monkeypatch, fake, check_mode=False, **params):
    monkeypatch.setattr(ipmi.time, "sleep", lambda s: None)
    return run_module(monkeypatch, fake, ipmi.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = IpmiCluster()
    reg = dict(ip="10.0.0.99", username="ADMIN", password="bmc-secret")

    r = run(monkeypatch, fake, check_mode=True, **reg)
    assert r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **reg)
    assert r["changed"]
    assert fake.writes()[0].body == dict(ip="10.0.0.99", access=dict(username="ADMIN", password="bmc-secret", keepAdminPassword=True))
    assert "bmc-secret" not in repr(r)

    r = run(monkeypatch, fake, **reg)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **reg)
    assert not r["changed"]

    r = run(monkeypatch, fake, check_mode=True, ip="10.0.0.99", power="on")
    assert r["changed"]
    assert r["diff"]["before"]["power"] == "off" and r["diff"]["after"]["power"] == "on"
    assert_only_gets(fake)

    r = run(monkeypatch, fake, ip="10.0.0.99", power="on")
    assert r["changed"]
    assert [c.path for c in fake.writes()] == ["/ipmi/51/power-on"]

    r = run(monkeypatch, fake, ip="10.0.0.99", power="on")
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, ip="10.0.0.99", state="absent")
    assert r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, ip="10.0.0.99", state="absent")
    assert r["changed"]
    assert not fake.devices

    r = run(monkeypatch, fake, ip="10.0.0.99", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_power_off_needs_confirmation(monkeypatch):
    fake = IpmiCluster([device()])
    r = run(monkeypatch, fake, server="node1", power="off")
    assert r["failed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, server="node1", power="off", confirm_action=True)
    assert r["changed"]
    assert fake.devices[7]["state"]["power"] is False


@pytest.mark.parametrize("action", ["power_cycle", "reboot_to_bios"])
def test_destructive_actions_need_confirmation(monkeypatch, action):
    fake = IpmiCluster([device()])
    r = run(monkeypatch, fake, server="node1", action=action)
    assert r["failed"]
    assert_only_gets(fake)


@pytest.mark.parametrize("action,path", [("identify", "identify"), ("controller_reset", "ipmi-controller-reset")])
def test_one_shot_actions_always_change_and_skip_in_check_mode(monkeypatch, action, path):
    fake = IpmiCluster([device()])
    r = run(monkeypatch, fake, check_mode=True, server="node1", action=action)
    assert r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, server="node1", action=action)
    assert r["changed"]
    assert fake.actions == [(7, path, None)]
    r = run(monkeypatch, fake, server="node1", action=action)
    assert r["changed"]


def test_power_cycle_with_confirmation(monkeypatch):
    fake = IpmiCluster([device()])
    r = run(monkeypatch, fake, server="1", action="power_cycle", confirm_action=True)
    assert r["changed"]
    assert fake.actions == [(7, "power-cycle", None)]


def test_initialize_sends_access_and_waits_for_task(monkeypatch):
    fake = IpmiCluster([device()])
    r = run(monkeypatch, fake, ipmi_id=7, action="initialize", username="ADMIN", password="pw", keep_admin_password=False)
    assert r["changed"]
    assert r["task"]["state"] == "FINISHED"
    assert fake.actions[0][2] == dict(username="ADMIN", password="pw", keepAdminPassword=False)


def test_unknown_power_state_fails(monkeypatch):
    fake = IpmiCluster([dict(device(), state=None)])
    r = run(monkeypatch, fake, server="node1", power="on")
    assert r["failed"]
    assert "did not report" in r["msg"]


def test_server_without_bmc_fails_without_registration_data(monkeypatch):
    fake = IpmiCluster([device(server=1)])
    r = run(monkeypatch, fake, server="node2", power="on")
    assert r["failed"]
    assert_only_gets(fake)


def test_unknown_server_fails(monkeypatch):
    r = run(monkeypatch, IpmiCluster(), server="ghost", power="on")
    assert r["failed"]


def test_power_and_action_exclusive(monkeypatch):
    r = run(monkeypatch, IpmiCluster([device()]), server="node1", power="on", action="identify")
    assert r["failed"]
