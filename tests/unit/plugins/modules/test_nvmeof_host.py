# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import nvmeof_host
from ansible_collections.croit.ceph.tests.unit.fake_croit import run_module
from ansible_collections.croit.ceph.tests.unit.plugins.modules.fake_nvmeof import NvmeofCluster

HOST = "nqn.2014-08.org.nvmexpress:uuid:esxi-01"
SUB1 = "nqn.2016-06.io.spdk:ds1"
SUB2 = "nqn.2016-06.io.spdk:ds2"
KEY1 = "DHHC-1:00:c2VjcmV0LWtleS1vbmU=:"
KEY2 = "DHHC-1:00:c2VjcmV0LWtleS10d28=:"


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, nvmeof_host.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def assert_no_secret(result):
    text = repr(result)
    assert KEY1 not in text and KEY2 not in text


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


def host(fake):
    return next((h for h in fake.hosts.values() if h["nqn"] == HOST), None)


SPEC = dict(gateway="gw", nqn=HOST, shared_key=KEY1, subsystems=[SUB1])


def test_full_idempotency_sequence(monkeypatch):
    fake = cluster()

    # 1. add in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert r["changed"]
    assert r["diff"]["after"]["shared_key"] == "******** (changed)"
    assert_only_gets(fake)
    assert_no_secret(r)
    assert host(fake) is None

    # 2. add
    r = run(monkeypatch, fake, **SPEC)
    assert r["changed"]
    assert fake.writes()[0].body["sharedKey"] == KEY1
    assert host(fake)["sharedKey"] == KEY1 and len(host(fake)["subsystems"]) == 1
    assert r["host"]["sharedKey"] == "********"
    assert_no_secret(r)

    # 3. re-run: the readable key is compared directly
    r = run(monkeypatch, fake, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 4. re-run in check mode
    r = run(monkeypatch, fake, check_mode=True, **SPEC)
    assert not r["changed"]
    assert_only_gets(fake)

    # 5. rotate the key and attach a second subsystem in check mode
    update = merged(SPEC, shared_key=KEY2, subsystems=[SUB1, SUB2])
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert r["diff"]["before"]["shared_key"] == "********"
    assert r["diff"]["after"]["shared_key"] == "******** (changed)"
    assert r["diff"]["after"]["subsystems"] == [SUB1, SUB2]
    assert_only_gets(fake)
    assert_no_secret(r)

    # 6. apply
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["PUT", "POST"]
    assert host(fake)["sharedKey"] == KEY2
    assert_no_secret(r)

    # 7. again
    r = run(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)

    # 8. revoke in check mode
    gone = dict(gateway="gw", nqn=HOST, state="absent")
    r = run(monkeypatch, fake, check_mode=True, **gone)
    assert r["changed"]
    assert_only_gets(fake)
    assert host(fake) is not None

    # 9. revoke
    r = run(monkeypatch, fake, **gone)
    assert r["changed"] and [c.method for c in fake.writes()] == ["DELETE"]
    assert host(fake) is None

    # 10. revoke again
    r = run(monkeypatch, fake, **gone)
    assert not r["changed"]
    assert_only_gets(fake)


def test_masked_key_uses_update_shared_key(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", nqn=HOST, shared_key=KEY1)
    fake.mask_keys = True
    r = run(monkeypatch, fake, gateway="gw", nqn=HOST, shared_key=KEY2)
    assert not r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, gateway="gw", nqn=HOST, shared_key=KEY2, update_shared_key="always")
    assert r["changed"] and host(fake)["sharedKey"] == KEY2
    assert_no_secret(r)


def test_remove_key(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", nqn=HOST, shared_key=KEY1)
    r = run(monkeypatch, fake, gateway="gw", nqn=HOST, shared_key="")
    assert r["changed"] and fake.writes()[0].body == {}
    assert r["diff"]["after"]["shared_key"] is None
    assert host(fake)["sharedKey"] is None
    r = run(monkeypatch, fake, gateway="gw", nqn=HOST, shared_key="")
    assert not r["changed"]


def test_key_left_alone_when_unset(monkeypatch):
    fake = cluster()
    run(monkeypatch, fake, gateway="gw", nqn=HOST, shared_key=KEY1)
    r = run(monkeypatch, fake, gateway="gw", nqn=HOST)
    assert not r["changed"]
    assert host(fake)["sharedKey"] == KEY1


def test_unknown_subsystem_fails(monkeypatch):
    fake = cluster()
    r = run(monkeypatch, fake, gateway="gw", nqn=HOST, subsystems=["nqn.ghost"])
    assert r["failed"] and SUB1 in r["msg"]
    assert_only_gets(fake)
