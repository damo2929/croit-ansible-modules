# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.croit.ceph.plugins.modules import cluster_tuning
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module


class TuningCluster(FakeCroit):
    def __init__(self, min_compat="reef"):
        super(TuningCluster, self).__init__()
        self.speed = 10
        self.ratios = dict(nearfull=0.85, backfillfull=0.9, full=0.95)
        self.min_compat = min_compat
        self.tz = "UTC"
        self.route("GET", "/maintenance/recovery-speed", lambda c: (200, dict(speed=self.speed)))
        self.route("PUT", "/maintenance/recovery-speed", self.put_speed)
        self.route("GET", "/maintenance/osd-full-ratios", lambda c: (200, dict(self.ratios)))
        self.route("PATCH", "/maintenance/osd-full-ratios", self.patch_ratios)
        self.route("GET", "/maintenance/min-compat-client", lambda c: (200, self.min_compat))
        self.route("PUT", "/maintenance/min-compat-client", self.put_min)
        self.route(
            "GET",
            "/maintenance/scheduling-timezone",
            lambda c: (200, dict(timezone=self.tz, options=["UTC", "Europe/Berlin", "America/New_York"])),
        )
        self.route("PATCH", "/maintenance/scheduling-timezone", self.patch_tz)

    def put_speed(self, call):
        self.speed = call.body["speed"]
        return 204, None

    def patch_ratios(self, call):
        self.ratios.update(call.body)
        return 204, None

    def put_min(self, call):
        self.min_compat = call.body["release"]
        return 204, None

    def patch_tz(self, call):
        if call.query.get("ignoreWarning") != "t":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="t", warningText="moves schedules"))
        self.tz = call.body["timezone"]
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, cluster_tuning.main, check_mode=check_mode, **params)


def test_sequence(monkeypatch):
    """Set and change sequence; the knobs cannot be unset, only changed."""
    fake = TuningCluster()
    spec = dict(recovery_speed=3, full_ratios=dict(nearfull=0.8), min_compat_client="squid")
    # 1. set (check)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["before"]["recovery_speed"] == 10
    assert r["diff"]["after"] == dict(
        recovery_speed=3, full_ratios=dict(nearfull=0.8, backfillfull=0.9, full=0.95), min_compat_client="squid"
    )
    assert fake.writes() == []
    # 2. set: only changed thresholds are sent
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    bodies = dict((c.path, c.body) for c in fake.writes())
    assert bodies == {
        "/maintenance/recovery-speed": dict(speed=3),
        "/maintenance/osd-full-ratios": dict(nearfull=0.8),
        "/maintenance/min-compat-client": dict(release="squid"),
    }
    assert r["tuning"]["recovery_speed"] == 3
    # 3. re-set
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"] and fake.writes() == []
    # 4. re-set (check)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"] and fake.writes() == []
    # 5. change (check)
    r = run(monkeypatch, fake, check_mode=True, recovery_speed=5)
    assert r["changed"] and r["diff"] == dict(before=dict(recovery_speed=3), after=dict(recovery_speed=5))
    assert fake.writes() == []
    # 6. change
    r = run(monkeypatch, fake, recovery_speed=5)
    assert r["changed"]
    # 7. change again
    r = run(monkeypatch, fake, recovery_speed=5)
    assert not r["changed"] and fake.writes() == []


def test_unset_options_are_not_read(monkeypatch):
    fake = TuningCluster()
    r = run(monkeypatch, fake, recovery_speed=10)
    assert not r["changed"]
    assert [c.path for c in fake.calls] == ["/maintenance/recovery-speed"]
    assert r["tuning"] == dict(recovery_speed=10)


def test_ratios_rounded(monkeypatch):
    fake = TuningCluster()
    fake.ratios["nearfull"] = 0.8500000001
    r = run(monkeypatch, fake, full_ratios=dict(nearfull=0.849))
    assert not r["changed"]


@pytest.mark.parametrize(
    "ratios",
    [dict(nearfull=0.92), dict(full=0.99), dict(backfillfull=0.96), dict(nearfull=0)],
)
def test_ratio_order_enforced(monkeypatch, ratios):
    fake = TuningCluster()
    r = run(monkeypatch, fake, check_mode=True, full_ratios=ratios)
    assert r["failed"] and "nearfull < backfillfull < full" in r["msg"]
    assert fake.writes() == []


@pytest.mark.parametrize("speed", [0, 11, -1])
def test_speed_range(monkeypatch, speed):
    r = run(monkeypatch, TuningCluster(), recovery_speed=speed)
    assert r["failed"]


def test_min_compat_unset_on_cluster(monkeypatch):
    fake = TuningCluster(min_compat=None)
    r = run(monkeypatch, fake, check_mode=True, min_compat_client="reef")
    assert r["changed"] and r["diff"]["before"] == dict(min_compat_client=None)


def test_timezone_warning_and_validation(monkeypatch):
    fake = TuningCluster()
    r = run(monkeypatch, fake, scheduling_timezone="Mars/Olympus")
    assert r["failed"] and "does not offer" in r["msg"]
    r = run(monkeypatch, fake, check_mode=True, scheduling_timezone="Europe/Berlin")
    assert r["changed"] and fake.writes() == []
    r = run(monkeypatch, fake, scheduling_timezone="Europe/Berlin")
    assert r["failed"] and r["warning"] == "moves schedules"
    r = run(monkeypatch, fake, scheduling_timezone="Europe/Berlin", ignore_warnings=True)
    assert r["changed"] and fake.tz == "Europe/Berlin"
    r = run(monkeypatch, fake, scheduling_timezone="Europe/Berlin")
    assert not r["changed"]


def test_needs_one_option(monkeypatch):
    r = run(monkeypatch, TuningCluster())
    assert r["failed"]
