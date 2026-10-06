#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /servers
# croit-api: GET /services

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: service_info
short_description: Read croit and Ceph services from a croit cluster
version_added: 0.1.0
description:
  - Lists the services croit manages, optionally only those of one type, on one server, or with one id.
  - The filters combine; with none set, every service is returned. OSDs are managed with M(croit.ceph.osd).
  - Read-only; it never changes anything and always reports no change.
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
seealso:
  - module: croit.ceph.service
    description: Add, remove, start, stop and restart services.
  - module: croit.ceph.server_info
    description: Read the servers the services run on.
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
options:
  server:
    description:
      - Only services running on this server, by hostname or numeric id. Fails when the server does not exist.
    type: str
  type:
    description:
      - Only services of this type, for example V(mon), V(mgr), V(mds) or V(radosgw).
    type: str
  service_id:
    description:
      - Only the service with this numeric id.
    type: int
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: All monitors
  croit.ceph.service_info:
    type: mon
  register: mons

- name: Show how many monitors the cluster has
  ansible.builtin.debug:
    msg: "{{ mons.services | length }} monitors"

- name: Services on one node
  croit.ceph.service_info:
    server: storage-01
  register: node

- name: Show the ones that are not running
  ansible.builtin.debug:
    msg: "{{ node.services | rejectattr('running') | map(attribute='name') | list }}"
"""

RETURN = r"""
services:
  description: The matching services (C(MultiServerServiceResponse) in the croit API).
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description: croit's numeric service id.
      returned: always
      type: int
      sample: 7
    type:
      description: Service type, for example V(mon), V(mgr), V(mds) or V(radosgw).
      returned: always
      type: str
      sample: mon
    name:
      description: Name of the service.
      returned: always
      type: str
      sample: ceph-mon@storage-01
    server:
      description: croit id of the server it runs on.
      returned: always
      type: int
      sample: 1
    serverHostname:
      description: Hostname of the server it runs on.
      returned: always
      type: str
      sample: storage-01
    state:
      description: Whether croit keeps the service enabled.
      returned: always
      type: str
      sample: enabled
    running:
      description: Whether the service is running.
      returned: always
      type: bool
      sample: true
"""

from ansible_collections.croit.ceph.plugins.module_utils.lookup import require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(server=dict(type="str"), type=dict(type="str"), service_id=dict(type="int")),
        wait=False,
        warnings=False,
    )
    p = m.params
    server_id = require_server(m, p["server"])["id"] if p["server"] is not None else None
    services = []
    for s in m.get_list("/services"):
        if p["type"] is not None and s.get("type") != p["type"]:
            continue
        if p["service_id"] is not None and s.get("id") != p["service_id"]:
            continue
        if server_id is not None and s.get("server") != server_id and server_id not in (s.get("multiServer") or []):
            continue
        services.append(s)
    m.exit(changed=False, services=services)


if __name__ == "__main__":
    main()
