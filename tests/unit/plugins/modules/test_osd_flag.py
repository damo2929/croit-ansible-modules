# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import osd_flag
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module


class FlagCluster(FakeCroit):
    def __init__(self):
        super(FlagCluster, self).__init__()
        self.flags = dict(noout=False, noscrub=False, norebalance=False, pause=False)
        self.route(
            "GET",
            "/maintenance/flags",
            lambda call: (
                200,
                [dict(name=k, description="", recommendedState=False, currentState=v) for k, v in self.flags.items()],
            ),
        )
        self.route("PUT", "/maintenance/flags/(?P<flag>[^/]+)/(?P<action>set|unset)", self.toggle)

    def toggle(self, call, flag, action):
        self.flags[flag] = action == "set"
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, osd_flag.main, check_mode=check_mode, **params)


def test_full_sequence(monkeypatch):
    """set = create, adding a flag = update, unset = delete."""
    fake = FlagCluster()

    r = run(monkeypatch, fake, check_mode=True, flags=["noout"])
    assert r["changed"]
    assert r["diff"] == dict(before=dict(noout=False), after=dict(noout=True))
    assert fake.writes() == [] and not fake.flags["noout"]

    r = run(monkeypatch, fake, flags=["noout"])
    assert r["changed"]
    assert [c.path for c in fake.writes()] == ["/maintenance/flags/noout/set"]
    assert fake.flags["noout"]

    for check in (False, True):
        r = run(monkeypatch, fake, check_mode=check, flags=["noout"])
        assert not r["changed"] and fake.writes() == []

    both = dict(flags=["noout", "norebalance"])
    r = run(monkeypatch, fake, check_mode=True, **both)
    assert r["changed"] and fake.writes() == []
    r = run(monkeypatch, fake, **both)
    assert [c.path for c in fake.writes()] == ["/maintenance/flags/norebalance/set"]
    r = run(monkeypatch, fake, **both)
    assert not r["changed"] and fake.writes() == []

    clear = dict(flags=["noout", "norebalance"], state="absent")
    r = run(monkeypatch, fake, check_mode=True, **clear)
    assert r["changed"] and fake.writes() == []
    assert fake.flags["noout"]
    r = run(monkeypatch, fake, **clear)
    assert r["changed"]
    assert sorted(c.path for c in fake.writes()) == ["/maintenance/flags/noout/unset", "/maintenance/flags/norebalance/unset"]
    assert not any(r_["currentState"] for r_ in r["flags"])
    r = run(monkeypatch, fake, **clear)
    assert not r["changed"] and fake.writes() == []


def test_single_flag_alias_and_duplicates(monkeypatch):
    fake = FlagCluster()
    r = run(monkeypatch, fake, flag="noscrub")
    assert r["changed"]
    r = run(monkeypatch, fake, flags=["noscrub", "noscrub"], state="absent")
    assert len(fake.writes()) == 1


def test_unknown_flag(monkeypatch):
    fake = FlagCluster()
    r = run(monkeypatch, fake, flags=["noout", "nosuchflag"])
    assert r["failed"]
    assert "nosuchflag" in r["msg"] and "noscrub" in r["msg"]
    assert fake.writes() == []
