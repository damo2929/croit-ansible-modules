# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import oidc_provider
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

SECRET = "oidc-client-s3cret"
DEFAULTS = dict(
    clientAuth="Basic",
    clientSecret=None,
    manualRoles=False,
    groupPointer="",
    roleMapping={},
    defaultRoles=[],
    scope="openid profile",
    issuerUrl=None,
    authorizeUrl=None,
    tokenUrl=None,
    userinfoUrl=None,
    jwksUrl=None,
    callbackBaseUri=None,
    defaultMaxExpiry=3600.0,
    defaultMinExpiry=60.0,
)


class OidcCluster(FakeCroit):
    """croit's PUT replaces the whole config: unset members fall back to defaults."""

    def __init__(self, providers=None):
        super(OidcCluster, self).__init__()
        self.providers = list(providers or [])
        self.next_id = 0
        self.serve_tasks()
        self.route("GET", "/auth/oidc", lambda call: (200, copy.deepcopy(self.providers)))
        self.route("POST", "/auth/oidc", self.create)
        self.route("PUT", r"/auth/oidc/(?P<pid>\d+)", self.replace)
        self.route("DELETE", r"/auth/oidc/(?P<pid>\d+)", self.delete)

    def build(self, pid, body):
        provider = dict(DEFAULTS)
        provider.update(body)
        provider.update(id=pid, providerName=body["name"])
        return provider

    def create(self, call):
        self.next_id += 1
        self.providers.append(self.build(self.next_id, call.body))
        return 200, self.new_task("Create OIDC provider", call.body["name"])

    def replace(self, call, pid):
        index = [i for i, p in enumerate(self.providers) if p["id"] == int(pid)][0]
        self.providers[index] = self.build(int(pid), call.body)
        return 200, self.new_task("Update OIDC provider")

    def delete(self, call, pid):
        self.providers = [p for p in self.providers if p["id"] != int(pid)]
        return 200, self.new_task("Delete OIDC provider")


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, oidc_provider.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


SPEC = dict(
    name="Keycloak",
    discovery_url="https://sso.example.com/.well-known/openid-configuration",
    client_id="croit",
    client_secret=SECRET,
    client_auth="basic",
    group_pointer="groups",
    role_mapping={"storage-admins": "admin"},
    default_roles=["viewer"],
)


def test_full_idempotency_sequence(monkeypatch):
    fake = OidcCluster()

    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **SPEC)
    assert r["changed"]
    assert r["task"]["state"] == "FINISHED"
    assert fake.providers[0]["clientSecret"] == SECRET

    r = run(monkeypatch, fake, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    update = merged(SPEC, scope="openid profile email")
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["scope"] == "openid profile"
    assert r["diff"]["after"]["scope"] == "openid profile email"
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    put = fake.writes()[0]
    # The whole configuration is sent, so nothing falls back to a default.
    assert put.body["clientSecret"] == SECRET
    assert put.body["roleMapping"] == {"storage-admins": "admin"}
    assert fake.providers[0]["scope"] == "openid profile email"

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    gone = dict(name="Keycloak", state="absent")
    r = run(monkeypatch, fake, check_mode=True, **gone)
    assert r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **gone)
    assert r["changed"]
    assert not fake.providers

    r = run(monkeypatch, fake, **gone)
    assert not r["changed"]
    assert_only_gets(fake)


def test_secret_never_in_result_or_diff(monkeypatch):
    fake = OidcCluster()
    r = run(monkeypatch, fake, **SPEC)
    assert SECRET not in repr(r)
    r = run(monkeypatch, fake, **merged(SPEC, client_secret="new-secret-value"))
    assert r["changed"]
    assert "new-secret-value" not in repr(r) and SECRET not in repr(r)
    assert r["diff"]["after"]["clientSecret"] == "******** (changed)"


def test_partial_update_keeps_other_fields(monkeypatch):
    fake = OidcCluster()
    run(monkeypatch, fake, **SPEC)
    r = run(monkeypatch, fake, name="Keycloak", default_roles=["viewer", "securefolder"])
    assert r["changed"]
    provider = fake.providers[0]
    assert provider["clientSecret"] == SECRET and provider["groupPointer"] == "groups"
    assert provider["defaultRoles"] == ["securefolder", "viewer"]


def test_empty_string_clears_override(monkeypatch):
    fake = OidcCluster()
    run(monkeypatch, fake, **merged(SPEC, issuer_url="https://issuer"))
    r = run(monkeypatch, fake, name="Keycloak", issuer_url="")
    assert r["changed"]
    assert fake.providers[0]["issuerUrl"] is None
    r = run(monkeypatch, fake, name="Keycloak", issuer_url="")
    assert not r["changed"]


def test_create_needs_discovery_and_client(monkeypatch):
    r = run(monkeypatch, OidcCluster(), name="X", client_id="c")
    assert r["failed"]
    assert "discovery_url" in r["msg"]


def test_invalid_role_mapping(monkeypatch):
    r = run(monkeypatch, OidcCluster(), **merged(SPEC, role_mapping={"g": "root"}))
    assert r["failed"]
