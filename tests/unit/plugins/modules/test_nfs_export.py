# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import nfs_export
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_nfs import NfsCroit, assert_only_gets


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, nfs_export.main, check_mode=check_mode, **params)


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def cluster(implementation="ganesha"):
    fake = NfsCroit()
    sid = fake.add_cluster("nfs", [1, 2], implementation)
    return fake, sid


def test_full_idempotency_sequence(monkeypatch):
    fake, sid = cluster()
    spec = dict(
        cluster="nfs",
        nfs_path="/projects",
        path="/volumes/_nogroup/projects",
        volume="cephfs",
        access=[dict(subnet="10.0.0.0/24", rw=True), dict(subnet="10.1.0.0/16")],
    )

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"]["access"] == [dict(subnet="10.0.0.0/24", rw=True), dict(subnet="10.1.0.0/16", rw=False)]
    assert r["diff"]["after"]["nfs4"] is True and r["diff"]["after"]["nfs3"] is False
    assert_only_gets(fake)
    assert not fake.clusters[sid]["exports"]

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["export"]["nfsPath"] == "/projects"
    assert fake.writes()[0].body["volume"] == "cephfs"

    # 3. re-run (access in another order, a host bit set, trailing slash on the path)
    again = merged(spec, nfs_path="/projects/", access=[dict(subnet="10.1.2.3/16"), dict(subnet="10.0.0.0/24", rw=True)])
    r = run(monkeypatch, fake, **again)
    assert not r["changed"], r.get("diff")
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode
    update = merged(spec, access=[dict(subnet="10.0.0.0/24", rw=True)], nfs3=True)
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["nfs3"] is False and r["diff"]["after"]["nfs3"] is True
    assert len(r["diff"]["after"]["access"]) == 1
    assert_only_gets(fake)

    # 6. update: the PUT carries the whole merged export, never the volume
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    put = fake.writes()[0]
    assert put.method == "PUT"
    assert put.body == dict(
        nfsPath="/projects",
        path="/volumes/_nogroup/projects",
        access=[dict(subnet="10.0.0.0/24", rw=True)],
        protocols=dict(nfs3=True, nfs4=True),
    )

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, cluster="nfs", nfs_path="/projects", state="absent")
    assert r["changed"]
    assert_only_gets(fake)
    assert fake.clusters[sid]["exports"]

    # 9. delete (no data is lost, so no confirmation)
    r = run(monkeypatch, fake, cluster="nfs", nfs_path="/projects", state="absent")
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["DELETE"]
    assert not fake.clusters[sid]["exports"]

    # 10. delete again
    r = run(monkeypatch, fake, cluster="nfs", nfs_path="/projects", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_unset_options_are_left_alone(monkeypatch):
    fake, sid = cluster()
    run(monkeypatch, fake, cluster="nfs", nfs_path="/a", path="/a", volume="cephfs", nfs3=True)
    r = run(monkeypatch, fake, cluster=str(sid), nfs_path="/a")
    assert not r["changed"]
    assert_only_gets(fake)


def test_ganesha_needs_volume_and_croit_nfs_refuses_it(monkeypatch):
    fake, sid = cluster("ganesha")
    r = run(monkeypatch, fake, check_mode=True, cluster="nfs", nfs_path="/a", path="/a")
    assert r["failed"] and "volume is required" in r["msg"]
    fake, sid = cluster("croit_nfs")
    r = run(monkeypatch, fake, cluster="nfs", nfs_path="/a", path="/a", volume="cephfs")
    assert r["failed"] and "leave volume unset" in r["msg"]
    r = run(monkeypatch, fake, cluster="nfs", nfs_path="/a", path="/a")
    assert r["changed"]
    assert "volume" not in fake.writes()[0].body


def test_volume_is_immutable(monkeypatch):
    fake, sid = cluster()
    run(monkeypatch, fake, cluster="nfs", nfs_path="/a", path="/a", volume="cephfs")
    r = run(monkeypatch, fake, check_mode=True, cluster="nfs", nfs_path="/a", volume="other")
    assert r["failed"] and "cannot be changed" in r["msg"]
    assert_only_gets(fake)


def test_create_needs_path_and_a_protocol(monkeypatch):
    fake, sid = cluster()
    r = run(monkeypatch, fake, cluster="nfs", nfs_path="/a", volume="cephfs")
    assert r["failed"] and "path is required" in r["msg"]
    r = run(monkeypatch, fake, cluster="nfs", nfs_path="/a", path="/a", volume="cephfs", nfs4=False)
    assert r["failed"] and "NFSv3, NFSv4" in r["msg"]
    assert_only_gets(fake)


def test_unknown_cluster_fails(monkeypatch):
    fake, sid = cluster()
    r = run(monkeypatch, fake, cluster="ghost", nfs_path="/a")
    assert r["failed"] and "nfs (%d)" % sid in r["msg"]
