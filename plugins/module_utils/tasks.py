# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""Helpers for croit's long running background tasks (``/tasks``)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import time

from ansible_collections.croit.ceph.plugins.module_utils.client import CroitError, path_join

STATE_FINISHED = "FINISHED"
STATE_FAILED = "FAILED"
STATE_CANCELED = "CANCELED"
TERMINAL_STATES = (STATE_FINISHED, STATE_FAILED, STATE_CANCELED)

# Keep failure messages readable; the full transcript is returned separately.
OUTPUT_TAIL_CHARS = 2000


class CroitTaskError(CroitError):
    """A croit task failed, was cancelled, timed out or needs an answer."""

    def __init__(self, message, task):
        super(CroitTaskError, self).__init__(message)
        self.task = task

    def to_fail_kwargs(self):
        kwargs = super(CroitTaskError, self).to_fail_kwargs()
        kwargs["task"] = self.task
        return kwargs


def is_task(data):
    """True when an API answer is a ManagedTask / ManagedThreadTask."""
    return isinstance(data, dict) and "id" in data and "state" in data and "done" in data and "statusCode" in data


def task_done(task):
    return bool(task.get("done")) or task.get("state") in TERMINAL_STATES


def pending_question(task):
    """The question a running task waits on, or None."""
    if task_done(task):
        return None
    return task.get("question") or None


def _tail(output):
    output = output or ""
    if len(output) > OUTPUT_TAIL_CHARS:
        return "...\n" + output[-OUTPUT_TAIL_CHARS:]
    return output


def describe(task):
    name = task.get("name") or "task"
    obj = task.get("object")
    return "croit task %s (%s%s)" % (task.get("id"), name, " on %s" % obj if obj else "")


def check_task(task):
    """Raise CroitTaskError when a finished task did not succeed."""
    state = task.get("state")
    if state == STATE_FAILED:
        raise CroitTaskError("%s failed:\n%s" % (describe(task), _tail(task.get("output"))), task)
    if state == STATE_CANCELED:
        raise CroitTaskError("%s was cancelled" % describe(task), task)
    return task


def get_task(client, task_id):
    return client.get(path_join("tasks", task_id))


def wait_for_task(client, task, timeout, interval=2.0, fail_on_question=True, sleep=None, clock=None):
    """Poll a task until it ends and return its final state.

    Does not judge the outcome; call check_task() for that. Raises
    CroitTaskError on timeout, or when the task waits on a question and
    ``fail_on_question`` is set (croit then needs an operator's answer, e.g.
    through the croit.ceph.task module).
    """
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    deadline = clock() + timeout
    current = task
    while True:
        if task_done(current):
            # Lists and create answers carry no transcript; fetch it once.
            if not current.get("output") and current.get("id") is not None:
                try:
                    current = get_task(client, current["id"])
                except CroitError:
                    pass
            return current
        question = pending_question(current)
        if question and fail_on_question:
            raise CroitTaskError(
                "%s is waiting for an answer: %s (options: %s). Answer it with croit.ceph.task "
                "(action=answer) or in the croit UI."
                % (describe(current), question.get("message"), ", ".join(question.get("responseOptions") or [])),
                current,
            )
        if clock() >= deadline:
            raise CroitTaskError(
                "Timed out after %ss waiting for %s (state %s)" % (timeout, describe(current), current.get("state")),
                current,
            )
        sleep(interval)
        current = get_task(client, current["id"])
