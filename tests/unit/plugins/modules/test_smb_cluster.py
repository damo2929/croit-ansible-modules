# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import smb_cluster
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_smb import SmbCluster

SECRET = "Sup3r-Secret!"


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, smb_cluster.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def find(fake, name):
    return next((c for c in fake.clusters.values() if c["description"] == name), None)


SIMPLE = dict(
    name="smb-office",
    type="simple",
    servers=[dict(server="node1", nic="eth0"), dict(server="node2", nic="eth1")],
    virtual_ips=["10.0.0.200/24"],
    initial_users=[dict(username="admin", password=SECRET)],
)


def test_full_idempotency_sequence(monkeypatch):
    fake = SmbCluster()

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **SIMPLE)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["before"] == {}
    assert r["diff"]["after"]["servers"] == [dict(server="node1", nic="eth0", vlan=None), dict(server="node2", nic="eth1", vlan=None)]
    assert_only_gets(fake)
    assert find(fake, "smb-office") is None

    # 2. create
    r = run(monkeypatch, fake, **SIMPLE)
    assert r["changed"]
    body = fake.writes()[0].body
    assert fake.writes()[0].path == "/services/smb"
    assert body["description"] == "smb-office"
    assert body["servers"] == [dict(server=1, nic=11, vlan=None), dict(server=2, nic=22, vlan=None)]
    assert body["users"] == [dict(username="admin", password=SECRET)]
    assert body["shares"] == []
    assert r["cluster"]["description"] == "smb-office"
    assert r["task"]["state"] == "FINISHED"
    assert SECRET in fake.passwords

    # 3. re-run: nothing to do (initial_users are create-only)
    r = run(monkeypatch, fake, **SIMPLE)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **SIMPLE)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. update in check mode: VIPs (other notation), snapshots, membership
    update = merged(
        SIMPLE,
        virtual_ips=["10.0.0.201/24", "10.0.0.200/24"],
        ceph_snapshots=True,
        servers=[dict(server="node1", nic="eth0"), dict(server="3", nic="eth0")],
        share_defaults=dict(vfs_objects=["catia", "fruit"]),
    )
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["after"]["virtual_ips"] == ["10.0.0.200/24", "10.0.0.201/24"]
    assert [m["server"] for m in r["diff"]["after"]["servers"]] == ["node1", "node3"]
    assert_only_gets(fake)

    # 6. update: PATCH only the changed fields, add node3, remove node2
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    writes = [(c.method, c.path) for c in fake.writes()]
    cid = find(fake, "smb-office")["serviceId"]
    assert writes == [
        ("PATCH", "/services/smb/%d" % cid),
        ("POST", "/services/smb/%d/servers" % cid),
        ("DELETE", "/services/smb/%d/servers/2" % cid),
    ]
    patch = fake.writes()[0].body
    assert set(patch) == set(["virtualIps", "cephSnapshots", "shareDefaults"])
    assert patch["shareDefaults"] == dict(parameters={}, vfsObjects=["catia", "fruit"], vfsObjectsBefore=[])
    assert len(r["tasks"]) == 3

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, name="smb-office", state="absent", confirm_delete=True)
    assert r["changed"]
    assert r["diff"]["after"] == {}
    assert_only_gets(fake)
    assert find(fake, "smb-office") is not None

    # 9. delete: confirm_delete also confirms croit's "several members" warning
    r = run(monkeypatch, fake, name="smb-office", state="absent", confirm_delete=True)
    assert r["changed"] and not r.get("failed")
    assert [c.query.get("ignoreWarning") for c in fake.writes()] == [None, "del-many"]
    assert find(fake, "smb-office") is None

    # 10. delete again
    r = run(monkeypatch, fake, name="smb-office", state="absent", confirm_delete=True)
    assert not r["changed"]
    assert_only_gets(fake)


def test_secret_never_in_result_or_diff(monkeypatch):
    fake = SmbCluster()
    for check in (True, False):
        r = run(monkeypatch, fake, check_mode=check, **SIMPLE)
        assert SECRET not in repr(r)


def test_delete_requires_confirmation(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-office")
    for check in (True, False):
        r = run(monkeypatch, fake, check_mode=check, name="smb-office", state="absent")
        assert r["failed"]
        assert "confirm_delete" in r["msg"]
    assert_only_gets(fake)


def test_cluster_by_service_id(monkeypatch):
    fake = SmbCluster()
    cluster = fake.add_cluster("smb-office")
    r = run(monkeypatch, fake, name=str(cluster["serviceId"]), virtual_ips=["10.0.0.200/24"])
    assert not r["changed"] and not r.get("failed")


def test_type_cannot_change(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-office")
    r = run(monkeypatch, fake, check_mode=True, name="smb-office", type="active_directory")
    assert r["failed"]
    assert "cannot be changed" in r["msg"]
    assert_only_gets(fake)


def test_ad_options_rejected_on_simple(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-office")
    r = run(monkeypatch, fake, name="smb-office", domain_controller="dc02")
    assert r["failed"]
    assert "active_directory" in r["msg"]


def test_member_interface_change_fails(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-office", servers=[(2, 21, None)])
    r = run(monkeypatch, fake, name="smb-office", servers=[dict(server="node2", nic="eth1")])
    assert r["failed"]
    assert "Remove the server" in r["msg"]
    assert_only_gets(fake)


def test_unknown_vlan_fails(monkeypatch):
    fake = SmbCluster()
    r = run(monkeypatch, fake, **merged(SIMPLE, servers=[dict(server="node1", nic="eth0", vlan=99)]))
    assert r["failed"]
    assert "no VLAN 99" in r["msg"]


def test_empty_servers_rejected(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-office")
    r = run(monkeypatch, fake, name="smb-office", servers=[])
    assert r["failed"]
    assert "state=absent" in r["msg"]


AD = dict(
    name="smb-ad",
    type="active_directory",
    servers=[dict(server="node1", nic="eth0", vlan=20)],
    virtual_ips=["10.0.0.210/24"],
    domain="MY-ORG.LOCAL",
    netbios_domain_name="MY-ORG",
    domain_controller="dc01",
    service_dns_name="files",
    domain_admin_user="Administrator",
    domain_admin_password=SECRET,
)


def test_ad_create_and_rerun(monkeypatch):
    fake = SmbCluster()
    r = run(monkeypatch, fake, **AD)
    assert r["changed"]
    call = fake.writes()[0]
    assert call.path == "/services/smb/active-directory-authentication"
    assert call.body["servers"] == [dict(server=1, nic=11, vlan=20, domainAdminUser="Administrator", domainAdminPassword=SECRET)]
    assert call.body["dnsServers"] == []
    assert SECRET not in repr(r)
    r = run(monkeypatch, fake, **AD)
    assert not r["changed"]
    assert_only_gets(fake)


def test_ad_create_needs_credentials(monkeypatch):
    fake = SmbCluster()
    r = run(monkeypatch, fake, check_mode=True, **merged(AD, domain_admin_password=None))
    assert r["failed"]
    assert "domain_admin_password" in r["msg"]


def test_ad_domain_is_immutable(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-ad", kind="active-directory")
    r = run(monkeypatch, fake, name="smb-ad", domain="OTHER.LOCAL")
    assert r["failed"]
    assert "cannot be changed" in r["msg"]


def test_ad_dns_name_change_needs_confirm_and_credentials(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-ad", kind="active-directory")
    r = run(monkeypatch, fake, name="smb-ad", service_dns_name="share")
    assert r["failed"] and "confirm_action" in r["msg"]
    r = run(monkeypatch, fake, name="smb-ad", service_dns_name="share", confirm_action=True)
    assert r["failed"] and "domain_admin_user" in r["msg"]
    assert_only_gets(fake)
    r = run(
        monkeypatch, fake, check_mode=True, name="smb-ad", service_dns_name="share", confirm_action=True,
        domain_admin_user="Administrator", domain_admin_password=SECRET,
    )
    assert r["changed"]
    assert_only_gets(fake)
    r = run(
        monkeypatch, fake, name="smb-ad", service_dns_name="share", confirm_action=True,
        domain_admin_user="Administrator", domain_admin_password=SECRET,
    )
    assert r["changed"]
    assert fake.writes()[0].path.endswith("/service-dns-name")
    assert SECRET not in repr(r)
    r = run(monkeypatch, fake, name="smb-ad", service_dns_name="share", confirm_action=True)
    assert not r["changed"]


def test_ad_adding_member_needs_credentials(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-ad", kind="active-directory")
    r = run(monkeypatch, fake, name="smb-ad", servers=[dict(server="node1", nic="eth0"), dict(server="node3", nic="eth0")])
    assert r["failed"] and "domain_admin" in r["msg"]


def test_migration_needs_confirm_action(monkeypatch):
    fake = SmbCluster()
    cluster = fake.add_cluster("smb-legacy", gen=1)
    fake.add_share_row(cluster, "data", "/smb/data")
    r = run(monkeypatch, fake, name="smb-legacy", generation=2)
    assert r["failed"] and "confirm_action" in r["msg"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, check_mode=True, name="smb-legacy", generation=2, confirm_action=True)
    assert r["changed"]
    assert r["diff"]["after"]["generation"] == 2
    assert_only_gets(fake)
    r = run(monkeypatch, fake, name="smb-legacy", generation=2, confirm_action=True, migrate_posix_shares=["data"])
    assert r["changed"]
    call = fake.writes()[0]
    assert call.path.endswith("/migrate-generation")
    assert call.body == dict(posixShareIds=[cluster["shares"][0]["id"]])
    r = run(monkeypatch, fake, name="smb-legacy", generation=2, confirm_action=True)
    assert not r["changed"]
    assert_only_gets(fake)


def test_interrupted_migration_is_resumed(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-half", gen=2, migrationInProgress=True)
    r = run(monkeypatch, fake, name="smb-half", generation=2, confirm_action=True)
    assert r["changed"]
    assert fake.writes()[0].path.endswith("/migrate-generation")


def test_gen2_options_on_gen1_fail(monkeypatch):
    fake = SmbCluster()
    fake.add_cluster("smb-legacy", gen=1)
    r = run(monkeypatch, fake, name="smb-legacy", global_parameters=dict(foo="bar"))
    assert r["failed"]
    assert "generation-2" in r["msg"]


def test_no_wait_returns_task_without_reading_back(monkeypatch):
    fake = SmbCluster()
    r = run(monkeypatch, fake, wait=False, **SIMPLE)
    assert r["changed"]
    assert r["cluster"] == {}
    assert r["task"]["id"]
