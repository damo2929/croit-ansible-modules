# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

import pytest

from ansible_collections.croit.ceph.plugins.modules import setting, setting_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

DEFAULTS = {
    "graph retention days": ("INT", "30"),
    "send telemetry": ("BOOL", "false"),
    "support email": ("STRING", "support@example.com"),
}


class SettingsCluster(FakeCroit):
    def __init__(self):
        super(SettingsCluster, self).__init__()
        self.stored = {}
        self.serve_tasks()
        self.route("GET", "/settings/available", lambda call: (200, self.rows(all_rows=True)))
        self.route("GET", "/settings", lambda call: (200, self.rows(all_rows=False)))
        self.route("PUT", "/settings", self.put)
        self.route("DELETE", "/settings", self.delete)

    def rows(self, all_rows):
        result = []
        for name, (kind, default) in DEFAULTS.items():
            if not all_rows and name not in self.stored:
                continue
            value = self.stored.get(name, default)
            result.append(
                dict(name=name, type=kind, level="SIMPLE", value=value, default=default, customized=name in self.stored)
            )
        return copy.deepcopy(result)

    def put(self, call):
        value = call.body["value"]
        self.stored[call.body["name"]] = ("true" if value else "false") if isinstance(value, bool) else str(value)
        return 200, self.new_task("Set setting", call.body["name"])

    def delete(self, call):
        self.stored.pop(call.body["name"], None)
        return 200, self.new_task("Reset setting", call.body["name"])


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, setting.main, check_mode=check_mode, **params)


def test_full_sequence(monkeypatch):
    fake = SettingsCluster()
    name = "graph retention days"
    # 1. set (check)
    r = run(monkeypatch, fake, check_mode=True, name=name, value=60)
    assert r["changed"] and r["diff"]["before"] == dict(state="absent")
    assert r["diff"]["after"] == dict(state="present", value="60")
    assert fake.writes() == []
    # 2. set: typed as the setting's INT type
    r = run(monkeypatch, fake, name=name, value="60")
    assert r["changed"]
    assert fake.writes()[0].body == dict(name=name, value=60)
    assert r["setting"]["value"] == "60"
    # 3. re-set
    r = run(monkeypatch, fake, name=name, value=60)
    assert not r["changed"] and fake.writes() == []
    # 4. re-set (check)
    r = run(monkeypatch, fake, check_mode=True, name=name, value=60)
    assert not r["changed"] and fake.writes() == []
    # 5. change (check)
    r = run(monkeypatch, fake, check_mode=True, name=name, value=90)
    assert r["changed"] and r["diff"]["before"]["value"] == "60"
    assert fake.writes() == []
    # 6. change
    r = run(monkeypatch, fake, name=name, value=90)
    assert r["changed"]
    # 7. change again
    r = run(monkeypatch, fake, name=name, value=90)
    assert not r["changed"] and fake.writes() == []
    # 8. unset (check)
    r = run(monkeypatch, fake, check_mode=True, name=name, state="absent")
    assert r["changed"] and fake.writes() == []
    # 9. unset
    r = run(monkeypatch, fake, name=name, state="absent")
    assert r["changed"]
    assert fake.writes()[0].method == "DELETE"
    assert fake.writes()[0].body == dict(name=name)
    # 10. unset again
    r = run(monkeypatch, fake, name=name, state="absent")
    assert not r["changed"] and fake.writes() == []


def test_storing_the_default_value_is_a_change(monkeypatch):
    fake = SettingsCluster()
    r = run(monkeypatch, fake, name="send telemetry", value=False)
    assert r["changed"]
    assert fake.writes()[0].body["value"] is False
    r = run(monkeypatch, fake, name="send telemetry", value="no")
    assert not r["changed"]


@pytest.mark.parametrize("name,value", [("send telemetry", "maybe"), ("graph retention days", "lots"), ("graph retention days", True)])
def test_bad_values_fail(monkeypatch, name, value):
    fake = SettingsCluster()
    r = run(monkeypatch, fake, name=name, value=value)
    assert r["failed"] and "value for setting" in r["msg"]
    assert fake.writes() == []


def test_unknown_setting_lists_known(monkeypatch):
    r = run(monkeypatch, SettingsCluster(), name="nope", value=1)
    assert r["failed"] and "send telemetry" in r["msg"]


def test_present_requires_value(monkeypatch):
    r = run(monkeypatch, SettingsCluster(), name="send telemetry")
    assert r["failed"]


def test_string_setting(monkeypatch):
    fake = SettingsCluster()
    r = run(monkeypatch, fake, name="support email", value="ops@example.com")
    assert r["changed"] and fake.writes()[0].body["value"] == "ops@example.com"


def test_info(monkeypatch):
    fake = SettingsCluster()
    fake.stored["send telemetry"] = "true"
    r = run_module(monkeypatch, fake, setting_info.main, check_mode=True)
    assert [s["name"] for s in r["settings"]] == ["send telemetry"]
    r = run_module(monkeypatch, fake, setting_info.main, available=True)
    assert len(r["settings"]) == 3
    r = run_module(monkeypatch, fake, setting_info.main, available=True, name="support email")
    assert r["settings"][0]["customized"] is False
