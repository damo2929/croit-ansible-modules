# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible.module_utils import basic

from ansible_collections.croit.ceph.plugins.modules import user as user_module
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

PASSWORD = "Sup3r-S3cret-Pw"


class UserCluster(FakeCroit):
    """Fake croit holding accounts; the API token in use belongs to ``identity``."""

    def __init__(self, accounts=None, identity="ansible-token"):
        super(UserCluster, self).__init__()
        self.accounts = list(accounts or [])
        self.passwords = {}
        self.next_id = 10
        self.identity = identity
        self.route("GET", "/users", lambda call: (200, copy.deepcopy(self.accounts)))
        self.route("POST", "/users", self.create)
        self.route("PATCH", r"/users/(?P<uid>-?\d+)", self.patch)
        self.route("DELETE", r"/users/(?P<uid>-?\d+)", self.delete)
        self.route("PUT", r"/users/(?P<uid>-?\d+)/password", self.password)
        self.route("GET", "/auth/token-info", lambda call: (200, dict(username=self.identity, roles=["admin", "viewer"])))

    def account(self, uid):
        return [a for a in self.accounts if a["id"] == int(uid)][0]

    def create(self, call):
        self.next_id += 1
        self.accounts.append(
            dict(id=self.next_id, username=call.body["username"], roles=list(call.body["roles"]), authScheme="password", preferences={})
        )
        return 200, dict(id=self.next_id)

    def patch(self, call, uid):
        self.account(uid)["roles"] = list(call.body["roles"])
        return 204, None

    def delete(self, call, uid):
        self.accounts.remove(self.account(uid))
        return 204, None

    def password(self, call, uid):
        self.passwords[int(uid)] = call.body["password"]
        return 204, None


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, user_module.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = UserCluster()
    spec = dict(username="alice", roles=["viewer"], password=PASSWORD)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["after"]["password"] == "********"
    assert_only_gets(fake)
    assert not fake.accounts

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["user"]["username"] == "alice"
    assert [c.method for c in fake.writes()] == ["POST", "PUT"]
    assert fake.passwords[r["user"]["id"]] == PASSWORD

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    update = merged(spec, roles=["viewer", "admin"])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["roles"] == ["viewer"]
    assert r["diff"]["after"]["roles"] == ["admin", "viewer"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert [(c.method, c.body) for c in fake.writes()] == [("PATCH", dict(roles=["admin", "viewer"]))]

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    gone = dict(username="alice", state="absent")
    r = run(monkeypatch, fake, check_mode=True, **gone)
    assert r["changed"]
    assert_only_gets(fake)
    assert fake.accounts

    r = run(monkeypatch, fake, **gone)
    assert r["changed"]
    assert not fake.accounts

    r = run(monkeypatch, fake, **gone)
    assert not r["changed"]
    assert_only_gets(fake)


def existing(**kw):
    account = dict(id=5, username="alice", roles=["viewer"], authScheme="password", preferences={})
    account.update(kw)
    return account


def test_password_never_in_result(monkeypatch):
    fake = UserCluster()
    r = run(monkeypatch, fake, username="alice", roles=["viewer"], password=PASSWORD)
    assert PASSWORD not in repr(r)
    r = run(monkeypatch, fake, username="alice", password=PASSWORD, update_password="always")
    assert PASSWORD not in repr(r)


def test_update_password_always(monkeypatch):
    fake = UserCluster([existing()])
    r = run(monkeypatch, fake, check_mode=True, username="alice", password=PASSWORD, update_password="always")
    assert r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, username="alice", password=PASSWORD, update_password="always")
    assert r["changed"]
    assert fake.passwords[5] == PASSWORD


def test_update_password_on_create_leaves_existing_alone(monkeypatch):
    fake = UserCluster([existing()])
    r = run(monkeypatch, fake, username="alice", password="other")
    assert not r["changed"]
    assert_only_gets(fake)


def test_create_without_password_warns(monkeypatch):
    fake = UserCluster()
    warnings = []
    monkeypatch.setattr(basic.AnsibleModule, "warn", lambda self, msg: warnings.append(msg))
    r = run(monkeypatch, fake, username="bob", roles=["viewer"])
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST"]
    assert "cannot log in" in " ".join(warnings)


def test_roles_required_on_create(monkeypatch):
    r = run(monkeypatch, UserCluster(), username="bob")
    assert r["failed"]


def test_admin_needs_viewer(monkeypatch):
    fake = UserCluster()
    r = run(monkeypatch, fake, check_mode=True, username="bob", roles=["admin"])
    assert r["failed"]
    assert "viewer" in r["msg"]


def test_roles_compared_as_set(monkeypatch):
    fake = UserCluster([existing(roles=["viewer", "admin"])])
    r = run(monkeypatch, fake, username="alice", roles=["admin", "viewer", "viewer"])
    assert not r["changed"]


def test_ldap_user_refused(monkeypatch):
    fake = UserCluster([existing(id=-1, authScheme="ldap")])
    r = run(monkeypatch, fake, username="alice", state="absent")
    assert r["failed"]
    assert "ldap" in r["msg"]


def test_refuses_to_delete_own_user(monkeypatch):
    fake = UserCluster([existing()], identity="alice")
    r = run(monkeypatch, fake, check_mode=True, username="alice", state="absent")
    assert r["failed"]
    r = run(monkeypatch, fake, username="alice", state="absent")
    assert r["failed"]
    assert fake.accounts


def test_refuses_to_demote_own_user(monkeypatch):
    fake = UserCluster([existing(roles=["admin", "viewer"])], identity="alice")
    r = run(monkeypatch, fake, username="alice", roles=["viewer"])
    assert r["failed"]
    assert_only_gets(fake)
