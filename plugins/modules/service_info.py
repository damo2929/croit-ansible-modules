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
- name: All monitors
  croit.ceph.service_info:
    type: mon
  register: mons

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
  sample:
    - id: 7
      type: mon
      name: ceph-mon@storage-01
      server: 1
      serverHostname: storage-01
      state: enabled
      running: true
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
