# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import crush_info, crush_rule
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

DEFAULT_RULE = dict(
    id=0,
    name="replicated_rule",
    type="REPLICATED",
    steps=[
        dict(op="TAKE", bucket="default", deviceClass=None),
        dict(op="CHOOSELEAF", bucketType="host", num=0, indep=False),
        dict(op="EMIT"),
    ],
)


class CrushCluster(FakeCroit):
    """Fake croit keeping CRUSH rules and the pools that use them."""

    def __init__(self, rules=None, pools=None):
        super(CrushCluster, self).__init__()
        self.rules = [copy.deepcopy(r) for r in (rules if rules is not None else [DEFAULT_RULE])]
        self.pools = pools or []
        self.route("GET", "/crush/rules", lambda call: (200, copy.deepcopy(self.rules)))
        self.route("GET", "/pools", lambda call: (200, copy.deepcopy(self.pools)))
        self.route("POST", "/crush/rules/simple", self.simple)
        self.route("POST", "/crush/rules/ssd-primary", self.ssd_primary)
        self.route("DELETE", "/crush/rules/(?P<name>[^/]+)", self.delete)
        self.reply("GET", "/crush/rules/classes", 200, ["hdd", "ssd"])
        self.reply("GET", "/crush/ec-profiles", 200, dict(default=dict(k=2, m=2, plugin="jerasure", technique="reed_sol_van")))
        self.reply("GET", "/crush", 200, dict(nodes=[], stray=[]))

    def next_id(self):
        return max([r["id"] for r in self.rules] + [-1]) + 1

    def simple(self, call):
        b = call.body
        if not b.get("deviceClass") and call.query.get("ignoreWarning") != "w1":
            return 400, dict(
                code=400,
                message="w",
                ignorableWarning=dict(token="w1", warningText="CRUSH rule should explicitly target a device class."),
            )
        ec = bool(b.get("erasureCoding"))
        steps = []
        if ec:
            steps.append(dict(op="TUNING", parameter="set_chooseleaf_tries", value=5))
        steps += [
            dict(op="TAKE", bucket=b["startBucket"], deviceClass=b.get("deviceClass")),
            dict(op="CHOOSELEAF_INDEP" if ec else "CHOOSELEAF", bucketType=b["independent"], num=0, indep=ec),
            dict(op="EMIT"),
        ]
        self.rules.append(dict(id=self.next_id(), name=b["name"], type="ERASURE" if ec else "REPLICATED", steps=steps))
        return 204, None

    def ssd_primary(self, call):
        b = call.body
        copies = b.get("ssdCopies", 1)
        steps = [
            dict(op="TAKE", bucket=b["ssdStartBucket"], deviceClass=b.get("ssdDeviceClass")),
            dict(op="CHOOSELEAF", bucketType=b["ssdIndependent"], num=copies),
            dict(op="EMIT"),
            dict(op="TAKE", bucket=b["hddStartBucket"], deviceClass=b.get("hddDeviceClass")),
            dict(op="CHOOSELEAF", bucketType=b["hddIndependent"], num=-copies),
            dict(op="EMIT"),
        ]
        self.rules.append(dict(id=self.next_id(), name=b["name"], type="REPLICATED", steps=steps))
        return 204, None

    def delete(self, call, name):
        self.rules = [r for r in self.rules if r["name"] != name]
        return 204, None


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, crush_rule.main, check_mode=check_mode, **params)


def names(fake):
    return [r["name"] for r in fake.rules]


def test_full_sequence(monkeypatch):
    """CRUSH rules cannot be updated, so steps 5-7 check that a differing rule fails without writes."""
    fake = CrushCluster()
    spec = dict(name="ssd", failure_domain="host", device_class="ssd")

    # 1. create in check mode
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"] == dict(
        type="simple", start_bucket="default", failure_domain="host", device_class="ssd", erasure_coding=False
    )
    assert fake.writes() == []
    assert "ssd" not in names(fake)

    # 2. create
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body == dict(name="ssd", startBucket="default", independent="host", deviceClass="ssd")
    assert r["rule"]["name"] == "ssd"
    assert r["layout"]["device_class"] == "ssd"

    # 3-4. re-run, and in check mode
    for check in (False, True):
        r = run(monkeypatch, fake, check_mode=check, **spec)
        assert not r["changed"]
        assert fake.writes() == []

    # 5-7. a different placement fails clearly, in check mode and for real, and writes nothing
    for check in (True, False):
        r = run(monkeypatch, fake, check_mode=check, name="ssd", failure_domain="rack")
        assert r["failed"]
        assert "cannot be changed in place" in r["msg"]
        assert "failure_domain ('host', wanted 'rack')" in r["msg"]
        assert fake.writes() == []

    # 8. delete in check mode
    r = run(monkeypatch, fake, check_mode=True, name="ssd", state="absent")
    assert r["changed"]
    assert fake.writes() == []
    assert "ssd" in names(fake)

    # 9. delete
    r = run(monkeypatch, fake, name="ssd", state="absent")
    assert r["changed"]
    assert [c.method for c in fake.writes()] == ["DELETE"]
    assert "ssd" not in names(fake)

    # 10. delete again
    r = run(monkeypatch, fake, name="ssd", state="absent")
    assert not r["changed"]
    assert fake.writes() == []


def test_name_only_checks_existence(monkeypatch):
    fake = CrushCluster()
    r = run(monkeypatch, fake, name="replicated_rule")
    assert not r["changed"]
    assert r["layout"]["failure_domain"] == "host"


def test_class_pinned_take_in_ceph_syntax(monkeypatch):
    rule = copy.deepcopy(DEFAULT_RULE)
    rule.update(id=4, name="pinned")
    rule["steps"][0] = dict(op="TAKE", bucket="default~ssd", deviceClass=None)
    fake = CrushCluster(rules=[rule])
    r = run(monkeypatch, fake, name="pinned", device_class="ssd", start_bucket="default")
    assert not r["changed"]


def test_missing_device_class_warning(monkeypatch):
    fake = CrushCluster()
    r = run(monkeypatch, fake, name="any", failure_domain="host")
    assert r["failed"]
    assert "device class" in r["warning"]
    assert "any" not in names(fake)
    r = run(monkeypatch, fake, name="any", failure_domain="host", ignore_warnings=True)
    assert r["changed"]
    assert "any" in names(fake)


def test_erasure_rule(monkeypatch):
    fake = CrushCluster()
    spec = dict(name="ec", erasure_coding=True, device_class="hdd", failure_domain="host")
    assert run(monkeypatch, fake, **spec)["changed"]
    assert fake.writes()[0].body["erasureCoding"] is True
    assert not run(monkeypatch, fake, **spec)["changed"]
    r = run(monkeypatch, fake, name="ec", erasure_coding=False)
    assert r["failed"]


def test_ssd_primary_sequence(monkeypatch):
    fake = CrushCluster()
    spec = dict(name="hybrid", type="ssd_primary", ssd_device_class="ssd", ssd_copies=1, hdd_device_class="hdd")
    r = run(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"] and fake.writes() == []
    r = run(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].path == "/crush/rules/ssd-primary"
    assert fake.writes()[0].body == dict(
        name="hybrid",
        ssdStartBucket="default",
        ssdIndependent="host",
        hddStartBucket="default",
        hddIndependent="host",
        ssdDeviceClass="ssd",
        hddDeviceClass="hdd",
        ssdCopies=1,
    )
    assert not run(monkeypatch, fake, **spec)["changed"]
    r = run(monkeypatch, fake, name="hybrid", ssd_copies=2)
    assert r["failed"]
    # a simple-rule option against an ssd_primary rule is a type mismatch
    r = run(monkeypatch, fake, name="hybrid", device_class="ssd")
    assert r["failed"]
    assert "type" in r["msg"]


def test_mixed_options_rejected(monkeypatch):
    fake = CrushCluster()
    r = run(monkeypatch, fake, name="x", type="simple", ssd_copies=1)
    assert r["failed"]
    assert fake.calls == []


def test_custom_rule_cannot_be_compared(monkeypatch):
    rule = dict(id=7, name="custom", type="REPLICATED", steps=[dict(op="TAKE", bucket="a"), dict(op="EMIT")] * 3)
    fake = CrushCluster(rules=[rule])
    assert not run(monkeypatch, fake, name="custom")["changed"]
    r = run(monkeypatch, fake, name="custom", failure_domain="host")
    assert r["failed"]
    assert "cannot compare" in r["msg"]


def test_delete_refused_while_pool_uses_rule(monkeypatch):
    fake = CrushCluster(pools=[dict(name="rbd", crushRule=0), dict(name="elsewhere", crushRule=3)])
    for check in (True, False):
        r = run(monkeypatch, fake, check_mode=check, name="replicated_rule", state="absent")
        assert r["failed"]
        assert "rbd" in r["msg"] and "elsewhere" not in r["msg"]
    assert fake.writes() == []
    assert "replicated_rule" in names(fake)


def test_crush_info(monkeypatch):
    fake = CrushCluster()
    r = run_module(monkeypatch, fake, crush_info.main, check_mode=True)
    assert not r["changed"]
    assert r["rules"][0]["layout"]["type"] == "simple"
    assert r["classes"] == ["hdd", "ssd"]
    assert "default" in r["ec_profiles"]
    assert "tree" not in r
    r = run_module(monkeypatch, fake, crush_info.main, gather=["tree"])
    assert r["tree"] == dict(nodes=[], stray=[])
    assert [c.path for c in fake.calls] == ["/crush"]
