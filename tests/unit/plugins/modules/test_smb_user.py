# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils import basic

from ansible_collections.croit.ceph.plugins.modules import smb_group, smb_info, smb_user
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_smb import SmbCluster

SECRET = "Al1ce-Secret!"


def run(monkeypatch, fake, main=smb_user.main, check_mode=False, **params):
    return run_module(monkeypatch, fake, main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def cluster_with_groups(fake):
    cluster = fake.add_cluster("smb-office")
    cluster["groups"] = [dict(id=1, groupname="staff", gid=3001), dict(id=2, groupname="projects", gid=3002)]
    return cluster


def user_of(cluster, name):
    return next((u for u in cluster["users"] if u["username"] == name), None)


SPEC = dict(cluster="smb-office", name="alice", groups=["staff"], password=SECRET)


def test_user_full_idempotency_sequence(monkeypatch):
    fake = SmbCluster()
    cluster = cluster_with_groups(fake)

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert r["changed"]
    assert r["diff"]["after"] == dict(uid=None, groups=["staff"], password="********")
    assert_only_gets(fake)
    assert user_of(cluster, "alice") is None

    # 2. create: the password goes with the create request
    r = run(monkeypatch, fake, **SPEC)
    assert r["changed"]
    assert fake.writes()[0].body == dict(username="alice", groupIds=[1], password=SECRET)
    assert r["user"]["groups"] == ["staff"]
    assert r["task"]["state"] == "FINISHED"

    # 3. re-run: password is on_create, so nothing to do
    r = run(monkeypatch, fake, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode: group membership
    update = merged(SPEC, groups=["projects", "staff"])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["groups"] == ["staff"]
    assert r["diff"]["after"]["groups"] == ["projects", "staff"]
    assert_only_gets(fake)

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert [(c.method, c.body) for c in fake.writes()] == [("PUT", dict(groupIds=[1, 2]))]

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, cluster="smb-office", name="alice", state="absent")
    assert r["changed"]
    assert_only_gets(fake)
    assert user_of(cluster, "alice") is not None

    # 9. delete
    r = run(monkeypatch, fake, cluster="smb-office", name="alice", state="absent")
    assert r["changed"]
    assert user_of(cluster, "alice") is None

    # 10. delete again
    r = run(monkeypatch, fake, cluster="smb-office", name="alice", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_password_always_and_never_shown(monkeypatch):
    fake = SmbCluster()
    cluster_with_groups(fake)
    run(monkeypatch, fake, **SPEC)
    r = run(monkeypatch, fake, check_mode=True, update_password="always", **SPEC)
    assert r["changed"]
    assert r["diff"]["after"]["password"] == "******** (changed)"
    assert_only_gets(fake)
    r = run(monkeypatch, fake, update_password="always", **SPEC)
    assert r["changed"]
    assert fake.writes()[0].path.endswith("/password")
    assert fake.passwords.count(SECRET) == 2
    assert SECRET not in repr(r)


def test_uid_is_fixed(monkeypatch):
    fake = SmbCluster()
    cluster = cluster_with_groups(fake)
    cluster["users"].append(dict(id=9, username="alice", uid=2001, groupIds=[]))
    r = run(monkeypatch, fake, cluster="smb-office", name="alice", uid=2001)
    assert not r["changed"]
    r = run(monkeypatch, fake, cluster="smb-office", name="alice", uid=2002)
    assert r["failed"] and "cannot be changed" in r["msg"]


def test_unknown_group_fails(monkeypatch):
    fake = SmbCluster()
    cluster_with_groups(fake)
    r = run(monkeypatch, fake, check_mode=True, cluster="smb-office", name="alice", groups=["nope"])
    assert r["failed"]
    assert "projects, staff" in r["msg"]


def test_no_managed_users_on_ad_or_gen1(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-ad", kind="active-directory")
    fake.add_cluster("smb-legacy", gen=1)
    for name in ("smb-ad", "smb-legacy"):
        for main in (smb_user.main, smb_group.main):
            r = run(monkeypatch, fake, main=main, cluster=name, name="alice")
            assert r["failed"]
            assert "generation-2 clusters without Active Directory" in r["msg"]


def test_create_without_password_warns(monkeypatch):
    fake = SmbCluster()
    cluster_with_groups(fake)
    warnings = []
    monkeypatch.setattr(basic.AnsibleModule, "warn", lambda self, msg: warnings.append(msg))
    r = run(monkeypatch, fake, cluster="smb-office", name="bob")
    assert r["changed"]
    assert "without a password" in " ".join(warnings)


# smb_group --------------------------------------------------------------------


def test_group_sequence(monkeypatch):
    fake = SmbCluster()
    cluster = fake.add_cluster("smb-office")
    spec = dict(main=smb_group.main, cluster="smb-office", name="staff", gid=3010)

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert_only_gets(fake)
    assert cluster["groups"] == []
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(groupname="staff", gid=3010)
    assert r["group"]["gid"] == 3010
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]

    r = run(monkeypatch, fake, **merged(spec, gid=3011))
    assert r["failed"] and "cannot be changed" in r["msg"]

    absent = dict(main=smb_group.main, cluster="smb-office", name="staff", state="absent")
    r = run(monkeypatch, fake, check_mode=True, **absent)
    assert r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, **absent)
    assert r["changed"]
    assert cluster["groups"] == []
    r = run(monkeypatch, fake, **absent)
    assert not r["changed"]
    assert_only_gets(fake)


def test_group_reports_member_names(monkeypatch):
    fake = SmbCluster()
    cluster = cluster_with_groups(fake)
    cluster["users"].append(dict(id=9, username="alice", uid=2001, groupIds=[1]))
    r = run(monkeypatch, fake, main=smb_group.main, cluster="smb-office", name="staff")
    assert not r["changed"]
    assert r["group"]["members"] == ["alice"]


# smb_info ---------------------------------------------------------------------


def test_info_gathers(monkeypatch):
    fake = SmbCluster()
    office = cluster_with_groups(fake)
    share = fake.add_share_row(office, "projects", "/smb/projects")
    fake.acls[share["id"]]["grants"] = [dict(name="staff", group=True, access="READ")]
    fake.add_cluster("smb-ad", kind="active-directory")

    r = run(monkeypatch, fake, main=smb_info.main, check_mode=True)
    assert not r["changed"]
    assert [c["description"] for c in r["clusters"]] == ["smb-office", "smb-ad"]
    assert r["clusters"][0]["shares"][0]["share"] == "projects"
    assert r["clusters"][0]["servers"][0]["hostname"] == "node1"
    assert_only_gets(fake)

    r = run(monkeypatch, fake, main=smb_info.main, gather=["users", "groups", "acls", "details"])
    office_info, ad_info = r["clusters"]
    assert [g["groupname"] for g in office_info["groups"]] == ["staff", "projects"]
    assert office_info["shares"][0]["acl"]["grants"] == [dict(name="staff", group=True, access="READ")]
    assert office_info["detail"]["servers"][0]["server"] == 1
    assert ad_info["users"] == [] and ad_info["groups"] == []

    r = run(monkeypatch, fake, main=smb_info.main, cluster="smb-ad", gather=[])
    assert [c["description"] for c in r["clusters"]] == ["smb-ad"]
    r = run(monkeypatch, fake, main=smb_info.main, cluster="ghost")
    assert r["failed"]
