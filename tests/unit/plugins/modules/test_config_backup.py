# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import config_backup
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

SECRET = "sup3r-s3cret-value"
ENC_KEY = "1b4e28ba-2fa1-11d2-883f-0016d3cca427"


class BackupCluster(FakeCroit):
    def __init__(self, cloud_enabled=False, s3=None):
        super(BackupCluster, self).__init__()
        self.serve_tasks(finish_on_poll=True)
        self.cloud = dict(enabled=cloud_enabled, backupEncryptionKey=ENC_KEY, clusterId="c1")
        self.s3 = dict(
            enabled=False,
            endpoint=None,
            bucket=None,
            prefix=None,
            region=None,
            accessKey=None,
            encrypt=False,
            skipCertCheck=False,
            secretKeySet=False,
        )
        self.s3.update(s3 or {})
        self.secret = None
        self.route("GET", "/maintenance/config-backups", lambda call: (200, copy.deepcopy(self.cloud)))
        self.route("PATCH", "/maintenance/config-backups", self.patch_cloud)
        self.route("GET", "/maintenance/config-backups/s3", lambda call: (200, copy.deepcopy(self.s3)))
        self.route("PUT", "/maintenance/config-backups/s3", self.put_s3)
        self.route("POST", "/maintenance/config-backups/create", lambda call: (200, self.new_task("Cloud backup", state="RUNNING")))
        self.route("POST", "/maintenance/config-backups/s3/create", lambda call: (200, self.new_task("S3 backup", state="RUNNING")))

    def patch_cloud(self, call):
        if call.body.get("enabled") is not None:
            self.cloud["enabled"] = call.body["enabled"]
        return 204, None

    def put_s3(self, call):
        body = call.body
        if body.get("secretKey") is not None:
            self.secret = body["secretKey"]
            self.s3["secretKeySet"] = True
        for key in ("enabled", "endpoint", "bucket", "prefix", "region", "accessKey", "encrypt"):
            self.s3[key] = body.get(key)
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, config_backup.main, check_mode=check_mode, **params)


def only_gets(fake):
    assert fake.writes() == [], fake.writes()


S3_SPEC = dict(enabled=True, endpoint="https://s3.example", bucket="b", access_key="AK", secret_key=SECRET)


def test_full_idempotency_sequence(monkeypatch):
    fake = BackupCluster()
    spec = dict(cloud_enabled=True, s3=S3_SPEC)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"]["s3"]["secret_key"] == "********"
    only_gets(fake)

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.cloud["enabled"] and fake.s3["enabled"] and fake.secret == SECRET

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    only_gets(fake)

    update = dict(cloud_enabled=True, s3=dict(S3_SPEC, prefix="cluster-a/", encrypt=True))
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["s3"]["prefix"] is None and r["diff"]["after"]["s3"]["prefix"] == "cluster-a/"
    only_gets(fake)

    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    body = fake.writes()[0].body
    assert body["secretKey"] is None  # stored secret kept
    assert body["bucket"] == "b" and body["prefix"] == "cluster-a/" and body["encrypt"] is True

    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    only_gets(fake)

    off = dict(cloud_enabled=False, s3=dict(enabled=False))
    r = run(monkeypatch, fake, check_mode=True, **off)
    assert r["changed"]
    only_gets(fake)

    r = run(monkeypatch, fake, **off)
    assert r["changed"] and not fake.cloud["enabled"] and not fake.s3["enabled"]
    assert fake.s3["bucket"] == "b"  # other settings kept

    r = run(monkeypatch, fake, **off)
    assert not r["changed"]
    only_gets(fake)


def test_secret_always_reports_change_and_never_leaks(monkeypatch):
    fake = BackupCluster(s3=dict(enabled=True, bucket="b", secretKeySet=True))
    r = run(monkeypatch, fake, s3=dict(secret_key=SECRET, update_secret="always"))
    assert r["changed"]
    assert r["diff"]["after"]["s3"]["secret_key"] == "******** (changed)"
    assert fake.secret == SECRET
    assert SECRET not in repr(r)


def test_secret_on_create_kept(monkeypatch):
    fake = BackupCluster(s3=dict(enabled=True, bucket="b", secretKeySet=True))
    r = run(monkeypatch, fake, s3=dict(secret_key="other"))
    assert not r["changed"]
    only_gets(fake)


def test_enable_without_secret_fails(monkeypatch):
    fake = BackupCluster()
    r = run(monkeypatch, fake, s3=dict(enabled=True, bucket="b"))
    assert r["failed"] and "secret_key" in r["msg"]
    only_gets(fake)


def test_empty_string_clears(monkeypatch):
    fake = BackupCluster(s3=dict(prefix="p/", secretKeySet=True))
    r = run(monkeypatch, fake, s3=dict(prefix=""))
    assert r["changed"] and fake.s3["prefix"] is None


def test_encryption_key_hidden_by_default(monkeypatch):
    fake = BackupCluster()
    r = run(monkeypatch, fake)
    assert not r["changed"]
    assert "backupEncryptionKey" not in r["cloud"] and ENC_KEY not in repr(r)
    r = run(monkeypatch, fake, return_encryption_key=True)
    assert r["cloud"]["backupEncryptionKey"] == ENC_KEY


def test_run_now_is_an_action(monkeypatch):
    fake = BackupCluster(cloud_enabled=True)
    r = run(monkeypatch, fake, check_mode=True, run_now=["cloud", "s3"])
    assert r["changed"]
    only_gets(fake)

    r = run(monkeypatch, fake, run_now=["cloud", "s3"])
    assert r["changed"]
    assert [t["state"] for t in r["tasks"]] == ["FINISHED", "FINISHED"]
    assert r["task"] == r["tasks"][-1]
    assert [c.path for c in fake.writes()] == ["/maintenance/config-backups/create", "/maintenance/config-backups/s3/create"]


def test_failed_backup_fails(monkeypatch):
    fake = BackupCluster()
    fake.routes = [rt for rt in fake.routes if rt[1].pattern != "^/maintenance/config-backups/s3/create$"]
    fake.route(
        "POST",
        "/maintenance/config-backups/s3/create",
        lambda call: (200, fake.new_task("S3 backup", state="FAILED", output="403 Forbidden")),
    )
    r = run(monkeypatch, fake, run_now=["s3"])
    assert r["failed"] and "403 Forbidden" in r["msg"]


def test_certificate_warning(monkeypatch):
    fake = BackupCluster(s3=dict(secretKeySet=True))
    state = dict(confirmed=False)
    original = fake.put_s3

    def put(call):
        if call.query.get("ignoreWarning") != "t":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="t", warningText="untrusted cert"))
        state["confirmed"] = True
        return original(call)

    fake.routes = [rt for rt in fake.routes if not (rt[0] == "PUT")]
    fake.route("PUT", "/maintenance/config-backups/s3", put)
    r = run(monkeypatch, fake, s3=dict(enabled=True, bucket="b"))
    assert r["failed"] and r["warning"] == "untrusted cert"
    r = run(monkeypatch, fake, s3=dict(enabled=True, bucket="b"), ignore_warnings=True)
    assert r["changed"] and state["confirmed"]
