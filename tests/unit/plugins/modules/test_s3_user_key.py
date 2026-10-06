# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import s3_user_key
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_s3 import S3Cluster

SECRET = "s3cr3t-value-1"
SECRET2 = "s3cr3t-value-2"
OTHER_SECRET = "other-secret-value"


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, s3_user_key.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def assert_no_secret(result, *secrets):
    text = repr(result)
    for secret in secrets:
        assert secret not in text


def cluster():
    fake = S3Cluster()
    fake.add_user("backup", "Backup", subusers=[dict(subuser="mon", permissions="read")])
    return fake


def secret_of(fake, ak):
    return [k["secret_key"] for k in fake.keys if k["access_key"] == ak][0]


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()
    spec = dict(uid="backup", access_key="AK1", secret_key=SECRET)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"] == dict(user="backup", access_key="AK1", secret_key="********")
    assert_only_gets(fake)
    assert fake.keys == []

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    put = fake.writes()[0]
    assert (put.method, put.path, put.query) == ("PUT", "/s3/users/backup/keys/AK1", dict(secretKey=SECRET))
    assert r["key"] == dict(user="backup", access_key="AK1")
    assert_no_secret(r, SECRET)

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    update = dict(spec)
    update["secret_key"] = SECRET2
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["secret_key"] == "********"
    assert r["diff"]["after"]["secret_key"] == "******** (changed)"
    assert_no_secret(r, SECRET, SECRET2)
    assert_only_gets(fake)
    assert secret_of(fake, "AK1") == SECRET

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert secret_of(fake, "AK1") == SECRET2
    assert_no_secret(r, SECRET, SECRET2)

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, uid="backup", access_key="AK1", state="absent")
    assert r["changed"]
    assert_only_gets(fake)
    assert fake.keys

    r = run(monkeypatch, fake, uid="backup", access_key="AK1", state="absent")
    assert r["changed"]
    assert fake.keys == []
    assert_no_secret(r, SECRET, SECRET2)

    r = run(monkeypatch, fake, uid="backup", access_key="AK1", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_existing_key_without_secret_left_alone(monkeypatch):
    fake = cluster()
    fake.add_key("backup", "AK1", SECRET)
    r = run(monkeypatch, fake, uid="backup", access_key="AK1")
    assert not r["changed"]
    assert_no_secret(r, SECRET)


def test_create_needs_secret(monkeypatch):
    r = run(monkeypatch, cluster(), uid="backup", access_key="AK1")
    assert r["failed"]
    assert "secret_key" in r["msg"]


def test_subuser_key(monkeypatch):
    fake = cluster()
    fake.add_key("backup", "USERKEY", OTHER_SECRET)
    r = run(monkeypatch, fake, uid="backup", subuser="mon", access_key="MONKEY", secret_key=SECRET)
    assert r["changed"]
    assert fake.writes()[0].path == "/s3/users/backup/subusers/mon/keys/MONKEY"
    assert r["key"] == dict(user="backup:mon", access_key="MONKEY")
    r = run(monkeypatch, fake, uid="backup", subuser="mon", access_key="MONKEY", secret_key=SECRET)
    assert not r["changed"]


def test_exclusive_rotation(monkeypatch):
    fake = cluster()
    fake.add_key("backup", "OLD1", OTHER_SECRET)
    fake.add_key("backup", "OLD2", OTHER_SECRET)
    fake.add_key("backup:mon", "MONKEY", OTHER_SECRET)
    spec = dict(uid="backup", access_key="NEW", secret_key=SECRET, exclusive=True)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["removed_keys"] == ["OLD1", "OLD2"]
    assert r["diff"]["before"]["other_access_keys"] == ["OLD1", "OLD2"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert sorted(k["access_key"] for k in fake.keys) == ["MONKEY", "NEW"]
    assert_no_secret(r, SECRET, OTHER_SECRET)

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert r["removed_keys"] == []
    assert_only_gets(fake)


def test_exclusive_with_absent_rejected(monkeypatch):
    r = run(monkeypatch, cluster(), uid="backup", access_key="AK", state="absent", exclusive=True)
    assert r["failed"]


def test_access_key_of_other_user_fails(monkeypatch):
    fake = cluster()
    fake.add_user("other", "Other")
    fake.add_key("other", "TAKEN", OTHER_SECRET)
    r = run(monkeypatch, fake, uid="backup", access_key="TAKEN", secret_key=SECRET)
    assert r["failed"]
    assert "another user" in r["msg"]
    assert_no_secret(r, OTHER_SECRET)
