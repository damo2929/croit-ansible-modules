# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.croit.ceph.plugins.modules import rbd as rbd_module
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_rbd import MIB, RbdCluster

GIB = 1024 * MIB


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, rbd_module.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = RbdCluster()
    spec = dict(pool="rbd", name="disk", size="10G", features=["layering", "exclusive_lock"], qos=dict(rbd_qos_iops_limit=500))

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and not r.get("failed")
    assert r["diff"]["before"] == {}
    assert r["diff"]["after"]["size"] == 10 * GIB
    assert_only_gets(fake)
    assert fake.images == {}

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["image"]["size"] == 10 * GIB
    assert fake.image_qos[("rbd", None, "disk")] == dict(rbd_qos_iops_limit=500)
    create = [c for c in fake.writes() if c.path == "/pools/rbd/rbds"][0]
    assert create.body == dict(name="disk", size=10 * GIB, features=["EXCLUSIVE_LOCK", "LAYERING"])

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
    update.update(size="20G", features=["layering"], qos=dict(rbd_qos_iops_limit=1000))
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["size"] == 10 * GIB
    assert r["diff"]["after"]["size"] == 20 * GIB
    assert r["diff"]["after"]["features"] == ["LAYERING"]
    assert r["diff"]["after"]["qos"] == dict(rbd_qos_iops_limit=1000)
    assert_only_gets(fake)
    assert fake.images[("rbd", None, "disk")]["size"] == 10 * GIB

    # 6. update
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    patch = [c for c in fake.writes() if c.method == "PATCH"]
    assert patch[0].body == dict(size=20 * GIB, features=["LAYERING"])
    assert r["image"]["size"] == 20 * GIB

    # 7. update again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. delete in check mode
    gone = dict(pool="rbd", name="disk", state="absent", confirm_delete=True)
    r = run(monkeypatch, fake, check_mode=True, **gone)
    assert r["changed"]
    assert_only_gets(fake)
    assert ("rbd", None, "disk") in fake.images

    # 9. delete (runs as a task)
    r = run(monkeypatch, fake, **gone)
    assert r["changed"]
    assert r["task"]["state"] == "FINISHED"
    assert fake.images == {}

    # 10. delete again
    r = run(monkeypatch, fake, **gone)
    assert not r["changed"]
    assert_only_gets(fake)


def test_size_rounded_to_mib(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", 10 * MIB)
    r = run(monkeypatch, fake, pool="rbd", name="disk", size=str(10 * MIB - 5))
    assert not r["changed"]


def test_shrink_fails(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", 10 * GIB)
    r = run(monkeypatch, fake, check_mode=True, pool="rbd", name="disk", size="5G")
    assert r["failed"]
    assert "cannot shrink" in r["msg"]
    assert_only_gets(fake)


def test_size_required_for_create(monkeypatch):
    fake = RbdCluster()
    r = run(monkeypatch, fake, pool="rbd", name="disk")
    assert r["failed"]
    assert "size is required" in r["msg"]


def test_unset_options_left_alone(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", GIB, features=["LAYERING", "OBJECT_MAP"])
    r = run(monkeypatch, fake, pool="rbd", name="disk")
    assert not r["changed"]
    assert_only_gets(fake)


def test_feature_order_and_case_do_not_matter(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", GIB, features=["LAYERING", "EXCLUSIVE_LOCK"])
    r = run(monkeypatch, fake, pool="rbd", name="disk", features=["exclusive_lock", "layering"])
    assert not r["changed"]


def test_namespace_image(monkeypatch):
    fake = RbdCluster()
    r = run(monkeypatch, fake, pool="rbd", namespace="tenant", name="disk", size="1G")
    assert r["changed"]
    assert ("rbd", "tenant", "disk") in fake.images
    r = run(monkeypatch, fake, pool="rbd", namespace="tenant", name="disk", size="1G")
    assert not r["changed"]
    assert all(c.query.get("namespace") == "tenant" for c in fake.calls if c.path.startswith("/pools/rbd/rbds/disk"))
    # same name in the default namespace is a different image
    r = run(monkeypatch, fake, check_mode=True, pool="rbd", name="disk", size="1G")
    assert r["changed"]


def test_erasure_coded_pool_is_immutable(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", GIB, ec="ec-a")
    r = run(monkeypatch, fake, pool="rbd", name="disk", erasure_coded_pool="ec-b")
    assert r["failed"]
    assert "cannot be changed" in r["msg"]
    r = run(monkeypatch, fake, pool="rbd", name="disk", erasure_coded_pool="ec-a")
    assert not r["changed"]


def test_delete_requires_confirmation(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", GIB)
    r = run(monkeypatch, fake, pool="rbd", name="disk", state="absent")
    assert r["failed"]
    assert "confirm_delete" in r["msg"]
    assert fake.images


def test_delete_with_snapshots_reports_croit_error(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", GIB, snaps=[dict(id=1, name="s", protect=False)])
    r = run(monkeypatch, fake, pool="rbd", name="disk", state="absent", confirm_delete=True)
    assert r["failed"]
    assert "snapshots" in r["msg"]


def test_clone_and_flatten(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "golden", 5 * GIB, snaps=[dict(id=1, name="v1", protect=True)])
    spec = dict(pool="rbd", name="vm", clone_from=dict(pool="rbd", image="golden", snapshot="v1"))

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"]["parent"] == dict(pool="rbd", image="golden", snapshot="v1")
    assert_only_gets(fake)

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["image"]["parent"] == dict(pool="rbd", image="golden", snapshot="v1")
    assert r["image"]["size"] == 5 * GIB
    assert [c.path for c in fake.writes()] == ["/pools/rbd/rbds/golden/snapshots/v1/clone"]

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]

    r = run(monkeypatch, fake, check_mode=True, flatten=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"]["parent"] is None
    assert_only_gets(fake)

    r = run(monkeypatch, fake, flatten=True, **spec)
    assert r["changed"]
    assert r["task"]["name"] == "Flatten"
    assert r["image"]["parent"] is None

    r = run(monkeypatch, fake, flatten=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)


def test_clone_grown_on_create(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "golden", 5 * GIB, snaps=[dict(id=1, name="v1", protect=True)])
    r = run(
        monkeypatch, fake, pool="rbd", name="vm", size="8G", clone_from=dict(pool="rbd", image="golden", snapshot="v1")
    )
    assert r["changed"]
    assert r["image"]["size"] == 8 * GIB


def test_qos_unknown_key_fails(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", GIB)
    r = run(monkeypatch, fake, pool="rbd", name="disk", qos=dict(rbd_qos_nonsense=1))
    assert r["failed"]
    assert "rbd_qos_iops_limit" in r["msg"]


def test_qos_null_removes_and_size_units(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", GIB)
    fake.image_qos[("rbd", None, "disk")] = dict(rbd_qos_iops_limit=5)
    r = run(monkeypatch, fake, pool="rbd", name="disk", qos=dict(rbd_qos_iops_limit=None, rbd_qos_bps_limit="100M"))
    assert r["changed"]
    assert fake.image_qos[("rbd", None, "disk")] == dict(rbd_qos_bps_limit=100 * MIB)
    r = run(monkeypatch, fake, pool="rbd", name="disk", qos=dict(rbd_qos_iops_limit=None, rbd_qos_bps_limit="100M"))
    assert not r["changed"]


def test_feature_change_warning(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", GIB)
    original = [r for r in fake.routes if r[0] == "PATCH" and r[1].pattern.startswith("^/pools/(?P<pool>")][0]

    def warn(call, **kw):
        if call.query.get("ignoreWarning") != "tok":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="tok", warningText="downtime"))
        return original[2](call, **kw)

    fake.routes.insert(0, ("PATCH", original[1], warn))
    r = run(monkeypatch, fake, pool="rbd", name="disk", features=["layering"])
    assert r["failed"]
    assert r["warning"] == "downtime"
    r = run(monkeypatch, fake, pool="rbd", name="disk", features=["layering"], ignore_warnings=True)
    assert r["changed"]
    assert fake.images[("rbd", None, "disk")]["features"] == ["LAYERING"]


@pytest.mark.parametrize("size", ["0", "abc"])
def test_invalid_size(monkeypatch, size):
    fake = RbdCluster()
    r = run(monkeypatch, fake, pool="rbd", name="disk", size=size)
    assert r["failed"]
