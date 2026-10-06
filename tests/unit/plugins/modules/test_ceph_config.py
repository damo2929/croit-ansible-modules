# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import re

import pytest

from ansible.module_utils import basic

from ansible_collections.croit.ceph.plugins.modules import ceph_config, ceph_config_info
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

OPTIONS = {
    "osd max backfills": dict(type="INT", unit=None, default=1),
    "osd memory target": dict(type="INT", unit="BYTES", default=4294967296),
    "mon warn on pool no redundancy": dict(type="BOOL", unit=None, default=True),
}


def unconfigured(name, section="global", mask=""):
    opt = OPTIONS.get(name, dict(type="STRING", unit=None, default=None))
    return dict(
        name=name,
        section=section,
        mask=mask,
        type=opt["type"],
        unit=opt["unit"],
        currentValue=opt["default"],
        defaultValue=opt["default"],
        croitDefaultValue=None,
        customized=False,
        useCroitDefault=False,
        useCephDefault=False,
    )


class ConfigCluster(FakeCroit):
    """Fake croit holding the mon config database as croit reports it."""

    def __init__(self, rows=None):
        super(ConfigCluster, self).__init__()
        self.rows = rows or []
        self.serve_tasks()
        self.route("GET", "/config/available", self.available)
        self.route("GET", "/config", self.configured)
        self.route("PUT", "/config", self.put)
        self.route("DELETE", "/config", self.delete)

    def find(self, name, section, mask):
        name = " ".join(name.replace("_", " ").split())
        for row in self.rows:
            if (row["name"], row["section"], row["mask"]) == (name, section, mask):
                return row
        return None

    def available(self, call):
        rows = [copy.deepcopy(r) for r in self.rows]
        for name in OPTIONS:
            if not any(r["name"] == name for r in rows):
                rows.append(unconfigured(name))
        return 200, rows

    def configured(self, call):
        return 200, [copy.deepcopy(r) for r in self.rows if r["customized"] or r["useCephDefault"]]

    def put(self, call):
        body = call.body
        section, mask = body.get("section", "global"), body.get("mask", "")
        row = self.find(body["name"], section, mask)
        if row is None:
            row = unconfigured(" ".join(body["name"].replace("_", " ").split()), section, mask)
            self.rows.append(row)
        row.update(customized=False, useCroitDefault=False, useCephDefault=False, currentValue=row["defaultValue"])
        if body.get("useCroitDefault"):
            row["useCroitDefault"] = True
        elif body.get("useCephDefault"):
            row["useCephDefault"] = True
        else:
            row.update(customized=True, currentValue=body["value"])
        return 200, self.new_task("Set config", body["name"])

    def delete(self, call):
        body = call.body
        row = self.find(body["name"], body.get("section", "global"), body.get("mask", ""))
        if row is not None:
            self.rows.remove(row)
        return 200, self.new_task("Unset config", body["name"])


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, ceph_config.main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()


def test_full_sequence(monkeypatch):
    fake = ConfigCluster()
    spec = dict(name="osd_max_backfills", section="osd", value=2)

    # 1. set (check)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and r["diff"]["before"] == dict(state="unset")
    assert r["diff"]["after"] == dict(state="value", value=2)
    assert_only_gets(fake)
    assert fake.rows == []
    # 2. set
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert r["task"]["state"] == "FINISHED"
    put = fake.writes()[0]
    assert put.body == dict(name="osd_max_backfills", section="osd", mask="", value=2)
    assert r["config"]["currentValue"] == 2
    # 3. re-set
    r = run(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)
    # 4. re-set (check)
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]
    assert_only_gets(fake)
    # 5. change (check)
    r = run(monkeypatch, fake, check_mode=True, name="osd max backfills", section="osd", value="3")
    assert r["changed"]
    assert r["diff"]["before"]["value"] == 2
    assert_only_gets(fake)
    # 6. change
    r = run(monkeypatch, fake, name="osd max backfills", section="osd", value="3")
    assert r["changed"]
    # 7. change again (string vs number normalisation)
    r = run(monkeypatch, fake, name="osd_max_backfills", section="osd", value=3)
    assert not r["changed"]
    assert_only_gets(fake)
    # 8. unset (check)
    r = run(monkeypatch, fake, check_mode=True, name="osd_max_backfills", section="osd", state="absent")
    assert r["changed"]
    assert r["diff"]["after"] == dict(state="unset")
    assert_only_gets(fake)
    # 9. unset
    r = run(monkeypatch, fake, name="osd_max_backfills", section="osd", state="absent")
    assert r["changed"]
    assert fake.writes()[0].method == "DELETE"
    assert fake.writes()[0].body == dict(name="osd_max_backfills", section="osd", mask="")
    # 10. unset again
    r = run(monkeypatch, fake, name="osd_max_backfills", section="osd", state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_sections_and_masks_are_separate(monkeypatch):
    row = unconfigured("osd max backfills", "osd", "")
    row.update(customized=True, currentValue=2)
    fake = ConfigCluster([row])
    r = run(monkeypatch, fake, name="osd_max_backfills", section="osd", mask="class:ssd", value=2)
    assert r["changed"]
    assert fake.writes()[0].body["mask"] == "class:ssd"
    assert len(fake.rows) == 2


@pytest.mark.parametrize("value", [True, "true", "True"])
def test_bool_normalisation(monkeypatch, value):
    row = unconfigured("mon warn on pool no redundancy")
    row.update(customized=True, currentValue="true")
    fake = ConfigCluster([row])
    r = run(monkeypatch, fake, name="mon_warn_on_pool_no_redundancy", value=value)
    assert not r["changed"]


def test_bytes_option_accepts_units(monkeypatch):
    fake = ConfigCluster()
    r = run(monkeypatch, fake, name="osd_memory_target", section="osd", mask="class:ssd", value="8G")
    assert r["changed"]
    assert fake.writes()[0].body["value"] == 8 * 1024 ** 3
    r = run(monkeypatch, fake, name="osd_memory_target", section="osd", mask="class:ssd", value="8G")
    assert not r["changed"]


def test_use_default_sequence(monkeypatch):
    fake = ConfigCluster()
    r = run(monkeypatch, fake, check_mode=True, name="osd_max_backfills", use_default="ceph")
    assert r["changed"]
    assert_only_gets(fake)
    r = run(monkeypatch, fake, name="osd_max_backfills", use_default="ceph")
    assert r["changed"]
    assert fake.writes()[0].body == dict(name="osd_max_backfills", section="global", mask="", useCephDefault=True)
    r = run(monkeypatch, fake, name="osd_max_backfills", use_default="ceph")
    assert not r["changed"]
    r = run(monkeypatch, fake, name="osd_max_backfills", use_default="croit")
    assert r["changed"]
    assert fake.writes()[0].body["useCroitDefault"] is True
    # a pinned default is not "unset"
    r = run(monkeypatch, fake, check_mode=True, name="osd_max_backfills", state="absent")
    assert r["changed"]


def test_value_and_use_default_exclusive(monkeypatch):
    r = run(monkeypatch, ConfigCluster(), name="osd_max_backfills", value=1, use_default="ceph")
    assert r["failed"]


def test_present_needs_value_or_default(monkeypatch):
    r = run(monkeypatch, ConfigCluster(), name="osd_max_backfills")
    assert r["failed"]


def test_unknown_option_warns_and_sets(monkeypatch):
    warnings = []
    monkeypatch.setattr(basic.AnsibleModule, "warn", lambda self, msg: warnings.append(msg))
    fake = ConfigCluster()
    r = run(monkeypatch, fake, name="made_up_option", value="x")
    assert r["changed"]
    assert any("does not know" in w for w in warnings)
    r = run(monkeypatch, fake, name="made_up_option", value="x")
    assert not r["changed"]


def test_task_failure_fails(monkeypatch):
    fake = ConfigCluster()
    fake.routes = [rt for rt in fake.routes if rt[0] != "PUT"]
    fake.route("PUT", "/config", lambda call: (200, fake.new_task("Set", state="FAILED", output="ceph refused")))
    r = run(monkeypatch, fake, name="osd_max_backfills", value=9)
    assert r["failed"]
    assert "ceph refused" in r["msg"]


def test_warning_needs_ignore_warnings(monkeypatch):
    fake = ConfigCluster()
    fake.routes.insert(
        0,
        (
            "PUT",
            re.compile("^/config$"),
            lambda call: (400, dict(code=400, message="w", ignorableWarning=dict(token="t", warningText="RGW frontend")))
            if call.query.get("ignoreWarning") != "t"
            else fake.put(call),
        ),
    )
    r = run(monkeypatch, fake, name="osd_max_backfills", value=2)
    assert r["failed"] and r["warning"] == "RGW frontend"
    r = run(monkeypatch, fake, name="osd_max_backfills", value=2, ignore_warnings=True)
    assert r["changed"]


def test_info(monkeypatch):
    row = unconfigured("osd max backfills", "osd", "")
    row.update(customized=True, currentValue=2)
    fake = ConfigCluster([row])
    r = run_module(monkeypatch, fake, ceph_config_info.main, check_mode=True)
    assert [c["name"] for c in r["config"]] == ["osd max backfills"]
    r = run_module(monkeypatch, fake, ceph_config_info.main, available=True, name="osd_memory_target")
    assert len(r["config"]) == 1
    r = run_module(monkeypatch, fake, ceph_config_info.main, available=True, section="osd")
    assert [c["section"] for c in r["config"]] == ["osd"]
    assert fake.writes() == []
