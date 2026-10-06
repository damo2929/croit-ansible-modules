#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /tasks/{taskId}
# croit-api: POST /tasks/{taskId}/answer
# croit-api: POST /tasks/{taskId}/cancel

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: task
short_description: Wait for, answer or cancel a croit background task
version_added: 0.1.0
description:
  - Acts on one croit background task, identified by its numeric id, for example the RV(task) another
    module returned when it ran with O(wait=false).
  - Waiting never reports a change. Cancelling a task that already ended, or answering a task with no
    pending question, leaves the task alone and reports no change.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
attributes:
  check_mode:
    support: full
    details:
      - In check mode the module does not wait for a running task; it returns the task's current state.
  diff_mode:
    support: none
options:
  task_id:
    description:
      - Numeric id of the croit task, as returned in RV(task.id) by other modules or by M(croit.ceph.task_info).
    type: int
    required: true
  action:
    description:
      - V(wait) waits until the task ends. It never reports a change.
      - V(cancel) asks a running task to stop. A task that already ended is left alone.
      - V(answer) answers the question the task is waiting on with O(answer). A task without a pending
        question is left alone.
    type: str
    choices: [wait, cancel, answer]
    default: wait
  answer:
    description:
      - The option to answer the task's question with. It must be one of the options the question offers,
        otherwise the module fails and lists them.
      - Required with O(action=answer).
    type: str
  wait_timeout:
    description:
      - How many seconds to wait for the task to end with O(action=wait), or after O(action=cancel) and
        O(action=answer) when O(wait=true).
    type: int
    default: 600
  wait:
    description:
      - With O(action=cancel) or O(action=answer), wait for the task to end afterwards.
      - Has no effect with O(action=wait), which always waits.
    type: bool
    default: false
  fail_on_error:
    description:
      - Fail when the task ended as failed or cancelled, after O(action=wait) or after waiting with
        O(action=answer).
      - A task cancelled with O(action=cancel) is never treated as an error.
    type: bool
    default: true
notes:
  - croit keeps finished tasks only for a while. A task id croit no longer knows makes the module fail.
  - A task that waits on a question cannot finish until it is answered; O(action=wait) fails with the
    question and its options instead of timing out.
seealso:
  - module: croit.ceph.task_info
    description: List running croit tasks or read tasks by id.
  - module: croit.ceph.api
    description: Raw croit API requests, which can also start tasks.
  - name: croit API reference
    description: The C(/tasks) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Start a pool creation without waiting
  croit.ceph.pool:
    name: bulk
    wait: false
  register: created

- name: Wait for it later, allowing up to 30 minutes
  croit.ceph.task:
    task_id: "{{ created.task.id }}"
    wait_timeout: 1800
  when: created.task is defined
  register: finished

- name: Show the task transcript
  ansible.builtin.debug:
    msg: "{{ finished.task.output }}"
  when: finished.task is defined

- name: Confirm the question a task asks, then wait for it to finish
  croit.ceph.task:
    task_id: 512
    action: answer
    answer: "Yes"
    wait: true

- name: Cancel a running task
  croit.ceph.task:
    task_id: 513
    action: cancel
"""

RETURN = r"""
task:
  description: The task (C(TaskResponse) in the croit API) after the action.
  returned: always
  type: dict
  contains:
    id:
      description: The task's id.
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as the croit task list shows it.
      returned: always
      type: str
      sample: Create pool
    object:
      description: What the task acts on, if anything.
      returned: always
      type: str
      sample: rbd-ssd
    state:
      description: The task's state, one of V(WAITING), V(RUNNING), V(FINISHED), V(FAILED) or V(CANCELED).
      returned: always
      type: str
      sample: FINISHED
    done:
      description: Whether the task has ended.
      returned: always
      type: bool
      sample: true
    statusCode:
      description: What the task ended with; V(0) succeeded, V(-256) cancelled, V(-1) still running.
      returned: always
      type: int
      sample: 0
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: Creating pool rbd-ssd ... done
    question:
      description: The question the task waits on, with C(message), C(responseOptions) and C(token), or V(null).
      returned: always
      type: dict
      sample: null
msg:
  description: Why nothing was done.
  returned: when the module waited in check mode, or found no pending question with O(action=answer)
  type: str
  sample: Task has no pending question
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.tasks import (
    CroitTaskError,
    check_task,
    pending_question,
    task_done,
    wait_for_task,
)


class TaskModule(CroitModule):
    def __init__(self):
        super(TaskModule, self).__init__(
            dict(
                task_id=dict(type="int", required=True),
                action=dict(type="str", default="wait", choices=["wait", "cancel", "answer"]),
                answer=dict(type="str"),
                wait=dict(type="bool", default=False),
                wait_timeout=dict(type="int", default=600),
                fail_on_error=dict(type="bool", default=True),
            ),
            wait=False,
            warnings=False,
            required_if=[("action", "answer", ["answer"])],
        )

    def wait_and_judge(self, task):
        try:
            task = wait_for_task(self.client, task, self.params["wait_timeout"], fail_on_question=True)
            if self.params["fail_on_error"]:
                check_task(task)
        except CroitTaskError as e:
            self.fail_from(e)
        return task

    def run(self):
        p = self.params
        task_path = path_join("tasks", p["task_id"])
        task = self.get_or_none(task_path)
        if task is None:
            self.module.fail_json(msg="croit does not know task %s (it may have been pruned)" % p["task_id"])

        if p["action"] == "wait":
            if self.check_mode and not task_done(task):
                self.exit(changed=False, task=task, msg="Not waiting in check mode")
            self.exit(changed=False, task=self.wait_and_judge(task))

        if p["action"] == "cancel":
            if task_done(task):
                self.exit(changed=False, task=task)
            if not self.check_mode:
                self.write("POST", path_join("tasks", p["task_id"], "cancel"))
                task = self.get(task_path)
                if p["wait"]:
                    task = self._wait_cancelled(task)
            self.exit(changed=True, task=task)

        # answer
        question = pending_question(task)
        if not question:
            self.exit(changed=False, task=task, msg="Task has no pending question")
        options = question.get("responseOptions") or []
        if options and p["answer"] not in options:
            self.module.fail_json(
                msg="%r is not an option for the task's question %r; options: %s"
                % (p["answer"], question.get("message"), ", ".join(options)),
                task=task,
            )
        if not self.check_mode:
            self.write(
                "POST",
                path_join("tasks", p["task_id"], "answer"),
                body=dict(token=question["token"], response=p["answer"]),
            )
            task = self.get(task_path)
            if p["wait"]:
                task = self.wait_and_judge(task)
        self.exit(changed=True, task=task)

    def _wait_cancelled(self, task):
        # A cancelled task ends as CANCELED, which is the expected outcome here.
        try:
            return wait_for_task(self.client, task, self.params["wait_timeout"], fail_on_question=False)
        except CroitTaskError as e:
            self.fail_from(e)


def main():
    TaskModule().run()


if __name__ == "__main__":
    main()
