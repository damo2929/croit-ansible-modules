# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import api_token
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

SECRET = "4f6c2b2e-secret-token-value"


class TokenCluster(FakeCroit):
    def __init__(self, tokens=None, identity="ansible"):
        super(TokenCluster, self).__init__()
        self.tokens = list(tokens or [])
        self.next_id = 20
        self.identity = identity
        self.route("GET", "/api-tokens", lambda call: (200, copy.deepcopy(self.tokens)))
        self.route("POST", "/api-tokens", self.create)
        self.route("PATCH", r"/api-tokens/(?P<tid>\d+)", self.patch)
        self.route("DELETE", r"/api-tokens/(?P<tid>\d+)", self.delete)
        self.route("GET", "/auth/token-info", lambda call: (200, dict(username=self.identity, roles=["admin", "viewer"])))

    def token(self, tid):
        return [t for t in self.tokens if t["id"] == int(tid)][0]

    def create(self, call):
        self.next_id += 1
        self.tokens.append(
            dict(id=self.next_id, name=call.body["name"], roles=list(call.body["roles"]), expiresBy=call.body.get("expiry"))
        )
        return 200, SECRET

    def patch(self, call, tid):
        self.token(tid)["roles"] = list(call.body["roles"])
        return 204, None

    def delete(self, call, tid):
        self.tokens.remove(self.token(tid))
        return 204, None


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, api_token.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = TokenCluster()
    spec = dict(name="prometheus", roles=["viewer"])

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and "token" not in r
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["token"] == SECRET
    assert r["api_token"]["name"] == "prometheus"
    assert SECRET not in repr(r["api_token"]) and SECRET not in repr(r["diff"])

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"] and "token" not in r
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    update = merged(spec, roles=["viewer", "securefolder"])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["after"]["roles"] == ["securefolder", "viewer"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **update)
    assert r["changed"] and "token" not in r
    assert [c.method for c in fake.writes()] == ["PATCH"]

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    gone = dict(name="prometheus", state="absent")
    r = run(monkeypatch, fake, check_mode=True, **gone)
    assert r["changed"]
    assert_only_gets(fake)
    assert fake.tokens

    r = run(monkeypatch, fake, **gone)
    assert r["changed"]
    assert not fake.tokens

    r = run(monkeypatch, fake, **gone)
    assert not r["changed"]
    assert_only_gets(fake)


def test_expiry_sent_on_create(monkeypatch):
    fake = TokenCluster()
    run(monkeypatch, fake, name="ci", roles=["viewer"], expiry="2027-01-01T00:00:00Z")
    assert fake.writes()[0].body["expiry"] == "2027-01-01T00:00:00Z"


def test_same_expiry_other_spelling_is_no_change(monkeypatch):
    fake = TokenCluster([dict(id=1, name="ci", roles=["viewer"], expiresBy="2027-01-01T00:00:00+00:00")])
    r = run(monkeypatch, fake, name="ci", roles=["viewer"], expiry="2027-01-01T00:00:00Z")
    assert not r["changed"]


def test_different_expiry_fails(monkeypatch):
    fake = TokenCluster([dict(id=1, name="ci", roles=["viewer"], expiresBy=None)])
    r = run(monkeypatch, fake, check_mode=True, name="ci", roles=["viewer"], expiry="2027-01-01T00:00:00Z")
    assert r["failed"]
    assert "cannot change the expiry" in r["msg"]
    assert_only_gets(fake)


def test_refuses_to_delete_token_in_use(monkeypatch):
    fake = TokenCluster([dict(id=1, name="ansible", roles=["admin", "viewer"], expiresBy=None)])
    r = run(monkeypatch, fake, name="ansible", state="absent")
    assert r["failed"]
    assert fake.tokens


def test_refuses_to_demote_token_in_use(monkeypatch):
    fake = TokenCluster([dict(id=1, name="ansible", roles=["admin", "viewer"], expiresBy=None)])
    r = run(monkeypatch, fake, name="ansible", roles=["viewer"])
    assert r["failed"]
    assert_only_gets(fake)


def test_duplicate_names_fail(monkeypatch):
    fake = TokenCluster([dict(id=1, name="x", roles=["viewer"]), dict(id=2, name="x", roles=["viewer"])])
    r = run(monkeypatch, fake, name="x", roles=["viewer"])
    assert r["failed"]


def test_admin_needs_viewer(monkeypatch):
    r = run(monkeypatch, TokenCluster(), name="x", roles=["admin"])
    assert r["failed"]
