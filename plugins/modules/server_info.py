#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /servers
# croit-api: GET /servers/nics

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: server_info
short_description: Read the servers (nodes) of a croit cluster
version_added: 0.1.0
description:
  - Returns the servers croit manages, optionally with their network interfaces.
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
  servers:
    description:
      - Only return these servers, by hostname or numeric id. Unknown servers fail the task.
      - All servers when not set.
    type: list
    elements: str
  include_nics:
    description:
      - Add each server's network interfaces (with their VLANs) as C(nics).
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: All servers
  croit.ceph.server_info:
  register: nodes

- name: Hostnames of the nodes that are not running
  ansible.builtin.debug:
    msg: "{{ nodes.servers | rejectattr('state', 'eq', 'running') | map(attribute='hostname') | list }}"

- name: One server with its interfaces
  croit.ceph.server_info:
    servers: [storage-07]
    include_nics: true
"""

RETURN = r"""
servers:
  description:
    - The servers (C(ServerResponse) in the croit API).
    - With O(include_nics=true) each one also has C(nics), a list of C(NicResponse).
  returned: always
  type: list
  elements: dict
  sample:
    - id: 7
      hostname: storage-07
      ip: 10.0.0.17
      state: running
      image: "2510.0.squid"
"""

from ansible_collections.croit.ceph.plugins.module_utils.lookup import list_servers, require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            servers=dict(type="list", elements="str"),
            include_nics=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    p = m.params
    servers = list_servers(m)
    if p["servers"]:
        selected = []
        for name in p["servers"]:
            found = require_server(m, name, servers)
            if found not in selected:
                selected.append(found)
        servers = selected
    if p["include_nics"]:
        nics = m.get_list("/servers/nics")
        for server in servers:
            server["nics"] = [n for n in nics if n.get("server") == server.get("id")]
    m.exit(changed=False, servers=servers)


if __name__ == "__main__":
    main()
