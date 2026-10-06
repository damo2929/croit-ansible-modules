# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import s3_multisite
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_rgw import TOKEN, RgwCluster

ENDPOINTS = ["http://10.1.0.11:80/", "http://10.1.0.12:80"]
SECONDARY = dict(enabled=True, type="SECONDARY", readonly=True, metrics={})


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, s3_multisite.main, check_mode=check_mode, **params)


def test_primary_sequence(monkeypatch):
    fake = RgwCluster()
    spec = dict(role="primary", endpoints=ENDPOINTS, sync_user="sync", confirm_action=True)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and fake.writes() == []
    assert r["diff"]["before"]["role"] == "standalone" and r["diff"]["after"]["role"] == "primary"
    assert not fake.multisite["enabled"]

    r = run(monkeypatch, fake, return_token=True, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(endpoints=["http://10.1.0.11:80", "http://10.1.0.12:80"], syncUser="sync")
    assert r["multisite"]["type"] == "PRIMARY" and r["token"] == TOKEN
    assert r["task"]["state"] == "FINISHED"

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"] and fake.writes() == []
    r = run(monkeypatch, fake, check_mode=True, return_token=True, **spec)
    assert not r["changed"] and fake.writes() == [] and r["token"] == TOKEN


def test_role_change_needs_confirm(monkeypatch):
    fake = RgwCluster()
    r = run(monkeypatch, fake, check_mode=True, role="primary", endpoints=ENDPOINTS, sync_user="sync")
    assert r["failed"] and "confirm_action" in r["msg"]
    assert fake.writes() == []


def test_convert_requires_endpoints_and_sync_user(monkeypatch):
    r = run(monkeypatch, RgwCluster(), role="primary", confirm_action=True)
    assert r["failed"] and "endpoints and sync_user are required" in r["msg"]


def test_join_and_readonly_sequence(monkeypatch):
    fake = RgwCluster()
    join = dict(role="secondary", zone="site-b", endpoints=["http://10.2.0.11:80"], token="SECRET-TOKEN",
                readonly=True, confirm_action=True)

    r = run(monkeypatch, fake, check_mode=True, **join)
    assert r["changed"] and fake.writes() == []
    assert r["diff"]["after"] == dict(role="secondary", readonly=True)
    r = run(monkeypatch, fake, **join)
    assert r["changed"]
    assert fake.writes()[0].body == dict(zone="site-b", endpoints=["http://10.2.0.11:80"], readonly=True, token="SECRET-TOKEN")
    assert [c.method for c in fake.writes()] == ["POST"]
    assert "SECRET-TOKEN" not in repr(r)

    r = run(monkeypatch, fake, role="secondary", readonly=True)
    assert not r["changed"] and fake.writes() == []
    r = run(monkeypatch, fake, check_mode=True, readonly=False)
    assert r["changed"] and fake.writes() == [] and fake.multisite["readonly"]
    r = run(monkeypatch, fake, readonly=False)
    assert r["changed"] and fake.writes()[0].body == dict(readonly=False)
    r = run(monkeypatch, fake, readonly=False)
    assert not r["changed"] and fake.writes() == []


def test_join_requires_exactly_one_source(monkeypatch):
    r = run(monkeypatch, RgwCluster(), role="secondary", zone="b", endpoints=["http://x:80"], confirm_action=True)
    assert r["failed"] and "exactly one" in r["msg"]


def test_join_with_primary_connection_hides_secret(monkeypatch):
    fake = RgwCluster()
    conn = dict(realm="r", zonegroup="zg", access_key="AK", secret_key="SK-SECRET", endpoints=["http://p:80/"])
    r = run(monkeypatch, fake, role="secondary", zone="b", endpoints=["http://x:80"], primary_connection=conn,
            confirm_action=True)
    assert r["changed"]
    sent = fake.writes()[0].body["primaryConnection"]
    assert sent == dict(realm="r", zoneGroup="zg", accessKey="AK", secretKey="SK-SECRET", endpoints=["http://p:80"])
    assert "SK-SECRET" not in repr(r)


def test_promote(monkeypatch):
    fake = RgwCluster(multisite=dict(SECONDARY))
    r = run(monkeypatch, fake, check_mode=True, role="primary", confirm_action=True)
    assert r["changed"] and fake.writes() == []
    r = run(monkeypatch, fake, role="primary", confirm_action=True)
    assert r["changed"]
    assert fake.writes()[0].path == "/s3/multisite/promote" and fake.writes()[0].body == {}
    assert r["multisite"]["type"] == "PRIMARY"
    r = run(monkeypatch, fake, role="primary", confirm_action=True)
    assert not r["changed"]


def test_promote_behind_needs_warning(monkeypatch):
    fake = RgwCluster(multisite=dict(SECONDARY, behind=True))
    r = run(monkeypatch, fake, role="primary", confirm_action=True)
    assert r["failed"] and r["warning"] == "site is behind"
    r = run(monkeypatch, fake, role="primary", confirm_action=True, ignore_warnings=True,
            pull_from_peer=dict(url="http://a:80", access_key="AK", secret_key="PEER-SECRET"))
    assert r["changed"]
    assert fake.writes()[-1].body == dict(pullFromPeer=dict(url="http://a:80", accessKey="AK", secretKey="PEER-SECRET"))
    assert "PEER-SECRET" not in repr(r)


def test_primary_cannot_become_secondary(monkeypatch):
    fake = RgwCluster(multisite=dict(enabled=True, type="PRIMARY", readonly=None, metrics={}))
    r = run(monkeypatch, fake, role="secondary", zone="x", endpoints=["http://x:80"], token="t", confirm_action=True)
    assert r["failed"] and "promoted" in r["msg"]


def test_readonly_on_primary_fails(monkeypatch):
    fake = RgwCluster(multisite=dict(enabled=True, type="PRIMARY", readonly=None, metrics={}))
    r = run(monkeypatch, fake, readonly=True)
    assert r["failed"]


def test_return_token_on_secondary_fails(monkeypatch):
    r = run(monkeypatch, RgwCluster(multisite=dict(SECONDARY)), return_token=True)
    assert r["failed"] and "only the multisite primary" in r["msg"]


def test_update_endpoints_is_an_action(monkeypatch):
    fake = RgwCluster(multisite=dict(enabled=True, type="PRIMARY", readonly=None, metrics={}))
    r = run(monkeypatch, fake, check_mode=True, update_endpoints=True, endpoints=ENDPOINTS)
    assert r["changed"] and fake.writes() == []
    r = run(monkeypatch, fake, update_endpoints=True, endpoints=ENDPOINTS)
    assert r["changed"] and fake.writes()[0].body == dict(endpoints=["http://10.1.0.11:80", "http://10.1.0.12:80"])
    r = run(monkeypatch, fake, update_endpoints=True)
    assert r["failed"]


def test_no_role_no_change(monkeypatch):
    fake = RgwCluster()
    r = run(monkeypatch, fake)
    assert not r["changed"] and fake.writes() == []
    assert r["multisite"]["enabled"] is False
