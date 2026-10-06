# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import hook_script
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

POINTS = [
    dict(name="PostDaemonStart", canChooseServer=True, description="", parameters=[]),
    dict(name="OnHealthDegrade", canChooseServer=False, description="", parameters=[]),
    dict(name="OnHealthRecover", canChooseServer=False, description="", parameters=[]),
]
SERVERS = [dict(id=1, hostname="node1"), dict(id=2, hostname="node2")]


class HookCluster(FakeCroit):
    def __init__(self, scripts=None):
        super(HookCluster, self).__init__()
        self.scripts = {}
        self.contents = {}
        self.next_id = 0
        for script, content in scripts or []:
            self.scripts[script["id"]] = script
            self.contents[script["id"]] = content
        self.reply("GET", "/events/hooks/hook-points", 200, POINTS)
        self.reply("GET", "/servers", 200, SERVERS)
        self.route(
            "GET",
            "/events/hook-scripts",
            lambda call: (200, dict(data=[copy.deepcopy(s) for s in self.scripts.values()], total=len(self.scripts), after=0)),
        )
        self.route("POST", "/events/hook-scripts", self.create)
        self.route("PATCH", r"/events/hook-scripts/(?P<sid>\d+)", self.patch)
        self.route("GET", r"/events/scripts/(?P<sid>\d+)", lambda call, sid: (200, self.contents[int(sid)]))
        self.route("DELETE", r"/events/scripts/(?P<sid>\d+)", self.delete)

    def create(self, call):
        if any(s["name"] == call.body["name"] for s in self.scripts.values()):
            return 400, dict(code=400, message="name taken")
        self.next_id += 1
        self.scripts[self.next_id] = dict(id=self.next_id, name=call.body["name"], hooks=call.body["hooks"])
        self.contents[self.next_id] = call.body["contents"]
        return 200, dict(id=self.next_id)

    def patch(self, call, sid):
        sid = int(sid)
        if "contents" in call.body:
            self.contents[sid] = call.body["contents"]
        if "hooks" in call.body:
            # croit may answer the server lists in its own order
            self.scripts[sid]["hooks"] = [
                dict(h, serverIds=list(reversed(h["serverIds"])) if h.get("serverIds") else h.get("serverIds"))
                for h in reversed(call.body["hooks"])
            ]
        return 204, None

    def delete(self, call, sid):
        del self.scripts[int(sid)]
        del self.contents[int(sid)]
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, hook_script.main, check_mode=check_mode, **params)


def only_gets(fake):
    assert fake.writes() == [], fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = HookCluster()
    spec = dict(name="notify.sh", content="#!/bin/sh\necho hi\n", hooks=[dict(event="OnHealthDegrade")])

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["after"]["hooks"] == dict(OnHealthDegrade="management node")
    only_gets(fake)
    assert not fake.scripts

    r = run(monkeypatch, fake, **spec)
    assert r["changed"] and r["script"]["name"] == "notify.sh"
    assert fake.contents[1] == spec["content"]

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    only_gets(fake)

    update = dict(
        name="notify.sh",
        content="#!/bin/sh\necho bye\n",
        hooks=[dict(event="OnHealthRecover"), dict(event="PostDaemonStart", servers=["node2", "1"])],
    )
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["content"] == spec["content"]
    assert r["diff"]["after"]["hooks"]["PostDaemonStart"] == ["node1", "node2"]
    only_gets(fake)
    assert fake.contents[1] == spec["content"]

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    patch = fake.writes()[0].body
    assert patch["contents"] == update["content"]
    assert dict(event="PostDaemonStart", allServers=False, serverIds=[1, 2]) in patch["hooks"]

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, name="notify.sh", state="absent")
    assert r["changed"]
    only_gets(fake)
    assert fake.scripts

    r = run(monkeypatch, fake, name="notify.sh", state="absent")
    assert r["changed"] and not fake.scripts

    r = run(monkeypatch, fake, name="notify.sh", state="absent")
    assert not r["changed"]
    only_gets(fake)


def existing(hooks, content="x"):
    return HookCluster([(dict(id=3, name="s.sh", hooks=hooks), content)])


def test_unset_hooks_and_content_left_alone(monkeypatch):
    fake = existing([dict(event="PostDaemonStart", allServers=True, serverIds=None)])
    r = run(monkeypatch, fake, name="s.sh")
    assert not r["changed"]
    # content is only read when managed
    assert not any(c.path.startswith("/events/scripts/") for c in fake.calls)


def test_all_servers_vs_list(monkeypatch):
    fake = existing([dict(event="PostDaemonStart", allServers=True, serverIds=None)])
    assert not run(monkeypatch, fake, name="s.sh", hooks=[dict(event="PostDaemonStart")])["changed"]
    r = run(monkeypatch, fake, name="s.sh", hooks=[dict(event="PostDaemonStart", servers=["node1"])])
    assert r["changed"]


def test_management_point_server_fields_ignored(monkeypatch):
    fake = existing([dict(event="OnHealthDegrade", allServers=True, serverIds=[])])
    assert not run(monkeypatch, fake, name="s.sh", hooks=[dict(event="OnHealthDegrade")])["changed"]


def test_empty_hooks_detach(monkeypatch):
    fake = existing([dict(event="OnHealthDegrade", allServers=False, serverIds=None)])
    r = run(monkeypatch, fake, name="s.sh", hooks=[])
    assert r["changed"] and fake.writes()[0].body == dict(hooks=[])


def test_content_compared_exactly(monkeypatch):
    fake = existing([], content="echo hi\n")
    assert run(monkeypatch, fake, name="s.sh", content="echo hi")["changed"]


def test_numeric_script_text(monkeypatch):
    fake = existing([], content=42)
    assert not run(monkeypatch, fake, name="s.sh", content="42")["changed"]


def test_unknown_point_fails(monkeypatch):
    fake = existing([])
    r = run(monkeypatch, fake, name="s.sh", hooks=[dict(event="OnCoffee")])
    assert r["failed"] and "PostDaemonStart" in r["msg"]


def test_servers_on_management_point_fail(monkeypatch):
    r = run(monkeypatch, existing([]), name="s.sh", hooks=[dict(event="OnHealthDegrade", servers=["node1"])])
    assert r["failed"] and "management node" in r["msg"]


def test_unknown_server_fails(monkeypatch):
    r = run(monkeypatch, existing([]), name="s.sh", hooks=[dict(event="PostDaemonStart", servers=["ghost"])])
    assert r["failed"] and "node1 (1)" in r["msg"]


def test_duplicate_point_fails(monkeypatch):
    r = run(monkeypatch, existing([]), name="s.sh", hooks=[dict(event="OnHealthDegrade"), dict(event="OnHealthDegrade")])
    assert r["failed"]


def test_create_needs_content(monkeypatch):
    r = run(monkeypatch, HookCluster(), name="new.sh", hooks=[])
    assert r["failed"] and "content" in r["msg"]
