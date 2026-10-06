# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.modules import task as task_module
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

QUESTION = dict(message="Stop OSDs?", responseOptions=["Yes", "No"], defaultResponse="No", token="tok-uuid")


def cluster(state="RUNNING", question=None, finish_on_poll=True):
    fake = FakeCroit()
    fake.serve_tasks(finish_on_poll=finish_on_poll)
    task = fake.new_task("Destroy OSDs", state=state)
    task["question"] = question

    def cancel(call, task_id):
        fake.tasks[int(task_id)].update(state="CANCELED", done=True, cancelled=True, statusCode=-256)
        return 204, None

    def answer(call, task_id):
        assert call.body == dict(token="tok-uuid", response="Yes")
        fake.tasks[int(task_id)]["question"] = None
        return 204, None

    fake.route("POST", r"/tasks/(?P<task_id>\d+)/cancel", cancel)
    fake.route("POST", r"/tasks/(?P<task_id>\d+)/answer", answer)
    return fake, task["id"]


def run(monkeypatch, fake, check_mode=False, **params):
    return run_module(monkeypatch, fake, task_module.main, check_mode=check_mode, **params)


def test_wait_reports_no_change(monkeypatch):
    fake, tid = cluster()
    r = run(monkeypatch, fake, task_id=tid)
    assert not r["changed"]
    assert r["task"]["state"] == "FINISHED"


def test_wait_fails_on_failed_task(monkeypatch):
    fake, tid = cluster(state="FAILED")
    r = run(monkeypatch, fake, task_id=tid)
    assert r["failed"]
    r = run(monkeypatch, fake, task_id=tid, fail_on_error=False)
    assert not r.get("failed")
    assert r["task"]["state"] == "FAILED"


def test_wait_does_not_block_in_check_mode(monkeypatch):
    fake, tid = cluster(finish_on_poll=False)
    r = run(monkeypatch, fake, check_mode=True, task_id=tid)
    assert not r["changed"]
    assert r["task"]["state"] == "RUNNING"
    assert len(fake.calls) == 1


def test_unknown_task_fails(monkeypatch):
    fake, tid = cluster()
    r = run(monkeypatch, fake, task_id=9999)
    assert r["failed"]


def test_cancel_idempotent(monkeypatch):
    fake, tid = cluster(finish_on_poll=False)
    r = run(monkeypatch, fake, check_mode=True, task_id=tid, action="cancel")
    assert r["changed"]
    assert fake.writes() == []

    r = run(monkeypatch, fake, task_id=tid, action="cancel", wait=True)
    assert r["changed"]
    assert r["task"]["state"] == "CANCELED"

    r = run(monkeypatch, fake, task_id=tid, action="cancel")
    assert not r["changed"]
    assert fake.writes() == []


def test_answer_idempotent(monkeypatch):
    fake, tid = cluster(question=QUESTION, finish_on_poll=False)
    r = run(monkeypatch, fake, check_mode=True, task_id=tid, action="answer", answer="Yes")
    assert r["changed"]
    assert fake.writes() == []

    r = run(monkeypatch, fake, task_id=tid, action="answer", answer="Yes")
    assert r["changed"]
    assert len(fake.writes()) == 1

    r = run(monkeypatch, fake, task_id=tid, action="answer", answer="Yes")
    assert not r["changed"]
    assert fake.writes() == []


def test_answer_must_be_an_option(monkeypatch):
    fake, tid = cluster(question=QUESTION)
    r = run(monkeypatch, fake, task_id=tid, action="answer", answer="Maybe")
    assert r["failed"]
    assert "Yes, No" in r["msg"]


def test_answer_requires_answer(monkeypatch):
    fake, tid = cluster(question=QUESTION)
    r = run(monkeypatch, fake, task_id=tid, action="answer")
    assert r["failed"]


def test_wait_on_question_fails_with_hint(monkeypatch):
    fake, tid = cluster(question=QUESTION)
    r = run(monkeypatch, fake, task_id=tid)
    assert r["failed"]
    assert "action=answer" in r["msg"]
