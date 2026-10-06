# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import cephfs_guard, cephfs_guard_info, cephfs_guard_webhook
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_nfs import NfsCroit, assert_only_gets

SECRET_URL = "https://alerts.example.com/hooks/s3cr3t-token"


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, cephfs_guard.main, check_mode=check_mode, **params)


def hook(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, cephfs_guard_webhook.main, check_mode=check_mode, **params)


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def test_full_idempotency_sequence(monkeypatch):
    fake = NfsCroit()
    spec = dict(
        volume="cephfs",
        servers=[dict(server="node1", nic="eth1"), dict(server="node2", nic="eth1", vlan=50, http_port=9200)],
        detection=dict(action_threshold=0.7),
        detectors=dict(file_entropy=dict(enabled=True, weight=2.0)),
        actions=dict(snapshot=True, block=True),
    )

    # 1. enable in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["after"]["actions"]["block"] is True
    assert [s["server"] for s in r["diff"]["after"]["servers"]] == ["node1", "node2"]
    assert_only_gets(fake)
    assert not fake.guards

    # 2. enable: POST with the set settings, then the requested port
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    post = fake.writes()[0]
    assert post.body == dict(
        volume="cephfs",
        servers=[dict(id=1, nicId=11, vlanId=None, useIpv6=False), dict(id=2, nicId=21, vlanId=250, useIpv6=False)],
        detection=dict(actionThreshold=0.7),
        detectors=dict(fileEntropy=dict(enabled=True, weight=2.0)),
        actions=dict(snapshot=dict(enabled=True), block=dict(enabled=True)),
    )
    assert [c.method for c in fake.writes()] == ["POST", "PATCH"]
    assert fake.writes()[1].body == dict(httpPort=9200)
    assert sorted(s["httpPort"] for s in r["services"]) == [9100, 9200]

    # 3. re-run
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"], r.get("diff")
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode: threshold, a detector, an action, a new server, a port
    update = merged(
        spec,
        servers=spec["servers"] + [dict(server="node3", nic="eth0")],
        detection=dict(action_threshold=0.8),
        detectors=dict(ransom_note=dict(enabled=False)),
        actions=dict(block=False),
    )
    update["servers"][0] = dict(server="node1", nic="eth1", mds_port=9001)
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["detection"]["action_threshold"] == 0.7
    assert r["diff"]["after"]["detection"]["action_threshold"] == 0.8
    assert r["diff"]["after"]["detectors"]["ransom_note"]["enabled"] is False
    assert r["diff"]["after"]["actions"]["block"] is False
    assert "node3" in [s["server"] for s in r["diff"]["after"]["servers"]]
    assert [s["mds_port"] for s in r["diff"]["before"]["servers"] if s["server"] == "node1"] == [9000]
    assert [s["mds_port"] for s in r["diff"]["after"]["servers"] if s["server"] == "node1"] == [9001]
    assert_only_gets(fake)

    # 6. update: each changed block is sent whole
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    writes = fake.writes()
    patch = writes[0]
    assert patch.method == "PATCH"
    assert patch.body["detection"] == dict(actionThreshold=0.8, minDetectors=1)
    assert patch.body["detectors"]["ransomNote"] == dict(enabled=False, weight=1.0)
    assert patch.body["detectors"]["fileEntropy"] == dict(enabled=True, weight=2.0)
    assert patch.body["actions"] == dict(snapshot=dict(enabled=True), yaraScan=dict(enabled=False), block=dict(enabled=False))
    assert writes[1].method == "POST" and writes[1].body == dict(servers=[dict(id=3, nicId=30, vlanId=None, useIpv6=False)])
    assert writes[2].body == dict(mdsPort=9001)

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"], r.get("diff")
    assert_only_gets(fake)

    # 8. disable in check mode
    r = run(monkeypatch, fake, check_mode=True, volume="cephfs", state="absent")
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert fake.guards

    # 9. disable (the volume is untouched, so no confirmation)
    r = run(monkeypatch, fake, volume="cephfs", state="absent")
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["DELETE"]
    assert not fake.guards

    # 10. disable again
    r = run(monkeypatch, fake, volume="cephfs", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_interface_of_existing_instance_is_fixed(monkeypatch):
    fake = NfsCroit()
    run(monkeypatch, fake, volume="cephfs", servers=[dict(server="node1", nic="eth1")])
    r = run(monkeypatch, fake, check_mode=True, volume="cephfs", servers=[dict(server="node1", nic="eth0")])
    assert r["failed"] and "cannot be" in r["msg"]
    assert_only_gets(fake)


def test_unlisted_servers_are_left_alone(monkeypatch):
    fake = NfsCroit()
    run(monkeypatch, fake, volume="cephfs", servers=[dict(server="node1", nic="eth1"), dict(server="node2", nic="eth1")])
    r = run(monkeypatch, fake, volume="cephfs", servers=[dict(server="node1", nic="eth1")])
    assert not r["changed"]
    assert_only_gets(fake)


def test_enable_requires_servers_and_complete_detectors(monkeypatch):
    fake = NfsCroit()
    r = run(monkeypatch, fake, volume="cephfs")
    assert r["failed"] and "servers is required" in r["msg"]
    r = run(monkeypatch, fake, volume="cephfs", servers=[dict(server="node1", nic="eth1")], detectors=dict(ransom_note=dict(enabled=True)))
    assert r["failed"] and "enabled and weight" in r["msg"]
    assert_only_gets(fake)


def test_duplicate_server_fails(monkeypatch):
    r = run(monkeypatch, NfsCroit(), volume="cephfs", servers=[dict(server="node1", nic="eth1"), dict(server="1", nic="eth0")])
    assert r["failed"] and "more than once" in r["msg"]


def test_webhook_sequence_and_secrecy(monkeypatch):
    fake = NfsCroit()
    run(monkeypatch, fake, volume="cephfs", servers=[dict(server="node1", nic="eth1")])
    spec = dict(volume="cephfs", url=SECRET_URL)

    r = hook(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["after"]["timeout"] == "5s"
    assert_only_gets(fake)
    r = hook(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(url=SECRET_URL)
    r = hook(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)
    r = hook(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]

    r = hook(monkeypatch, fake, check_mode=True, alert_timeout="10s", **spec)
    assert r["changed"] and r["diff"]["before"]["timeout"] == "5s" and r["diff"]["after"]["timeout"] == "10s"
    assert_only_gets(fake)
    r = hook(monkeypatch, fake, alert_timeout="10s", **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(url=SECRET_URL, timeout="10s")
    r = hook(monkeypatch, fake, alert_timeout="10s", **spec)
    assert not r["changed"]
    assert "s3cr3t-token" not in repr(r)

    r = hook(monkeypatch, fake, check_mode=True, state="absent", **spec)
    assert r["changed"]
    assert_only_gets(fake)
    r = hook(monkeypatch, fake, state="absent", **spec)
    assert r["changed"] and [c.method for c in fake.writes()] == ["DELETE"]
    assert "s3cr3t-token" not in repr(r)
    r = hook(monkeypatch, fake, state="absent", **spec)
    assert not r["changed"]


def test_webhook_needs_guarded_volume(monkeypatch):
    fake = NfsCroit()
    r = hook(monkeypatch, fake, volume="cephfs", url=SECRET_URL)
    assert r["failed"] and "cephfs_guard" in r["msg"]
    r = hook(monkeypatch, fake, volume="cephfs", url=SECRET_URL, state="absent")
    assert not r["changed"]


def test_info(monkeypatch):
    fake = NfsCroit()
    run(monkeypatch, fake, volume="cephfs", servers=[dict(server="node1", nic="eth1")])
    hook(monkeypatch, fake, volume="cephfs", url=SECRET_URL)
    r = run_module(monkeypatch, fake, cephfs_guard_info.main, check_mode=True)
    assert not r["changed"]
    assert r["configs"][0]["volume"] == "cephfs"
    assert len(r["configs"][0]["services"]) == 1
    assert "webhooks" not in r["configs"][0] and "incidents" not in r
    r = run_module(monkeypatch, fake, cephfs_guard_info.main, volume="cephfs", webhooks=True, incidents=True)
    assert r["configs"][0]["webhooks"][0]["url"] == "********"
    assert [i["id"] for i in r["incidents"]] == [1]
    assert "s3cr3t-token" not in repr(r)
    assert_only_gets(fake)
