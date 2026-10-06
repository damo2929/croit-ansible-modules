# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import api
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module


def test_get_never_changes(monkeypatch):
    fake = FakeCroit()
    fake.reply("GET", "/cluster/status", 200, dict(health="HEALTH_OK"))
    r = run_module(monkeypatch, fake, api.main, path="/cluster/status")
    assert not r["changed"]
    assert r["json"] == dict(health="HEALTH_OK")
    assert r["status"] == 200


def test_get_runs_in_check_mode(monkeypatch):
    fake = FakeCroit()
    fake.reply("GET", "/x", 200, [])
    r = run_module(monkeypatch, fake, api.main, check_mode=True, path="/x")
    assert not r["changed"]
    assert len(fake.calls) == 1


def test_write_skipped_in_check_mode(monkeypatch):
    fake = FakeCroit()
    r = run_module(monkeypatch, fake, api.main, check_mode=True, path="/x", method="POST", body=dict(a=1))
    assert r["changed"]
    assert fake.calls == []


def test_write_waits_for_task(monkeypatch):
    fake = FakeCroit()
    fake.serve_tasks(finish_on_poll=True)
    fake.route("POST", "/services/restart", lambda call: (200, fake.new_task("Restart", state="RUNNING")))
    r = run_module(monkeypatch, fake, api.main, path="/services/restart", method="POST", body=dict(services=[1]))
    assert r["changed"]
    assert r["task"]["state"] == "FINISHED"
    assert [c.method for c in fake.calls] == ["POST", "GET"]


def test_write_no_wait(monkeypatch):
    fake = FakeCroit()
    fake.route("POST", "/services/restart", lambda call: (200, fake.new_task("Restart", state="RUNNING")))
    r = run_module(monkeypatch, fake, api.main, path="/services/restart", method="POST", wait=False)
    assert r["task"]["state"] == "RUNNING"
    assert len(fake.calls) == 1


def test_error_fails(monkeypatch):
    fake = FakeCroit()
    fake.reply("DELETE", "/x", 409, dict(code=409, message="in use"))
    r = run_module(monkeypatch, fake, api.main, path="/x", method="DELETE")
    assert r["failed"]
    assert r["status"] == 409
    assert "in use" in r["msg"]


def test_query_passed(monkeypatch):
    fake = FakeCroit()
    fake.reply("GET", "/tasks/status", 200, [])
    run_module(monkeypatch, fake, api.main, path="/tasks/status", query=dict(taskIds=[1, 2]))
    assert fake.calls[0].query == dict(taskIds=["1", "2"])
