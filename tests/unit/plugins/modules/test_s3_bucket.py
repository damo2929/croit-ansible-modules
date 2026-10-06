# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json

from ansible_collections.croit.ceph.plugins.modules import s3_bucket, s3_bucket_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_s3 import S3Cluster

POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {"Effect": "Allow", "Principal": "*", "Action": ["s3:GetObject"], "Resource": ["arn:aws:s3:::b/*"]}
    ],
}


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, s3_bucket.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def cluster():
    fake = S3Cluster()
    fake.add_user("backup", "Backup")
    fake.add_user("web", "Web")
    return fake


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()
    spec = dict(name="b", owner="backup", versioning="enabled", quota=dict(enabled=True, max_size="1T"))

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"]["versioning"] == "ENABLED"
    assert r["diff"]["after"]["quota"] == dict(enabled=True, max_size=1024 ** 4, max_objects=-1)
    assert_only_gets(fake)
    assert "b" not in fake.buckets

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert [(c.method, c.path) for c in fake.writes()] == [("PUT", "/s3/buckets/b"), ("PUT", "/s3/buckets/b/quota")]
    assert fake.writes()[0].body == dict(owner="backup", versioning="ENABLED")
    assert r["bucket"]["versioning"] == "ENABLED"
    assert r["task"]["state"] == "FINISHED"

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    update = dict(spec)
    update.update(owner="web", versioning="suspended", policy=POLICY,
                  acl=[dict(grantee="single_user", permission="full_control", user_id="web"),
                       dict(grantee="all_users", permission="read")])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["owner"] == "backup"
    assert r["diff"]["after"]["owner"] == "web"
    assert r["diff"]["before"]["policy"] is None
    assert r["diff"]["after"]["policy"] == POLICY
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    writes = fake.writes()
    assert [(c.method, c.path) for c in writes] == [("PATCH", "/s3/buckets/b"), ("POST", "/s3/buckets/b/policy")]
    assert writes[0].body["owner"] == "web"
    assert writes[0].body["versioning"] == "SUSPENDED"
    assert writes[1].body == POLICY
    assert writes[1].query == dict(owner="web")
    assert fake.details["b"]["versioning"] == "SUSPENDED"

    r = run(monkeypatch, fake, **update)
    assert not r["changed"], r.get("diff")
    assert_only_gets(fake)

    absent = dict(name="b", state="absent", confirm_delete=True)
    r = run(monkeypatch, fake, check_mode=True, **absent)
    assert r["changed"]
    assert_only_gets(fake)
    assert "b" in fake.buckets

    r = run(monkeypatch, fake, **absent)
    assert r["changed"]
    assert fake.writes()[0].body == dict(name="b")
    assert "b" not in fake.buckets

    r = run(monkeypatch, fake, **absent)
    assert not r["changed"]
    assert_only_gets(fake)


def test_policy_compared_as_json(monkeypatch):
    fake = cluster()
    fake.add_bucket("b", "backup", policy=POLICY)
    reordered = json.dumps({"Statement": POLICY["Statement"], "Version": "2012-10-17"}, indent=4)
    r = run(monkeypatch, fake, name="b", policy=reordered)
    assert not r["changed"]
    assert_only_gets(fake)


def test_policy_removed_with_empty_dict(monkeypatch):
    fake = cluster()
    fake.add_bucket("b", "backup", policy=POLICY)
    r = run(monkeypatch, fake, name="b", policy={})
    assert r["changed"]
    assert [(c.method, c.path) for c in fake.writes()] == [("DELETE", "/s3/buckets/b/policy")]
    r = run(monkeypatch, fake, name="b", policy={})
    assert not r["changed"]


def test_invalid_policy(monkeypatch):
    fake = cluster()
    fake.add_bucket("b", "backup")
    r = run(monkeypatch, fake, name="b", policy="{not json")
    assert r["failed"]
    assert "not valid JSON" in r["msg"]


def test_acl_order_and_display_names_ignored(monkeypatch):
    fake = cluster()
    fake.add_bucket("b", "backup", acl=[
        dict(grantee="ALL_USERS", permission="Read", userId=None, displayName=None),
        dict(grantee="SINGLE_USER", permission="FullControl", userId="backup", displayName="Backup"),
    ])
    r = run(monkeypatch, fake, name="b", acl=[
        dict(grantee="single_user", permission="full_control", user_id="backup"),
        dict(grantee="all_users", permission="read"),
    ])
    assert not r["changed"]
    assert_only_gets(fake)


def test_acl_validation(monkeypatch):
    fake = cluster()
    fake.add_bucket("b", "backup")
    r = run(monkeypatch, fake, name="b", acl=[dict(grantee="single_user", permission="read")])
    assert r["failed"]
    r = run(monkeypatch, fake, name="b", acl=[dict(grantee="all_users", permission="read", user_id="x")])
    assert r["failed"]
    r = run(monkeypatch, fake, name="b", acl=[])
    assert r["failed"]


def test_suspended_satisfied_by_off(monkeypatch):
    fake = cluster()
    fake.add_bucket("b", "backup", versioning="OFF")
    r = run(monkeypatch, fake, name="b", versioning="suspended")
    assert not r["changed"]


def test_create_needs_owner(monkeypatch):
    r = run(monkeypatch, cluster(), check_mode=True, name="b")
    assert r["failed"]
    assert "owner" in r["msg"]


def test_create_only_options(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, name="b", owner="backup", placement="fast", object_lock=True,
            expected_number_of_objects=1000000)
    assert r["changed"]
    assert fake.writes()[0].body == dict(owner="backup", placement="fast", objectLock=True,
                                         expectedNumberOfObjects=1000000)
    r = run(monkeypatch, fake, name="b", owner="backup", placement="other", object_lock=False)
    assert not r["changed"]


def test_object_lock_with_suspended_versioning_fails(monkeypatch):
    r = run(monkeypatch, cluster(), name="b", owner="backup", object_lock=True, versioning="suspended")
    assert r["failed"]


def test_tenant_move_rejected(monkeypatch):
    fake = cluster()
    fake.add_user("t1$alice", "Alice")
    fake.add_bucket("b", "backup")
    r = run(monkeypatch, fake, name="b", owner="t1$alice")
    assert r["failed"]
    assert "tenant" in r["msg"]


def test_tenanted_create(monkeypatch):
    fake = cluster()
    fake.add_user("t1$alice", "Alice")
    r = run(monkeypatch, fake, name="t1:data", owner="t1$alice")
    assert r["changed"]
    assert fake.writes()[0].path == "/s3/buckets/data"
    assert "t1:data" in fake.buckets
    r = run(monkeypatch, fake, name="t1:data", owner="t1$alice")
    assert not r["changed"]


def test_delete_requires_confirmation(monkeypatch):
    fake = cluster()
    fake.add_bucket("b", "backup")
    r = run(monkeypatch, fake, name="b", state="absent")
    assert r["failed"]
    assert "b" in fake.buckets


def test_non_empty_bucket_needs_purge(monkeypatch):
    fake = cluster()
    fake.add_bucket("b", "backup", objects=42)
    r = run(monkeypatch, fake, check_mode=True, name="b", state="absent", confirm_delete=True)
    assert r["failed"]
    assert "purge_objects" in r["msg"]
    r = run(monkeypatch, fake, name="b", state="absent", confirm_delete=True, purge_objects=True)
    assert r["changed"]
    assert fake.writes()[0].body == dict(name="b", deleteData=True, thisWillDeleteData=s3_bucket.DELETE_CONFIRMATION)
    assert "b" not in fake.buckets


def test_bucket_info(monkeypatch):
    fake = cluster()
    fake.add_bucket("b1", "backup", policy=POLICY)
    fake.add_bucket("b2", "web")
    r = run_module(monkeypatch, fake, s3_bucket_info.main, check_mode=True)
    assert sorted(b["bucket"] for b in r["buckets"]) == ["b1", "b2"]
    assert "acl" not in r["buckets"][0]
    r = run_module(monkeypatch, fake, s3_bucket_info.main, names=["b1"], include_details=True, include_policy=True)
    assert len(r["buckets"]) == 1
    assert r["buckets"][0]["policy"] == POLICY
    assert r["buckets"][0]["versioning"] == "OFF"
    r = run_module(monkeypatch, fake, s3_bucket_info.main, owner="web")
    assert [b["bucket"] for b in r["buckets"]] == ["b2"]
    assert not r["changed"]
    assert fake.writes() == []
