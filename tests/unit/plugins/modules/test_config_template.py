# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import config_template
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

STOCK = "server pool.ntp.org iburst\n"
ALT = "server time.example.com iburst\n"


class TemplateCluster(FakeCroit):
    def __init__(self):
        super(TemplateCluster, self).__init__()
        self.templates = [
            dict(
                id="chrony",
                description="Chrony on the servers",
                currentTemplateName="default",
                currentTemplate=STOCK,
                availableTemplates=[dict(name="default", template=STOCK), dict(name="example", template=ALT)],
            )
        ]
        self.serve_tasks()
        self.route("GET", "/config-templates", lambda call: (200, copy.deepcopy(self.templates)))
        self.route("PUT", "/config-templates/templates/(?P<template>[^/]+)", self.put)

    def put(self, call, template):
        t = [x for x in self.templates if x["id"] == template][0]
        if call.body.get("predefinedTemplate"):
            name = call.body["predefinedTemplate"]
            t.update(currentTemplateName=name, currentTemplate=[a for a in t["availableTemplates"] if a["name"] == name][0]["template"])
        else:
            t.update(currentTemplateName="custom", currentTemplate=call.body["customTemplate"])
        return 200, self.new_task("Save template", template)


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, config_template.main, check_mode=check_mode, **params)


def test_full_sequence(monkeypatch):
    fake = TemplateCluster()
    custom = "server ntp1.example.com iburst\nserver ntp2.example.com iburst"
    # 1. custom (check)
    r = run(monkeypatch, fake, check_mode=True, name="chrony", content=custom)
    assert r["changed"]
    assert r["diff"]["before"]["content"] == STOCK and r["diff"]["after"]["content"] == custom
    assert fake.writes() == []
    # 2. custom
    r = run(monkeypatch, fake, name="chrony", content=custom)
    assert r["changed"]
    assert fake.writes()[0].body == dict(customTemplate=custom)
    assert r["template"]["currentTemplate"] == custom
    # 3. again; a trailing newline does not count
    r = run(monkeypatch, fake, name="chrony", content=custom + "\n")
    assert not r["changed"] and fake.writes() == []
    # 4. again (check)
    r = run(monkeypatch, fake, check_mode=True, name="chrony", content=custom)
    assert not r["changed"] and fake.writes() == []
    # 5. change (check)
    r = run(monkeypatch, fake, check_mode=True, name="chrony", content=custom + "\nmakestep 1 3")
    assert r["changed"] and fake.writes() == []
    # 6. change
    r = run(monkeypatch, fake, name="chrony", content=custom + "\nmakestep 1 3")
    assert r["changed"]
    # 7. change again
    r = run(monkeypatch, fake, name="chrony", content=custom + "\nmakestep 1 3")
    assert not r["changed"]
    # 8. back to stock (check)
    r = run(monkeypatch, fake, check_mode=True, name="chrony", predefined="default")
    assert r["changed"] and r["diff"]["after"] == dict(predefined="default", content=STOCK)
    assert fake.writes() == []
    # 9. back to stock
    r = run(monkeypatch, fake, name="chrony", predefined="default")
    assert r["changed"] and fake.writes()[0].body == dict(predefinedTemplate="default")
    # 10. stock again
    r = run(monkeypatch, fake, name="chrony", predefined="default")
    assert not r["changed"] and fake.writes() == []


def test_whitespace_inside_is_significant(monkeypatch):
    fake = TemplateCluster()
    r = run(monkeypatch, fake, name="chrony", content=" " + STOCK)
    assert r["changed"]


def test_unknown_template_and_predefined(monkeypatch):
    fake = TemplateCluster()
    r = run(monkeypatch, fake, name="ghost", predefined="default")
    assert r["failed"] and "chrony" in r["msg"]
    r = run(monkeypatch, fake, name="chrony", predefined="ghost")
    assert r["failed"] and "default, example" in r["msg"]
    assert fake.writes() == []


def test_content_and_predefined_exclusive(monkeypatch):
    r = run(monkeypatch, TemplateCluster(), name="chrony", content="x", predefined="default")
    assert r["failed"]
    r = run(monkeypatch, TemplateCluster(), name="chrony")
    assert r["failed"]


def test_network_template_warning(monkeypatch):
    fake = TemplateCluster()

    def put(call, template):
        if call.query.get("ignoreWarning") != "t":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="t", warningText="may cause loss"))
        return fake.put(call, template)

    fake.routes = [rt for rt in fake.routes if rt[0] != "PUT"]
    fake.route("PUT", "/config-templates/templates/(?P<template>[^/]+)", put)
    r = run(monkeypatch, fake, name="chrony", predefined="example")
    assert r["failed"] and r["warning"] == "may cause loss"
    r = run(monkeypatch, fake, name="chrony", predefined="example", ignore_warnings=True)
    assert r["changed"]
