#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: api
short_description: Send a raw request to the croit API
version_added: 0.1.0
description:
  - Sends one request to any croit API endpoint, using the collection's API token handling, background
    task waiting and ignorable warning handling.
  - B(Last resort.) This module cannot know whether a write changes anything, so it is not idempotent.
    A V(GET) never reports a change, and any other method always does.
  - Prefer a dedicated C(croit.ceph) module. When this module is unavoidable, use C(changed_when) and
    C(when) to keep the playbook idempotent.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: partial
    details:
      - V(GET) requests are always sent, even in check mode, and never report a change.
      - Any other method is skipped in check mode and reported as changed.
  diff_mode:
    support: none
options:
  path:
    description:
      - API path relative to O(api_url), for example V(/pools) or V(/cluster/status).
      - Path parameters must already be URL-encoded, for example V(/pools/my%20pool).
    type: str
    required: true
  method:
    description:
      - HTTP method of the request.
      - Only V(GET) is treated as read-only; every other method reports a change.
    type: str
    choices: [GET, POST, PUT, PATCH, DELETE]
    default: GET
  body:
    description:
      - JSON request body, as a dict, list or scalar. It is sent JSON-encoded.
      - When not set, the request has no body.
    type: raw
  query:
    description:
      - Query parameters to add to the request.
      - A list value repeats the parameter once per item, a dict value is sent JSON-encoded, and a
        V(null) value is left out.
    type: dict
notes:
  - The module returns whatever croit answers, unfiltered. Endpoints that answer secrets (keyrings,
    S3 keys, passwords) put them into RV(json); use C(no_log) on such tasks.
seealso:
  - name: croit API reference
    description: Every croit API endpoint, with request and response schemas.
    link: https://www.croit.io/api-docs
  - module: croit.ceph.task
    description: Wait for, answer or cancel a croit background task started with O(wait=false).
  - module: croit.ceph.cluster_info
    description: Read croit and Ceph cluster status without a raw request.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Read the Ceph health checks
  croit.ceph.api:
    path: /cluster/status/detail
  register: health

- name: Show the raw answer
  ansible.builtin.debug:
    var: health.json

- name: Mute a health check, guarded so the task only runs when the check is raised
  croit.ceph.api:
    path: /cluster/status/mute/POOL_NO_REDUNDANCY
    method: POST
  when: "'POOL_NO_REDUNDANCY' in (health.json | map(attribute='check') | list)"

- name: Read several tasks at once with a repeated query parameter
  croit.ceph.api:
    path: /tasks/status
    query:
      taskIds: [412, 413]
  register: task_status
"""

RETURN = r"""
status:
  description: HTTP status code croit answered.
  returned: when the request was sent (not for a write skipped in check mode)
  type: int
  sample: 200
json:
  description:
    - The parsed response body, or the raw text when croit answered plain text or invalid JSON.
    - V(null) when the response had no body, for example on HTTP 204.
  returned: when the request was sent (not for a write skipped in check mode)
  type: raw
  sample:
    - check: POOL_NO_REDUNDANCY
      severity: HEALTH_WARN
msg:
  description: Explains that a write was skipped.
  returned: when a write was skipped in check mode
  type: str
  sample: POST /cluster/status/mute/OSD_DOWN skipped in check mode
task:
  description:
    - The croit background task the request started (C(TaskResponse) in the croit API).
    - Its final state when O(wait=true), otherwise its state as croit answered it.
  returned: when a non-GET request answered a croit task
  type: dict
  contains:
    id:
      description: The task's id, usable with M(croit.ceph.task) and M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as the croit task list shows it.
      returned: always
      type: str
      sample: Restart services
    state:
      description: The task's state.
      returned: always
      type: str
      sample: FINISHED
    done:
      description: Whether the task has ended.
      returned: always
      type: bool
      sample: true
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: Restarting osd.3 ... done
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import CroitError, CroitWarning
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            path=dict(type="str", required=True),
            method=dict(type="str", default="GET", choices=["GET", "POST", "PUT", "PATCH", "DELETE"]),
            body=dict(type="raw"),
            query=dict(type="dict"),
        )
    )
    p = m.params
    method = p["method"]

    if method != "GET" and m.check_mode:
        m.exit(changed=True, msg="%s %s skipped in check mode" % (method, p["path"]))

    try:
        status, data = m.client.request(
            method, p["path"], body=p["body"], query=p["query"], ignore_warnings=p["ignore_warnings"]
        )
    except CroitWarning as e:
        m.module.fail_json(
            msg="%s. Re-run with ignore_warnings=true to confirm it." % e.message, warning=e.warning_text, status=e.status
        )
    except CroitError as e:
        m.fail_from(e)

    result = dict(changed=method != "GET", status=status, json=data)
    if method != "GET":
        task = m.handle_task(data)
        if task is not None:
            result["task"] = task
    m.exit(**result)


if __name__ == "__main__":
    main()
