#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /tasks/active
# croit-api: GET /tasks/status

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: task_info
short_description: Read croit background tasks
version_added: 0.1.0
description:
  - Returns croit background tasks, either every task that is still running or waiting, or specific
    tasks by id with their full transcript.
  - This module never changes anything.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: N/A
options:
  task_ids:
    description:
      - Ids of the tasks to return, with their full transcript. Ids croit no longer knows are left out
        rather than failing.
      - When not set, every task that is still running or waiting is returned, without transcript.
    type: list
    elements: int
seealso:
  - module: croit.ceph.task
    description: Wait for, answer or cancel one of the tasks.
  - name: croit API reference
    description: The C(/tasks) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: List running croit tasks
  croit.ceph.task_info:
  register: running

- name: Refuse to start maintenance while croit is busy
  ansible.builtin.assert:
    that: running.tasks | length == 0
    fail_msg: "croit is still running: {{ running.tasks | map(attribute='name') | join(', ') }}"

- name: Read two tasks with their transcripts
  croit.ceph.task_info:
    task_ids: [412, 413]
  register: finished
"""

RETURN = r"""
tasks:
  description:
    - The tasks (C(TaskResponse) in the croit API).
    - Without O(task_ids), C(output) is empty because croit leaves the transcript out of its task lists.
  returned: always
  type: list
  elements: dict
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
      sample: RUNNING
    done:
      description: Whether the task has ended.
      returned: always
      type: bool
      sample: false
    statusCode:
      description: What the task ended with; V(0) succeeded, V(-256) cancelled, V(-1) still running.
      returned: always
      type: int
      sample: -1
    startedBy:
      description: The user or API token that started the task, or C(system).
      returned: always
      type: str
      sample: ansible
    output:
      description: The task's transcript; empty unless the task was requested with O(task_ids).
      returned: always
      type: str
      sample: ""
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(dict(task_ids=dict(type="list", elements="int")), wait=False, warnings=False)
    ids = m.params["task_ids"]
    if ids:
        tasks = m.get_list("/tasks/status", query=dict(taskIds=ids))
    else:
        tasks = m.get_list("/tasks/active")
    m.exit(changed=False, tasks=tasks)


if __name__ == "__main__":
    main()
