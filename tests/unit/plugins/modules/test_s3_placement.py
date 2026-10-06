# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import s3_placement
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_rgw import RgwCluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, s3_placement.main, check_mode=check_mode, **params)


def row(fake, name, sc="STANDARD"):
    rows = [p for p in fake.placements if p["name"] == name and p["storageClass"] == sc]
    return rows[0] if rows else None


def test_full_idempotency_sequence(monkeypatch):
    fake = RgwCluster()
    spec = dict(name="ec", data_pool="rgw-ec", index_pool="rgw-index")

    # 1./2. create
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and fake.writes() == [] and row(fake, "ec") is None
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(dataPool="rgw-ec", indexPool="rgw-index")
    assert r["placement"]["dataPool"] == "rgw-ec"
    # 3./4. again
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"] and fake.writes() == []
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"] and fake.writes() == []
    # 5./6./7. make it the default
    r = run(monkeypatch, fake, check_mode=True, default=True, **spec)
    assert r["changed"] and fake.writes() == []
    assert r["diff"]["before"]["default"] is False and r["diff"]["after"]["default"] is True
    r = run(monkeypatch, fake, default=True, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(placementRule="ec", storageClass="STANDARD")
    assert row(fake, "ec")["isDefault"] and not row(fake, "default-placement")["isDefault"]
    r = run(monkeypatch, fake, default=True, **spec)
    assert not r["changed"] and fake.writes() == []
    # 8./9./10. delete (the default needs the warning confirmed)
    r = run(monkeypatch, fake, check_mode=True, name="ec", state="absent", confirm_delete=True)
    assert r["changed"] and fake.writes() == [] and row(fake, "ec")
    r = run(monkeypatch, fake, name="ec", state="absent", confirm_delete=True, ignore_warnings=True)
    assert r["changed"] and row(fake, "ec") is None
    r = run(monkeypatch, fake, name="ec", state="absent", confirm_delete=True)
    assert not r["changed"] and fake.writes() == []


def test_storage_class(monkeypatch):
    fake = RgwCluster()
    r = run(monkeypatch, fake, name="default-placement", storage_class="COLD", data_pool="rgw-cold")
    assert r["changed"]
    call = fake.writes()[0]
    assert call.path == "/s3/placements/default-placement/storage-classes/COLD"
    assert call.body == dict(dataPool="rgw-cold")
    r = run(monkeypatch, fake, name="default-placement", storage_class="COLD", data_pool="rgw-cold")
    assert not r["changed"]
    r = run(monkeypatch, fake, name="default-placement", storage_class="COLD", state="absent", confirm_delete=True)
    assert r["changed"] and row(fake, "default-placement", "COLD") is None
    assert row(fake, "default-placement") is not None


def test_storage_class_needs_rule(monkeypatch):
    fake = RgwCluster()
    r = run(monkeypatch, fake, name="nope", storage_class="COLD", data_pool="x")
    assert r["failed"] and "STANDARD" in r["msg"]
    assert fake.writes() == []


def test_pool_change_fails(monkeypatch):
    fake = RgwCluster()
    r = run(monkeypatch, fake, check_mode=True, name="default-placement", data_pool="other")
    assert r["failed"] and "cannot be changed" in r["msg"]
    assert fake.writes() == []


def test_index_pool_only_for_standard(monkeypatch):
    r = run(monkeypatch, RgwCluster(), name="default-placement", storage_class="COLD", data_pool="x", index_pool="y")
    assert r["failed"]


def test_create_requires_data_pool(monkeypatch):
    r = run(monkeypatch, RgwCluster(), name="new")
    assert r["failed"] and "data_pool" in r["msg"]


def test_default_false_on_default_fails(monkeypatch):
    fake = RgwCluster()
    r = run(monkeypatch, fake, name="default-placement", default=False)
    assert r["failed"] and "cannot unset" in r["msg"]


def test_delete_requires_confirm(monkeypatch):
    fake = RgwCluster()
    r = run(monkeypatch, fake, check_mode=True, name="default-placement", state="absent")
    assert r["failed"] and "confirm_delete" in r["msg"]
    assert "with all its storage classes" in r["msg"]


def test_delete_default_needs_warning(monkeypatch):
    fake = RgwCluster()
    r = run(monkeypatch, fake, name="default-placement", state="absent", confirm_delete=True)
    assert r["failed"] and r["warning"] == "deletes the default"
    assert row(fake, "default-placement")
