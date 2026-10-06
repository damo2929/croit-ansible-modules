# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils import basic

from ansible_collections.croit.ceph.plugins.modules import smb_share
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_smb import SmbCluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, smb_share.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def share_of(cluster, name):
    return next((s for s in cluster["shares"] if s["share"] == name), None)


GEN2 = dict(
    cluster="smb-office",
    name="projects",
    path="/smb/projects/",
    grants=[dict(name="staff", group=True, access="read_write"), dict(name="auditor", access="read")],
)


def test_gen2_full_idempotency_sequence(monkeypatch):
    fake = SmbCluster()
    cluster = fake.add_cluster("smb-office")

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **GEN2)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["after"]["path"] == "/smb/projects"
    assert r["diff"]["after"]["grants"] == [
        dict(name="auditor", group=False, access="read"),
        dict(name="staff", group=True, access="read_write"),
    ]
    assert_only_gets(fake)
    assert share_of(cluster, "projects") is None

    # 2. create: grants seed the on-disk ACL
    r = run(monkeypatch, fake, **GEN2)
    assert r["changed"]
    body = fake.writes()[0].body
    assert body["type"] == "simple" and body["path"] == "/smb/projects"
    assert body["grants"] == [dict(name="staff", group=True, access="READ_WRITE"), dict(name="auditor", group=False, access="READ")]
    assert r["share"]["share"] == "projects"

    # 3. re-run (grants compared as a set, read from the on-disk ACL)
    r = run(monkeypatch, fake, **merged(GEN2, grants=list(reversed(GEN2["grants"]))))
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **GEN2)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode: ACL and VFS stack
    update = merged(GEN2, grants=[dict(name="staff", group=True, access="read")], vfs_objects=["catia", "fruit"])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["after"]["grants"] == [dict(name="staff", group=True, access="read")]
    assert r["diff"]["after"]["vfs_objects"] == ["catia", "fruit"]
    assert_only_gets(fake)

    # 6. update: options PUT, then ACL PUT (a task)
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    share_id = share_of(cluster, "projects")["id"]
    assert [(c.method, c.path) for c in fake.writes()] == [
        ("PUT", "/services/smb/%d/shares/%d/options" % (cluster["serviceId"], share_id)),
        ("PUT", "/services/smb/%d/shares/%d/acl" % (cluster["serviceId"], share_id)),
    ]
    assert fake.writes()[0].body == dict(parameters={}, vfsObjects=["catia", "fruit"], vfsObjectsBefore=[])
    assert r["acl"]["grants"] == [dict(name="staff", group=True, access="READ")]

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, cluster="smb-office", name="projects", state="absent")
    assert r["changed"]
    assert_only_gets(fake)
    assert share_of(cluster, "projects") is not None

    # 9. delete (the directory stays, so no confirmation)
    r = run(monkeypatch, fake, cluster="smb-office", name="projects", state="absent")
    assert r["changed"]
    assert share_of(cluster, "projects") is None

    # 10. delete again
    r = run(monkeypatch, fake, cluster="smb-office", name="projects", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_gen2_fixed_fields_fail(monkeypatch):
    fake = SmbCluster()
    cluster = fake.add_cluster("smb-office")
    fake.add_share_row(cluster, "projects", "/smb/projects")
    for opt, value in (("path", "/elsewhere"), ("acl_mode", "posix"), ("volume", "other")):
        r = run(monkeypatch, fake, check_mode=True, cluster="smb-office", name="projects", **{opt: value})
        assert r["failed"], opt
        assert "create it again" in r["msg"]
    assert_only_gets(fake)


def test_gen2_unchanged_path_notation_is_no_change(monkeypatch):
    fake = SmbCluster()
    cluster = fake.add_cluster("smb-office")
    fake.add_share_row(cluster, "projects", "/smb/projects")
    r = run(monkeypatch, fake, cluster="smb-office", name="projects", path="smb/projects/", acl_mode="windows")
    assert not r["changed"] and not r.get("failed")


def test_gen2_warns_about_dropped_acl_entries(monkeypatch):
    fake = SmbCluster()
    cluster = fake.add_cluster("smb-office")
    share = fake.add_share_row(cluster, "projects", "/smb/projects")
    fake.acls[share["id"]]["unrepresentable"] = ["(D;;FA;;;S-1-5-21-1)"]
    warnings = []
    monkeypatch.setattr(basic.AnsibleModule, "warn", lambda self, msg: warnings.append(msg))
    r = run(monkeypatch, fake, check_mode=True, cluster="smb-office", name="projects", grants=[dict(name="staff", group=True)])
    assert r["changed"]
    assert "(D;;FA;;;S-1-5-21-1)" in " ".join(warnings)


def test_gen1_options_rejected_on_gen2(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-office")
    r = run(monkeypatch, fake, cluster="smb-office", name="projects", path="/p", rw_access=True)
    assert r["failed"]
    assert "generation-1" in r["msg"]


def test_gen1_simple_full_sequence(monkeypatch):
    fake = SmbCluster()
    cluster = fake.add_cluster("smb-legacy", gen=1)
    spec = dict(cluster="smb-legacy", name="data", path="/smb/data")

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"] == dict(path="/smb/data", rw_access=True, ro_access=False, guest=False)
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(type="simple", share="data", path="/smb/data", rw=True, ro=False, guest=False)
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]

    update = merged(spec, guest=True)
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    put = fake.writes()[0]
    assert put.method == "PUT"
    assert put.body == dict(type="simple", share="data", path="/smb/data", rw=True, ro=False, guest=True)
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, cluster="smb-legacy", name="data", state="absent")
    assert r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, cluster="smb-legacy", name="data", state="absent")
    assert r["changed"]
    assert share_of(cluster, "data") is None
    r = run(monkeypatch, fake, cluster="smb-legacy", name="data", state="absent")
    assert not r["changed"]


def test_gen1_ad_users_compared_as_sets(monkeypatch):
    fake = SmbCluster()
    cluster = fake.add_cluster("smb-ad", kind="active-directory", gen=1)
    fake.add_share_row(cluster, "data", "/smb/data", rwUsers=["@staff", "alice"], roUsers=[])
    r = run(monkeypatch, fake, cluster="smb-ad", name="data", rw_users=["alice", "@staff"])
    assert not r["changed"]
    r = run(monkeypatch, fake, cluster="smb-ad", name="data", ro_users=["bob"])
    assert r["changed"]
    put = fake.writes()[0].body
    assert put["rwUsers"] == ["@staff", "alice"] and put["roUsers"] == ["bob"]


def test_gen2_options_rejected_on_gen1(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-legacy", gen=1)
    r = run(monkeypatch, fake, cluster="smb-legacy", name="data", path="/p", grants=[dict(name="x")])
    assert r["failed"]
    assert "do not apply" in r["msg"]


def test_unknown_cluster_fails(monkeypatch):
    fake = SmbCluster()
    r = run(monkeypatch, fake, cluster="ghost", name="data", path="/p")
    assert r["failed"]
    assert "not known" in r["msg"]


def test_create_needs_path(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-office")
    r = run(monkeypatch, fake, cluster="smb-office", name="data")
    assert r["failed"]
    assert "path is required" in r["msg"]
