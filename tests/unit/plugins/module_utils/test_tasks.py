# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.croit.ceph.plugins.module_utils.client import CroitClient
from ansible_collections.croit.ceph.plugins.module_utils.tasks import (
    CroitTaskError,
    check_task,
    is_task,
    wait_for_task,
)
from ansible_collections.croit.ceph.tests.unit.fake_croit import API_URL, FakeCroit


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def start_task(states, question=None):
    """A task that walks through ``states`` on successive polls."""
    fake = FakeCroit()
    task = fake.new_task("Create pool", "p", state=states[0], output="")
    seq = list(states)

    def handler(call, task_id):
        state = seq.pop(0) if len(seq) > 1 else seq[0]
        body = dict(task, state=state, done=state in ("FINISHED", "FAILED", "CANCELED"), output="log of %s" % state)
        if question and state == "RUNNING":
            body["question"] = question
        return 200, body

    fake.route("GET", r"/tasks/(?P<task_id>\d+)", handler)
    return fake, CroitClient(API_URL, "tok", opener=fake), task


def test_is_task():
    assert is_task(dict(id=1, state="RUNNING", done=False, statusCode=-1))
    assert not is_task(dict(id=1))
    assert not is_task(None)


def test_wait_until_finished():
    fake, client, task = start_task(["RUNNING", "RUNNING", "FINISHED"])
    clock = Clock()
    final = wait_for_task(client, task, 60, sleep=clock.sleep, clock=clock)
    assert final["state"] == "FINISHED"
    assert final["output"] == "log of FINISHED"
    assert check_task(final) is final


def test_failed_task_raises_with_output():
    fake, client, task = start_task(["RUNNING", "FAILED"])
    clock = Clock()
    final = wait_for_task(client, task, 60, sleep=clock.sleep, clock=clock)
    with pytest.raises(CroitTaskError) as e:
        check_task(final)
    assert "failed" in e.value.message
    assert "log of FAILED" in e.value.message
    assert e.value.to_fail_kwargs()["task"]["state"] == "FAILED"


def test_cancelled_task_raises():
    with pytest.raises(CroitTaskError):
        check_task(dict(id=1, state="CANCELED", done=True, statusCode=-256))


def test_timeout():
    fake, client, task = start_task(["RUNNING"])
    clock = Clock()
    with pytest.raises(CroitTaskError) as e:
        wait_for_task(client, task, 10, interval=2, sleep=clock.sleep, clock=clock)
    assert "Timed out" in e.value.message


def test_question_fails_with_options():
    question = dict(message="Stop OSDs?", responseOptions=["Yes", "No"], defaultResponse="No", token="u")
    fake, client, task = start_task(["RUNNING"], question=question)
    clock = Clock()
    with pytest.raises(CroitTaskError) as e:
        wait_for_task(client, task, 60, sleep=clock.sleep, clock=clock)
    assert "Stop OSDs?" in e.value.message
    assert "Yes, No" in e.value.message
