# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import nvmeof_disk
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_nvmeof import NvmeofCluster

GIB = 1024 ** 3
SUB1 = "nqn.2016-06.io.spdk:ds1"
SUB2 = "nqn.2016-06.io.spdk:ds2"


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, nvmeof_disk.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def merged(base, **overrides):
    result = dict(base)
    result.update(overrides)
    return result


def cluster():
    fake = NvmeofCluster()
    gid = fake.seed_gateway("gw")
    fake.seed_subsystem(gid, SUB1)
    fake.seed_subsystem(gid, SUB2)
    return fake


def disk(fake, image="vm1"):
    return next((d for d in fake.disks.values() if d["image"] == image), None)


SPEC = dict(gateway="gw", pool="rbd", image="vm1", block_size=4096, subsystems=[SUB1])


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()

    # 1. export in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert r["changed"] and r["diff"]["after"]["subsystems"] == [SUB1]
    assert_only_gets(fake)
    assert disk(fake) is None

    # 2. export
    r = run(monkeypatch, fake, **SPEC)
    assert r["changed"]
    body = fake.writes()[0].body
    assert body["type"] == "CEPH" and body["blockSize"] == 4096 and len(body["subsystems"]) == 1
    assert r["disk"]["subsystemNqns"] == [SUB1]

    # 3. re-run
    r = run(monkeypatch, fake, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. grow + attach in check mode
    update = merged(SPEC, size="20G", subsystems=[SUB1, SUB2])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["size"] == 10 * GIB and r["diff"]["after"]["size"] == 20 * GIB
    assert r["diff"]["after"]["subsystems"] == [SUB1, SUB2]
    assert_only_gets(fake)

    # 6. grow + attach
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["PATCH", "POST"]
    assert fake.writes()[0].body == dict(size=20 * GIB)
    assert disk(fake)["size"] == 20 * GIB

    # 7. again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. remove in check mode
    gone = dict(gateway="gw", pool="rbd", image="vm1", state="absent", confirm_delete=True)
    r = run(monkeypatch, fake, check_mode=True, **gone)
    assert r["changed"] and not r["image_deleted"]
    assert_only_gets(fake)

    # 9. remove, keeping the image
    r = run(monkeypatch, fake, **gone)
    assert r["changed"]
    assert fake.writes()[0].body == dict(deleteData=False)
    assert disk(fake) is None and ("rbd", "vm1") in fake.images

    # 10. remove again
    r = run(monkeypatch, fake, **gone)
    assert not r["changed"]
    assert_only_gets(fake)


def test_delete_requires_confirmation(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1")
    for check_mode in (True, False):
        r = run(monkeypatch, fake, check_mode=check_mode, gateway="gw", pool="rbd", image="vm1", state="absent")
        assert r["failed"] and "confirm_delete" in r["msg"]
        assert_only_gets(fake)


def test_delete_image_too(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm2")
    r = run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm2", state="absent", confirm_delete=True, delete_image=True)
    assert r["changed"] and r["image_deleted"]
    assert fake.writes()[0].body == dict(deleteData=True)
    assert fake.deleted_images == ["rbd/vm2"]


def test_shrink_refused(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1")
    for check_mode in (True, False):
        r = run(monkeypatch, fake, check_mode=check_mode, gateway="gw", pool="rbd", image="vm1", size="5G")
        assert r["failed"] and "shrink" in r["msg"]
        assert_only_gets(fake)


def test_size_rounded_up_to_mib(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1")
    r = run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1", size=str(10 * GIB + 1))
    assert r["changed"] and fake.writes()[0].body == dict(size=10 * GIB + 1024 * 1024)


def test_unreadable_size_fails(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1")
    d = disk(fake)
    d["size"] = None
    d["hints"] = [dict(message="image not readable")]
    r = run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1", size="20G")
    assert r["failed"] and "image not readable" in r["msg"]


def test_create_only_fields_fail_on_change(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1", block_size=512)
    r = run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1", block_size=4096)
    assert r["failed"] and "cannot be changed" in r["msg"]
    r = run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1", cluster="other")
    assert r["failed"] and "cannot be changed" in r["msg"]
    assert_only_gets(fake)


def test_unknown_subsystem_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm1", subsystems=["nqn.ghost"])
    assert r["failed"] and SUB1 in r["msg"]
    assert_only_gets(fake)


def test_missing_image_surfaces_croit_error(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, gateway="gw", pool="rbd", image="ghost")
    assert r["failed"] and "does not exist" in r["msg"]


def test_size_on_create_grows_after_export(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, gateway="gw", pool="rbd", image="vm3", size="50G")
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["POST", "PATCH"]
    assert disk(fake, "vm3")["size"] == 50 * GIB
