# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import rbd_snapshot
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_rbd import MIB, RbdCluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, rbd_snapshot.main, check_mode=check_mode, **params)


def snaps(fake, key=("rbd", None, "disk")):
    return dict((s["name"], s["protect"]) for s in fake.images[key]["snaps"])


def cluster():
    fake = RbdCluster()
    fake.add_image("rbd", "disk", 100 * MIB)
    return fake


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()
    spec = dict(pool="rbd", image="disk", name="s1")

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"] == dict(name="s1", protected=False)
    assert fake.writes() == []
    assert snaps(fake) == {}

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["snapshot"]["name"] == "s1"
    assert snaps(fake) == dict(s1=False)

    # 3. re-run
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert fake.writes() == []

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert fake.writes() == []

    # 5. update (protect) in check mode
    r = run(monkeypatch, fake, check_mode=True, protected=True, **spec)
    assert r["changed"]
    assert r["diff"]["before"]["protected"] is False
    assert r["diff"]["after"]["protected"] is True
    assert fake.writes() == []
    assert snaps(fake) == dict(s1=False)

    # 6. update
    r = run(monkeypatch, fake, protected=True, **spec)
    assert r["changed"]
    assert r["snapshot"]["protect"] is True

    # 7. update again
    r = run(monkeypatch, fake, protected=True, **spec)
    assert not r["changed"]
    assert fake.writes() == []

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, state="absent", confirm_delete=True, **spec)
    assert r["changed"]
    assert fake.writes() == []

    # 9. delete: unprotects first
    r = run(monkeypatch, fake, state="absent", confirm_delete=True, **spec)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["PATCH", "DELETE"]
    assert snaps(fake) == {}

    # 10. delete again
    r = run(monkeypatch, fake, state="absent", confirm_delete=True, **spec)
    assert not r["changed"]
    assert fake.writes() == []


def test_create_protected(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, pool="rbd", image="disk", name="gold", protected=True)
    assert r["changed"]
    assert snaps(fake) == dict(gold=True)


def test_delete_requires_confirmation(monkeypatch):
    fake = cluster()
    fake.images[("rbd", None, "disk")]["snaps"].append(dict(id=1, name="s1", protect=False))
    r = run(monkeypatch, fake, pool="rbd", image="disk", name="s1", state="absent")
    assert r["failed"]
    assert snaps(fake) == dict(s1=False)


def test_missing_image_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, pool="rbd", image="nope", name="s1")
    assert r["failed"]
    assert "does not exist" in r["msg"]


def test_namespace(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", MIB, namespace="t")
    r = run(monkeypatch, fake, pool="rbd", namespace="t", image="disk", name="s1")
    assert r["changed"]
    assert snaps(fake, ("rbd", "t", "disk")) == dict(s1=False)
    assert all(c.query.get("namespace") == "t" for c in fake.calls)
