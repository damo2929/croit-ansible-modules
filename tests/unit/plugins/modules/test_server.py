# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

import pytest

from ansible_collections.croit.ceph.plugins.modules import disk_info
from ansible_collections.croit.ceph.plugins.modules import server as server_module
from ansible_collections.croit.ceph.plugins.modules import server_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_servers import (
    ServerCluster,
    disk,
    nic,
    server,
)


def cluster():
    return ServerCluster(
        servers=[server(1, "node1", ips=["10.0.0.1", "192.168.0.1"]), server(2, "node2")],
        nics=[nic(11, 1, "eth0", "aa:bb:cc:00:00:01", ip="10.0.0.1/24"), nic(21, 2, "eth0", "aa:bb:cc:00:00:02")],
        disks=[
            disk(1, 1, "node1", role="osd", device_class="hdd"),
            disk(2, 1, "node1"),
            disk(3, 2, "node2", device_class="nvme", missing=True),
        ],
    )


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, server_module.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()
    # Servers register themselves, so the sequence is: update, update again, forget.
    spec = dict(server="node1", notes="rack B4", nr_hugepages=0)

    # 1. update in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["before"]["notes"] == ""
    assert r["diff"]["after"]["notes"] == "rack B4"
    assert_only_gets(fake)
    assert fake.servers[1]["notes"] is None

    # 2. update
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(notes="rack B4")
    assert r["server"]["notes"] == "rack B4"
    assert r["task"]["state"] == "FINISHED"

    # 3. re-run
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. rename + management IP in check mode
    update = dict(server="node1", hostname="storage-01", ip="192.168.0.1")
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["after"]["hostname"] == "storage-01"
    assert_only_gets(fake)

    # 6. rename
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.writes()[0].body == dict(hostname="storage-01", ip="192.168.0.1")
    assert fake.servers[1]["hostname"] == "storage-01"

    # 7. same task again: the old name no longer exists, the new one is found
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. forget in check mode
    r = run(monkeypatch, fake, check_mode=True, server="storage-01", state="absent", confirm_delete=True)
    assert r["changed"]
    assert_only_gets(fake)
    assert 1 in fake.servers

    # 9. forget
    r = run(monkeypatch, fake, server="storage-01", state="absent", confirm_delete=True)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["DELETE"]
    assert 1 not in fake.servers

    # 10. forget again
    r = run(monkeypatch, fake, server="storage-01", state="absent", confirm_delete=True)
    assert not r["changed"]
    assert_only_gets(fake)


def test_by_id(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="2", notes="x")
    assert r["changed"]
    assert fake.servers[2]["notes"] == "x"


def test_unknown_server_cannot_be_created(monkeypatch):
    r = run(monkeypatch, cluster(), server="ghost", notes="x")
    assert r["failed"]
    assert "registers itself" in r["msg"]


def test_ip_must_be_assigned(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", ip="172.16.0.9")
    assert r["failed"]
    assert "192.168.0.1" in r["msg"]
    assert_only_gets(fake)


def test_delete_requires_confirmation(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", state="absent")
    assert r["failed"]
    assert 1 in fake.servers


@pytest.mark.parametrize("action", ["reboot", "shutdown"])
def test_disruptive_actions_require_confirmation(monkeypatch, action):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", action=action)
    assert r["failed"]
    assert "confirm_action" in r["msg"]
    assert_only_gets(fake)


@pytest.mark.parametrize("action", ["reboot", "shutdown", "redetect"])
def test_actions_skipped_in_check_mode(monkeypatch, action):
    fake = cluster()
    r = run(monkeypatch, fake, check_mode=True, server="node1", action=action, confirm_action=True)
    assert r["changed"]
    assert_only_gets(fake)


def test_reboot_runs_task_and_always_changes(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", action="reboot", confirm_action=True)
    assert r["changed"]
    assert r["task"]["name"] == "Reboot"
    assert [c.path for c in fake.writes()] == ["/servers/1/reboot"]
    r = run(monkeypatch, fake, server="node1", action="reboot", confirm_action=True)
    assert r["changed"]


def test_redetect_needs_no_confirmation(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", action="redetect")
    assert r["changed"]
    assert "task" not in r


def test_settings_and_action_together(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, server="node1", image="img-new", action="reboot", confirm_action=True)
    assert r["changed"]
    assert [c.method + " " + c.path for c in fake.writes()] == ["PATCH /servers/1", "POST /servers/1/reboot"]


def test_reboot_question_fails_with_hint(monkeypatch):
    fake = cluster()
    question = dict(message="PGs would go inactive. Continue?", responseOptions=["Yes", "No"], defaultResponse="No", token="t")

    def reboot(call, sid):
        task = fake.new_task("Reboot", "node1", state="RUNNING")
        task["question"] = question
        return 200, task

    fake.routes.insert(0, ("POST", re.compile(r"^/servers/(?P<sid>\d+)/reboot$"), reboot))
    r = run(monkeypatch, fake, server="node1", action="reboot", confirm_action=True)
    assert r["failed"]
    assert "action=answer" in r["msg"]


def test_image_warning(monkeypatch):
    fake = cluster()
    original = fake.patch_server

    def patch(call, sid):
        if call.query.get("ignoreWarning") != "tok":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="tok", warningText="image change"))
        return original(call, sid)

    fake.routes.insert(0, ("PATCH", re.compile(r"^/servers/(?P<sid>\d+)$"), patch))
    r = run(monkeypatch, fake, server="node1", image="img-new")
    assert r["failed"]
    assert r["warning"] == "image change"
    r = run(monkeypatch, fake, server="node1", image="img-new", ignore_warnings=True)
    assert r["changed"]
    assert fake.servers[1]["image"] == "img-new"


# server_info -------------------------------------------------------------------


def test_server_info_all_and_filtered(monkeypatch):
    fake = cluster()
    r = run_module(monkeypatch, fake, server_info.main, check_mode=True)
    assert not r["changed"]
    assert [s["hostname"] for s in r["servers"]] == ["node1", "node2"]
    r = run_module(monkeypatch, fake, server_info.main, servers=["node2", "1"], include_nics=True)
    assert [s["id"] for s in r["servers"]] == [2, 1]
    assert [n["id"] for n in r["servers"][1]["nics"]] == [11]
    assert_only_gets(fake)


def test_server_info_unknown_fails(monkeypatch):
    r = run_module(monkeypatch, cluster(), server_info.main, servers=["ghost"])
    assert r["failed"]


# disk_info ---------------------------------------------------------------------


def test_disk_info_filters(monkeypatch):
    fake = cluster()
    r = run_module(monkeypatch, fake, disk_info.main)
    assert len(r["disks"]) == 3
    r = run_module(monkeypatch, fake, disk_info.main, server="node1", roles=["unassigned"])
    assert [d["id"] for d in r["disks"]] == [2]
    assert fake.calls[-1].path == "/servers/1/disks"
    r = run_module(monkeypatch, fake, disk_info.main, device_classes=["nvme"], include_missing=False)
    assert r["disks"] == []
    assert_only_gets(fake)
