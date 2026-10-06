# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import s3_user, s3_user_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_s3 import S3Cluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, s3_user.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = S3Cluster()
    spec = dict(uid="backup", display_name="Backup", email="b@example.com",
                user_quota=dict(enabled=True, max_size="10T"))

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["before"] == {}
    assert r["diff"]["after"]["user_quota"] == dict(enabled=True, max_size=10 * 1024 ** 4, max_objects=-1)
    assert_only_gets(fake)
    assert "backup" not in fake.users

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST", "PUT"]
    assert fake.writes()[0].body == dict(uid="backup", name="Backup", email="b@example.com")
    assert r["user"]["userQuota"] == dict(enabled=True, maxSize=10 * 1024 ** 4, maxObjects=-1)

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
    update.update(email="", suspended=True, bucket_quota=dict(enabled=True, max_objects=1000))
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["email"] == "b@example.com"
    assert r["diff"]["after"]["email"] == ""
    assert r["diff"]["after"]["bucket_quota"] == dict(enabled=True, max_size=-1, max_objects=1000)
    assert_only_gets(fake)

    # 6. update: only changed fields
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    writes = fake.writes()
    assert [(c.method, c.path) for c in writes] == [("PATCH", "/s3/users/backup"), ("PUT", "/s3/users/backup/bucket-quota")]
    assert writes[0].body == dict(email="", suspended=True)
    assert writes[1].body == dict(enabled=True, maxSize=-1, maxObjects=1000)

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, uid="backup", state="absent")
    assert r["changed"]
    assert_only_gets(fake)
    assert "backup" in fake.users

    # 9. delete
    r = run(monkeypatch, fake, uid="backup", state="absent")
    assert r["changed"]
    assert "backup" not in fake.users

    # 10. delete again
    r = run(monkeypatch, fake, uid="backup", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_tenant_identity(monkeypatch):
    fake = S3Cluster()
    r = run(monkeypatch, fake, uid="alice", tenant="t1", display_name="Alice")
    assert r["changed"]
    assert fake.writes()[0].body == dict(uid="alice", tenant="t1", name="Alice")
    assert "t1$alice" in fake.users
    r = run(monkeypatch, fake, uid="t1$alice", display_name="Alice")
    assert not r["changed"]


def test_tenant_mismatch_fails(monkeypatch):
    r = run(monkeypatch, S3Cluster(), uid="t1$alice", tenant="t2")
    assert r["failed"]


def test_create_needs_display_name(monkeypatch):
    fake = S3Cluster()
    r = run(monkeypatch, fake, check_mode=True, uid="x")
    assert r["failed"]
    assert "display_name" in r["msg"]


def test_create_suspended_patches_afterwards(monkeypatch):
    fake = S3Cluster()
    r = run(monkeypatch, fake, uid="x", display_name="X", suspended=True)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST", "PATCH"]
    assert fake.users["x"]["suspended"] is True


def test_unset_options_left_alone(monkeypatch):
    fake = S3Cluster()
    fake.add_user("u", "U", email="u@example.com", suspended=True)
    r = run(monkeypatch, fake, uid="u")
    assert not r["changed"]
    assert_only_gets(fake)


def test_null_placement_matches_empty(monkeypatch):
    fake = S3Cluster()
    fake.add_user("u", "U")
    r = run(monkeypatch, fake, uid="u", default_placement="", email="")
    assert not r["changed"]


def test_quota_partial_keeps_other_bounds(monkeypatch):
    fake = S3Cluster()
    fake.add_user("u", "U", userQuota=dict(enabled=True, maxSize=1024, maxObjects=5))
    r = run(monkeypatch, fake, uid="u", user_quota=dict(max_objects=10))
    assert r["changed"]
    assert fake.writes()[0].body == dict(enabled=True, maxSize=1024, maxObjects=10)


def test_negative_bounds_normalised(monkeypatch):
    fake = S3Cluster()
    fake.add_user("u", "U", userQuota=dict(enabled=False, maxSize=-1024, maxObjects=-7))
    r = run(monkeypatch, fake, uid="u", user_quota=dict(enabled=False, max_size="unlimited", max_objects=-1))
    assert not r["changed"]


def test_invalid_quota_size(monkeypatch):
    fake = S3Cluster()
    fake.add_user("u", "U")
    r = run(monkeypatch, fake, uid="u", user_quota=dict(max_size="lots"))
    assert r["failed"]
    assert "user_quota.max_size" in r["msg"]


def test_delete_refused_while_owning_buckets(monkeypatch):
    fake = S3Cluster()
    fake.add_user("u", "U")
    fake.add_bucket("b1", "u")
    r = run(monkeypatch, fake, check_mode=True, uid="u", state="absent")
    assert r["failed"]
    assert "b1" in r["msg"]
    assert_only_gets(fake)


def test_user_info(monkeypatch):
    fake = S3Cluster()
    fake.add_user("a", "A")
    fake.add_user("b", "B")
    fake.add_bucket("bk", "b")
    fake.add_key("b", "AK", "SECRETVALUE")
    r = run_module(monkeypatch, fake, s3_user_info.main, check_mode=True)
    assert sorted(u["uid"] for u in r["users"]) == ["a", "b"]
    r = run_module(monkeypatch, fake, s3_user_info.main, uids=["b"], include_buckets=True)
    assert [u["uid"] for u in r["users"]] == ["b"]
    assert r["users"][0]["buckets"][0]["bucket"] == "bk"
    assert "SECRETVALUE" not in repr(r)
    assert not r["changed"]
    assert fake.writes() == []
