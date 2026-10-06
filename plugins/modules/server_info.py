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
  - Returns the servers (nodes) croit manages, with their state, addresses, image and service counts.
  - Optionally adds each server's network interfaces and VLANs.
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
  - module: croit.ceph.server
    description: Change server settings and reboot, shut down or forget servers.
  - module: croit.ceph.server_nic
    description: Manage the network interfaces of a server.
  - module: croit.ceph.disk_info
    description: Read the disks of the servers.
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
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
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

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
  register: node

- name: Show the interface names of that server
  ansible.builtin.debug:
    msg: "{{ node.servers[0].nics | map(attribute='name') | list }}"
"""

RETURN = r"""
servers:
  description:
    - The servers (C(ServerResponse) in the croit API), in croit's order, or in the order of O(servers).
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description: croit's numeric server id.
      returned: always
      type: int
      sample: 7
    hostname:
      description: Hostname of the server.
      returned: always
      type: str
      sample: storage-07
    ip:
      description: Management IP croit reaches the node on.
      returned: always
      type: str
      sample: 10.0.0.17
    state:
      description: V(booting), V(running), V(offline), V(rebooting) or V(shutting_down).
      returned: always
      type: str
      sample: running
    image:
      description: OS image the server boots, or V(default).
      returned: always
      type: str
      sample: "2510.0.squid"
    services:
      description: Number of each service type the server carries, keyed by type.
      returned: always
      type: dict
      sample: {osd: 12, mon: 1}
    nics:
      description:
        - The server's network interfaces (C(NicResponse) in the croit API), each with C(id), C(name),
          C(linuxName), C(mac), C(ip), C(ip6), C(type) and C(vlans).
      returned: when O(include_nics=true)
      type: list
      elements: dict
      sample:
        - id: 31
          name: eth0
          linuxName: enp1s0f0
          mac: "0c:c4:7a:aa:bb:01"
          ip: 10.0.0.17/24
          type: ethernet
          vlans: []
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
