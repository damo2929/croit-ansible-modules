# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import rbd_namespace
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_rbd import MIB, RbdCluster


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, rbd_namespace.main, check_mode=check_mode, **params)


def test_idempotency_sequence(monkeypatch):
    """The standard sequence; a namespace has no updatable fields, so steps 5-7 do not apply."""
    fake = RbdCluster()
    spec = dict(pool="rbd", name="tenant")

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"] == dict(before={}, after=dict(namespace="tenant"))
    assert fake.writes() == []
    assert fake.namespaces["rbd"] == set()

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["namespaces"] == ["tenant"]

    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert fake.writes() == []

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert fake.writes() == []

    r = run(monkeypatch, fake, check_mode=True, state="absent", **spec)
    assert r["changed"]
    assert fake.writes() == []
    assert fake.namespaces["rbd"] == set(["tenant"])

    r = run(monkeypatch, fake, state="absent", **spec)
    assert r["changed"]
    assert r["namespaces"] == []

    r = run(monkeypatch, fake, state="absent", **spec)
    assert not r["changed"]
    assert fake.writes() == []


def test_non_empty_namespace_delete_fails(monkeypatch):
    fake = RbdCluster()
    fake.add_image("rbd", "disk", MIB, namespace="tenant")
    r = run(monkeypatch, fake, pool="rbd", name="tenant", state="absent")
    assert r["failed"]
    assert "not empty" in r["msg"]
