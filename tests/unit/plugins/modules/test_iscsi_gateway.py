# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import iscsi_gateway
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_iscsi import IQN, IscsiCluster

PORTAL_1 = dict(server="storage-1", ip="10.10.0.11")
PORTAL_2 = dict(server="storage-2", ip="10.10.0.12")


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, iscsi_gateway.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = IscsiCluster()
    spec = dict(description="VMware", servers=[PORTAL_1])

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["before"] == {}
    assert r["diff"]["after"]["servers"] == [PORTAL_1]
    assert_only_gets(fake)
    assert fake.service is None

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(description="VMware", servers=[dict(serverId=1, ip="10.10.0.11")])
    assert r["gateway"]["servers"][0]["hostname"] == "storage-1"
    assert r["task"]["state"] == "FINISHED"

    # 3. / 4. re-run, real and check mode
    for check in (False, True):
        r = run(monkeypatch, fake, check_mode=check, **spec)
        assert not r["changed"]
        assert_only_gets(fake)

    # 5. update in check mode: add a portal, change description
    update = dict(description="VMware prod", servers=[PORTAL_1, PORTAL_2])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["after"]["servers"] == [PORTAL_1, PORTAL_2]
    assert r["diff"]["after"]["description"] == "VMware prod"
    assert_only_gets(fake)
    assert len(fake.portals) == 1

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["PATCH", "POST"]
    assert len(r["gateway"]["servers"]) == 2

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, state="absent", confirm_delete=True)
    assert r["changed"] and r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert fake.service is not None

    # 9. delete confirms croit's warning
    r = run(monkeypatch, fake, state="absent", confirm_delete=True)
    assert r["changed"]
    assert [c.query.get("ignoreWarning") for c in fake.writes()] == [None, "del-gw"]
    assert fake.service is None

    # 10. delete again
    r = run(monkeypatch, fake, state="absent", confirm_delete=True)
    assert not r["changed"]
    assert_only_gets(fake)


def test_delete_requires_confirmation(monkeypatch):
    fake = IscsiCluster(gateway=True)
    for check in (True, False):
        r = run(monkeypatch, fake, check_mode=check, state="absent")
        assert r["failed"] and "confirm_delete" in r["msg"]
        assert_only_gets(fake)


def test_servers_list_is_complete(monkeypatch):
    fake = IscsiCluster(gateway=True)
    fake.portals.append(dict(serverId=2, hostname="storage-2", ip="10.10.0.12", healthy=True))
    r = run(monkeypatch, fake, servers=[PORTAL_2, dict(server="3", ip="10.10.0.13")])
    assert r["changed"]
    methods = [(c.method, c.path) for c in fake.writes()]
    # added before removed
    assert methods == [("POST", "/services/iscsi/7"), ("DELETE", "/services/iscsi/7/servers/storage-1")]
    assert sorted(p["hostname"] for p in fake.portals) == ["storage-2", "storage-3"]


def test_portal_ip_change_fails(monkeypatch):
    fake = IscsiCluster(gateway=True)
    r = run(monkeypatch, fake, servers=[dict(server="storage-1", ip="10.10.0.99")])
    assert r["failed"] and "cannot change a portal's IP" in r["msg"]
    assert_only_gets(fake)


def test_unknown_server_and_empty_list_fail(monkeypatch):
    fake = IscsiCluster(gateway=True)
    r = run(monkeypatch, fake, servers=[dict(server="ghost", ip="1.2.3.4")])
    assert r["failed"] and "storage-1 (1)" in r["msg"]
    r = run(monkeypatch, fake, servers=[])
    assert r["failed"] and "state=absent" in r["msg"]


def test_create_needs_servers(monkeypatch):
    fake = IscsiCluster()
    r = run(monkeypatch, fake, description="x")
    assert r["failed"] and "servers is required" in r["msg"]


def test_target_selection_and_warning(monkeypatch):
    fake = IscsiCluster(gateway=True)
    r = run(monkeypatch, fake, target=IQN)
    assert not r["changed"]
    other = "iqn.2001-07.com.ceph:other"
    r = run(monkeypatch, fake, target=other)
    assert r["failed"] and "ignore_warnings" in r["msg"]
    r = run(monkeypatch, fake, target=other, ignore_warnings=True)
    assert r["changed"] and fake.selected_target == other
    assert fake.writes()[-1].body == other


def test_client_passwords_masked_in_config(monkeypatch):
    fake = IscsiCluster(gateway=True)
    fake.clients["iqn.x"] = dict(username="user-1234", password="secret-12345", group=None, own=[])
    r = run(monkeypatch, fake)
    assert "secret-12345" not in repr(r)
    assert r["config"]["clients"][0]["password"] == "********"
