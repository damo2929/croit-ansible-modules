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
  - Sends one request to any croit API endpoint, using the collection's API token handling,
    background task waiting and warning handling.
  - B(Last resort.) This module cannot know whether a write changes anything, so it is not idempotent.
    A V(GET) never reports a change, and any other method always does. Prefer a dedicated
    module, and use C(changed_when) or C(when) to make a playbook idempotent.
  - See U(https://www.croit.io/api-docs) for the endpoints.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: full
    details:
      - V(GET) requests are always sent. Other methods are skipped in check mode and reported as changed.
  diff_mode:
    support: none
options:
  path:
    description:
      - API path relative to O(api_url), for example V(/pools) or V(/cluster/status).
      - Path parameters must already be URL-encoded.
    type: str
    required: true
  method:
    description:
      - HTTP method.
    type: str
    choices: [GET, POST, PUT, PATCH, DELETE]
    default: GET
  body:
    description:
      - JSON request body.
    type: raw
  query:
    description:
      - Query parameters. Lists repeat the parameter; dicts are sent JSON-encoded.
    type: dict
"""

EXAMPLES = r"""
- name: Read the ceph health checks
  croit.ceph.api:
    path: /cluster/status/detail
  register: health

- name: Mute a health check (not idempotent; guard it yourself)
  croit.ceph.api:
    path: /cluster/status/mute/POOL_NO_REDUNDANCY
    method: POST
  when: "'POOL_NO_REDUNDANCY' in (health.json | map(attribute='check') | list)"
"""

RETURN = r"""
status:
  description: HTTP status code croit answered. Not returned when a write was skipped in check mode.
  returned: when the request was sent
  type: int
  sample: 200
json:
  description: The parsed response body, or the raw text when it was not JSON.
  returned: when the request was sent
  type: raw
task:
  description: The final state of the croit background task the request started, when it answered one and O(wait=true).
  returned: when the response was a croit task
  type: dict
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
