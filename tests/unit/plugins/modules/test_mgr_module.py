# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import mgr_module
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module


class MgrCluster(FakeCroit):
    """Fake croit with a few manager modules and their options."""

    def __init__(self):
        super(MgrCluster, self).__init__()
        self.modules = dict(
            prometheus=dict(name="prometheus", enabled=False, alwaysOn=False, canRun=True),
            pg_autoscaler=dict(name="pg_autoscaler", enabled=True, alwaysOn=True, canRun=True),
            balancer=dict(name="balancer", enabled=False, alwaysOn=True, canRun=True),
        )
        self.options = dict(
            prometheus=dict(server_port=dict(type="int", value=None, default="9283"), cache=dict(type="bool", value="True")),
            pg_autoscaler=dict(sleep_interval=dict(type="secs", value="60")),
            balancer=dict(),
        )
        self.route("GET", "/modules", lambda call: (200, dict(data=[copy.deepcopy(m) for m in self.modules.values()], total=3, after=0)))
        self.route("GET", "/modules/(?P<name>[^/]+)", self.get_options)
        self.route("PATCH", "/modules/(?P<name>[^/]+)", self.patch)
        self.route("POST", "/modules/(?P<name>[^/]+)/(?P<action>enable|disable)", self.toggle)

    def get_options(self, call, name):
        rows = [dict(name=k, description="", type=v["type"], level="basic", value=v["value"]) for k, v in self.options[name].items()]
        return 200, rows

    def patch(self, call, name):
        for key, value in call.body.items():
            self.options[name][key]["value"] = None if value is None else (str(value) if not isinstance(value, bool) else str(value).lower())
        return 204, None

    def toggle(self, call, name, action):
        if name == "balancer" and action == "enable" and call.query.get("ignoreWarning") != "b":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="b", warningText="Pre-Luminous clients are incompatible"))
        self.modules[name]["enabled"] = action == "enable"
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, mgr_module.main, check_mode=check_mode, **params)


def test_full_sequence(monkeypatch):
    """enable+configure = create, change option = update, disable = delete."""
    fake = MgrCluster()
    spec = dict(name="prometheus", enabled=True, options=dict(server_port=9284))

    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["before"] == dict(enabled=False, options=dict(server_port=None))
    assert r["diff"]["after"] == dict(enabled=True, options=dict(server_port="9284"))
    assert fake.writes() == []

    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert [(c.method, c.path, c.body) for c in fake.writes()] == [
        ("PATCH", "/modules/prometheus", dict(server_port=9284)),
        ("POST", "/modules/prometheus/enable", None),
    ]
    assert r["module"]["enabled"] is True
    assert r["options"] == dict(server_port="9284")

    for check in (False, True):
        r = run(monkeypatch, fake, check_mode=check, **spec)
        assert not r["changed"]
        assert fake.writes() == []

    update = dict(name="prometheus", options=dict(server_port=9285))
    r = run(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"] and fake.writes() == []
    assert fake.options["prometheus"]["server_port"]["value"] == "9284"
    r = run(monkeypatch, fake, **update)
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["PATCH"]
    r = run(monkeypatch, fake, **update)
    assert not r["changed"] and fake.writes() == []

    disable = dict(name="prometheus", enabled=False)
    r = run(monkeypatch, fake, check_mode=True, **disable)
    assert r["changed"] and fake.writes() == []
    assert fake.modules["prometheus"]["enabled"]
    r = run(monkeypatch, fake, **disable)
    assert r["changed"]
    assert [c.path for c in fake.writes()] == ["/modules/prometheus/disable"]
    r = run(monkeypatch, fake, **disable)
    assert not r["changed"] and fake.writes() == []


def test_bool_options_case_insensitive(monkeypatch):
    fake = MgrCluster()
    r = run(monkeypatch, fake, name="prometheus", options=dict(cache=True))
    assert not r["changed"]
    r = run(monkeypatch, fake, name="prometheus", options=dict(cache=False))
    assert r["changed"]
    assert fake.writes()[0].body == dict(cache=False)


def test_null_clears_option(monkeypatch):
    fake = MgrCluster()
    r = run(monkeypatch, fake, name="pg_autoscaler", options=dict(sleep_interval=None))
    assert r["changed"]
    assert fake.writes()[0].body == dict(sleep_interval=None)
    r = run(monkeypatch, fake, name="pg_autoscaler", options=dict(sleep_interval=None))
    assert not r["changed"]


def test_unknown_module_and_option(monkeypatch):
    fake = MgrCluster()
    r = run(monkeypatch, fake, name="nope", enabled=True)
    assert r["failed"] and "prometheus" in r["msg"]
    r = run(monkeypatch, fake, name="prometheus", options=dict(bogus=1))
    assert r["failed"] and "server_port" in r["msg"]
    assert fake.writes() == []


def test_always_on_cannot_be_disabled(monkeypatch):
    fake = MgrCluster()
    r = run(monkeypatch, fake, name="pg_autoscaler", enabled=False)
    assert r["failed"]
    assert fake.writes() == []


def test_balancer_toggles_with_warning(monkeypatch):
    fake = MgrCluster()
    r = run(monkeypatch, fake, name="balancer", enabled=True)
    assert r["failed"]
    assert "Pre-Luminous" in r["warning"]
    r = run(monkeypatch, fake, name="balancer", enabled=True, ignore_warnings=True)
    assert r["changed"]
    assert fake.modules["balancer"]["enabled"]
    # always-on, but croit can switch the balancer off
    r = run(monkeypatch, fake, name="balancer", enabled=False)
    assert r["changed"]
    assert not fake.modules["balancer"]["enabled"]
