# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.croit.ceph.plugins.modules import server_ssh_keys
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

ALICE = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAlice alice@ops"
BOB = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBob bob@ops"
UI_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQUiKey ui@croit"


class KeyCluster(FakeCroit):
    def __init__(self, keys=None):
        super(KeyCluster, self).__init__()
        self.keys = list(keys or [])
        self.route("GET", "/server-access/keys", lambda call: (200, list(self.keys)))
        self.route("PUT", "/server-access/keys", self.put)

    def put(self, call):
        self.keys = list(call.body["keys"])
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, server_ssh_keys.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "unexpected writes: %r" % fake.writes()


def test_full_idempotency_sequence(monkeypatch):
    fake = KeyCluster([UI_KEY])

    r = run(monkeypatch, fake, check_mode=True, keys=[ALICE])
    assert r["changed"]
    assert r["diff"]["after"]["keys"] == [UI_KEY, ALICE]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, keys=[ALICE])
    assert r["changed"]
    assert fake.keys == [UI_KEY, ALICE]
    assert r["ssh_keys"] == [UI_KEY, ALICE]

    r = run(monkeypatch, fake, keys=[ALICE])
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, keys=[ALICE])
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, keys=[ALICE, BOB], exclusive=True)
    assert r["changed"]
    assert r["diff"]["after"]["keys"] == [ALICE, BOB]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, keys=[ALICE, BOB], exclusive=True)
    assert r["changed"]
    assert fake.keys == [ALICE, BOB]

    r = run(monkeypatch, fake, keys=[BOB, ALICE], exclusive=True)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, keys=[BOB], state="absent")
    assert r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, keys=[BOB], state="absent")
    assert r["changed"]
    assert fake.keys == [ALICE]

    r = run(monkeypatch, fake, keys=[BOB], state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


@pytest.mark.parametrize(
    "variant",
    [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAlice",
        "ssh-ed25519   AAAAC3NzaC1lZDI1NTE5AAAAIAlice   other comment",
        'from="10.0.0.0/8" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAlice alice@ops',
    ],
)
def test_comment_options_and_whitespace_ignored(monkeypatch, variant):
    fake = KeyCluster([ALICE])
    r = run(monkeypatch, fake, keys=[variant])
    assert not r["changed"]
    r = run(monkeypatch, fake, keys=[variant], state="absent")
    assert r["changed"]
    assert fake.keys == []


def test_duplicates_in_input_added_once(monkeypatch):
    fake = KeyCluster()
    run(monkeypatch, fake, keys=[ALICE, ALICE + " again"])
    assert fake.keys == [ALICE]


def test_exclusive_with_absent_fails(monkeypatch):
    r = run(monkeypatch, KeyCluster(), keys=[ALICE], state="absent", exclusive=True)
    assert r["failed"]


def test_exclusive_empty_removes_all(monkeypatch):
    fake = KeyCluster([ALICE, UI_KEY])
    r = run(monkeypatch, fake, keys=[], exclusive=True)
    assert r["changed"]
    assert fake.keys == []
