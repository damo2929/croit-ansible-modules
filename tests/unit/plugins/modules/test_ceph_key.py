# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import re

import pytest

from ansible_collections.croit.ceph.plugins.modules import ceph_key, ceph_key_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

SECRET = "AQBsecretsecretsecret=="


class KeyCluster(FakeCroit):
    """Fake croit holding ceph keys."""

    def __init__(self, keys=None, system=None):
        super(KeyCluster, self).__init__()
        self.keys = dict((k["user"], k) for k in (keys or []))
        self.system = set(system or [])
        self.route("GET", "/keys", self.list_keys)
        self.route("POST", "/keys", self.create)
        self.route("PATCH", "/keys/(?P<user>[^/]+)", self.patch)
        self.route("DELETE", "/keys/(?P<user>[^/]+)", self.delete)
        self.route("GET", "/keys/(?P<user>[^/]+)/download", self.download)

    def list_keys(self, call):
        include_system = call.query.get("includeSystemKeys") == "true"
        show = call.query.get("showKeys") == "true"
        result = []
        for name, key in self.keys.items():
            if name in self.system and not include_system:
                continue
            key = copy.deepcopy(key)
            key["key"] = SECRET if show else None
            result.append(key)
        return 200, result

    @staticmethod
    def raw(permissions):
        return dict((d, permissions.get(d)) for d in ("mon", "osd", "mds", "mgr"))

    def create(self, call):
        body = call.body
        assert body["permissions"]["type"] == "RawCephPermissions"
        if body["user"] in self.keys:
            return 400, dict(code=400, message="exists")
        raw = self.raw(body["permissions"])
        self.keys[body["user"]] = dict(user=body["user"], comment=body["comment"], permissions=dict(raw, type="RawCephPermissions"), rawPermissions=raw)
        return 204, None

    def patch(self, call, user):
        key = self.keys[user]
        if "comment" in call.body:
            key["comment"] = call.body["comment"]
        if "permissions" in call.body:
            key["rawPermissions"] = self.raw(call.body["permissions"])
            key["permissions"] = dict(key["rawPermissions"], type="RawCephPermissions")
        return 204, None

    def delete(self, call, user):
        del self.keys[user]
        return 204, None

    def download(self, call, user):
        return 200, dict(fileName="ceph.%s.keyring" % user, url="/dl/x", fileContents="[%s]\n\tkey = %s\n" % (user, SECRET))


def existing(user="client.vms", comment="", **caps):
    raw = dict((d, caps.get(d)) for d in ("mon", "osd", "mds", "mgr"))
    return dict(user=user, comment=comment, permissions=dict(raw, type="RawCephPermissions"), rawPermissions=raw)


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, ceph_key.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = KeyCluster()
    spec = dict(name="client.vms", comment="Hypervisors", caps=dict(mon="profile rbd", osd="profile rbd pool=vms"))

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["after"]["caps"]["osd"] == "profile rbd pool=vms"
    assert_only_gets(fake)
    assert "client.vms" not in fake.keys

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    body = fake.writes()[0].body
    assert body == dict(
        user="client.vms",
        comment="Hypervisors",
        permissions=dict(type="RawCephPermissions", mon="profile rbd", osd="profile rbd pool=vms"),
    )
    assert r["key"]["user"] == "client.vms"

    # 3. re-run
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode
    update = dict(spec)
    update["caps"] = dict(mon="profile rbd", osd="profile rbd pool=vms, profile rbd pool=images")
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["caps"]["osd"] == "profile rbd pool=vms"
    assert r["diff"]["after"]["caps"]["osd"] == "profile rbd pool=vms, profile rbd pool=images"
    assert_only_gets(fake)

    # 6. update: only permissions sent
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert list(fake.writes()[0].body) == ["permissions"]
    assert fake.keys["client.vms"]["rawPermissions"]["osd"] == "profile rbd pool=vms, profile rbd pool=images"

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, name="client.vms", state="absent")
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert "client.vms" in fake.keys

    # 9. delete
    r = run(monkeypatch, fake, name="client.vms", state="absent")
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["DELETE"]
    assert "client.vms" not in fake.keys

    # 10. delete again
    r = run(monkeypatch, fake, name="client.vms", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


@pytest.mark.parametrize(
    "have,want",
    [
        ("profile rbd pool=vms", "profile  rbd   pool = vms"),
        ("allow r, allow rw pool=a", "allow r,allow rw pool=a"),
        ("allow r", " allow r "),
    ],
)
def test_caps_compared_ignoring_whitespace(monkeypatch, have, want):
    fake = KeyCluster([existing(osd=have)])
    r = run(monkeypatch, fake, name="client.vms", caps=dict(osd=want))
    assert not r["changed"]
    assert_only_gets(fake)


def test_caps_are_the_complete_set(monkeypatch):
    fake = KeyCluster([existing(mon="profile rbd", osd="profile rbd", mgr="profile rbd")])
    r = run(monkeypatch, fake, name="client.vms", caps=dict(mon="profile rbd", osd="profile rbd"))
    assert r["changed"]
    assert r["diff"]["after"]["caps"]["mgr"] is None
    assert fake.writes()[0].body["permissions"] == dict(type="RawCephPermissions", mon="profile rbd", osd="profile rbd")


def test_unset_options_left_alone(monkeypatch):
    fake = KeyCluster([existing(comment="x", mon="allow r")])
    r = run(monkeypatch, fake, name="client.vms")
    assert not r["changed"]
    assert_only_gets(fake)


def test_comment_only_update(monkeypatch):
    fake = KeyCluster([existing(comment="old", mon="allow r")])
    r = run(monkeypatch, fake, name="client.vms", comment="new")
    assert r["changed"]
    assert fake.writes()[0].body == dict(comment="new")


def test_secret_never_returned_by_default(monkeypatch):
    fake = KeyCluster([existing(mon="allow r")])
    r = run(monkeypatch, fake, name="client.vms", comment="changed")
    assert SECRET not in repr(r)
    assert "keyring" not in r


def test_return_keyring(monkeypatch):
    fake = KeyCluster([existing(mon="allow r")])
    r = run(monkeypatch, fake, name="client.vms", return_keyring=True)
    assert not r["changed"]
    assert r["keyring"]["file_name"] == "ceph.client.vms.keyring"
    assert SECRET in r["keyring"]["contents"]
    assert SECRET not in repr(r["diff"])
    assert_only_gets(fake)


def test_return_keyring_not_for_missing_key_in_check_mode(monkeypatch):
    fake = KeyCluster()
    r = run(monkeypatch, fake, check_mode=True, name="client.new", return_keyring=True)
    assert r["changed"]
    assert "keyring" not in r
    assert not any(c.path.endswith("/download") for c in fake.calls)


def test_key_type_sent_on_create_only(monkeypatch):
    fake = KeyCluster()
    run(monkeypatch, fake, name="client.new", key_type="aes")
    assert fake.writes()[0].body["keyType"] == "aes"
    r = run(monkeypatch, fake, name="client.new", key_type="aes256k")
    assert not r["changed"]


def test_system_keys_are_found(monkeypatch):
    fake = KeyCluster([existing(user="client.admin", mon="allow *")], system=["client.admin"])
    r = run(monkeypatch, fake, name="client.admin", caps=dict(mon="allow *"))
    assert not r["changed"]
    assert fake.calls[0].query == dict(includeSystemKeys="true")


def test_system_key_warning(monkeypatch):
    fake = KeyCluster([existing(user="client.admin", mon="allow *")], system=["client.admin"])
    fake.routes.insert(
        0,
        (
            "DELETE",
            re.compile("^/keys/client.admin$"),
            lambda call, **kw: (400, dict(code=400, message="w", ignorableWarning=dict(token="t", warningText="dangerous")))
            if call.query.get("ignoreWarning") != "t"
            else fake.delete(call, "client.admin"),
        ),
    )
    r = run(monkeypatch, fake, name="client.admin", state="absent")
    assert r["failed"]
    assert r["warning"] == "dangerous"
    assert "client.admin" in fake.keys
    r = run(monkeypatch, fake, name="client.admin", state="absent", ignore_warnings=True)
    assert r["changed"]
    assert "client.admin" not in fake.keys


def test_unqualified_name_fails(monkeypatch):
    fake = KeyCluster()
    r = run(monkeypatch, fake, name="vms")
    assert r["failed"]
    assert "client.vms" in r["msg"]
    assert fake.calls == []


# ceph_key_info ---------------------------------------------------------------


def test_info_lists_without_secrets(monkeypatch):
    fake = KeyCluster([existing(mon="allow r"), existing(user="client.admin", mon="allow *")], system=["client.admin"])
    r = run_module(monkeypatch, fake, ceph_key_info.main, check_mode=True)
    assert not r["changed"]
    assert [k["user"] for k in r["ceph_keys"]] == ["client.vms"]
    assert all("key" not in k for k in r["ceph_keys"])


def test_info_by_name_includes_system_keys(monkeypatch):
    fake = KeyCluster([existing(mon="allow r"), existing(user="client.admin", mon="allow *")], system=["client.admin"])
    r = run_module(monkeypatch, fake, ceph_key_info.main, name="client.admin")
    assert [k["user"] for k in r["ceph_keys"]] == ["client.admin"]


def test_info_show_secrets(monkeypatch):
    fake = KeyCluster([existing(mon="allow r")])
    r = run_module(monkeypatch, fake, ceph_key_info.main, show_secrets=True)
    assert r["ceph_keys"][0]["key"] == SECRET
    assert fake.calls[0].query["showKeys"] == "true"
