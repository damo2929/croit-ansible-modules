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
  - Returns croit background tasks, either the ones still running or specific tasks by id.
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
      - Ids of the tasks to return, with their full transcript. Unknown ids are left out.
      - When not set, every task that is still running or waiting is returned (without transcript).
    type: list
    elements: int
"""

EXAMPLES = r"""
- name: List running croit tasks
  croit.ceph.task_info:
  register: running

- name: Read two tasks
  croit.ceph.task_info:
    task_ids: [412, 413]
"""

RETURN = r"""
tasks:
  description: The tasks (C(TaskResponse) in the croit API).
  returned: always
  type: list
  elements: dict
  sample:
    - id: 412
      name: Create pool
      object: rbd-ssd
      state: RUNNING
      done: false
      statusCode: -1
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
