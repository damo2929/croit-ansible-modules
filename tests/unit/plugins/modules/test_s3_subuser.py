# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import s3_subuser
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_s3 import S3Cluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, s3_subuser.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def cluster():
    fake = S3Cluster()
    fake.add_user("backup", "Backup")
    return fake


def subusers(fake):
    return fake.users["backup"]["subusers"]


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()
    spec = dict(uid="backup", subuser="mon", permissions="read")

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["after"] == dict(permissions="read")
    assert_only_gets(fake)
    assert subusers(fake) == []

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(subuser="mon", permissions="read")
    assert r["subuser"] == dict(id="backup:mon", permissions="read")
    assert r["task"]["state"] == "FINISHED"

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    update = dict(spec)
    update["permissions"] = "full-control"
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"] == dict(permissions="read")
    assert r["diff"]["after"] == dict(permissions="full-control")
    assert_only_gets(fake)
    assert subusers(fake)[0]["permissions"] == "read"

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert [(c.method, c.path, c.body) for c in fake.writes()] == [
        ("PATCH", "/s3/users/backup/subusers/mon", dict(permissions="full-control"))
    ]

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, uid="backup", subuser="mon", state="absent")
    assert r["changed"]
    assert_only_gets(fake)
    assert subusers(fake)

    r = run(monkeypatch, fake, uid="backup", subuser="mon", state="absent")
    assert r["changed"]
    assert subusers(fake) == []

    r = run(monkeypatch, fake, uid="backup", subuser="mon", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_none_matches_null(monkeypatch):
    fake = cluster()
    subusers(fake).append(dict(subuser="s", permissions=None))
    r = run(monkeypatch, fake, uid="backup", subuser="s", permissions="none")
    assert not r["changed"]


def test_create_without_permissions(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, uid="backup", subuser="s")
    assert r["changed"]
    assert fake.writes()[0].body == dict(subuser="s", permissions=None)
    r = run(monkeypatch, fake, uid="backup", subuser="s")
    assert not r["changed"]


def test_missing_user(monkeypatch):
    fake = S3Cluster()
    r = run(monkeypatch, fake, uid="ghost", subuser="s")
    assert r["failed"]
    r = run(monkeypatch, fake, uid="ghost", subuser="s", state="absent")
    assert not r["changed"] and not r.get("failed")


def test_prefixed_name_rejected(monkeypatch):
    r = run(monkeypatch, cluster(), uid="backup", subuser="backup:s")
    assert r["failed"]


def test_delete_removes_subuser_keys(monkeypatch):
    fake = cluster()
    subusers(fake).append(dict(subuser="s", permissions="read"))
    fake.add_key("backup:s", "AK", "SECRET")
    r = run(monkeypatch, fake, uid="backup", subuser="s", state="absent")
    assert r["changed"]
    assert fake.keys == []
