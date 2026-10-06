#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /networks

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: network_info
short_description: Read the networks croit knows on a croit cluster
version_added: 0.1.0
description:
  - Lists the subnets croit manages, which it uses for node addresses, DHCP and PXE boot, and for the Ceph public
    and cluster networks.
  - The result can be filtered by O(cidr) or O(type). Each network gets an added C(cidr) member with its
    canonical network, so results can be matched against M(croit.ceph.network) tasks.
  - The module never changes anything.
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
  cidr:
    description:
      - Only return the network with this CIDR, for example V(10.10.0.0/24). A host address with a prefix such
        as V(10.10.0.5/24) names the same network.
      - When not set, networks of every CIDR are returned.
    type: str
  type:
    description:
      - Only return networks of this type. When not set, networks of every type are returned.
    type: str
    choices: [other, ceph_public, ceph_internal, croit, ipmi]
seealso:
  - module: croit.ceph.network
    description: Create, update and delete networks.
  - name: croit API reference
    description: The C(/networks) endpoint this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: All networks
  croit.ceph.network_info:
  register: nets

- name: Show every network in CIDR notation
  ansible.builtin.debug:
    msg: "{{ nets.networks | map(attribute='cidr') | list }}"

- name: The Ceph public network(s)
  croit.ceph.network_info:
    type: ceph_public
  register: public

- name: Use the public network in another task
  ansible.builtin.debug:
    msg: "Ceph public network is {{ public.networks[0].cidr }}"
  when: public.networks | length > 0
"""

RETURN = r"""
networks:
  description: The matching networks (C(NetworkInfo) in the croit API), each with an added C(cidr) member.
  returned: always
  type: list
  elements: dict
  contains:
    cidr:
      description: The canonical network in CIDR notation, added by this module; null if croit's row is unusable.
      returned: always
      type: str
      sample: 10.10.0.0/24
    id:
      description: croit's id of the network.
      returned: always
      type: int
      sample: 4
    ip:
      description: An address in the network, not necessarily the network address; together with C(netmask) it gives the CIDR.
      returned: always
      type: str
      sample: 10.10.0.0
    netmask:
      description: The CIDR prefix length.
      returned: always
      type: int
      sample: 24
    type:
      description: What croit uses the network for.
      returned: always
      type: str
      sample: ceph_public
    description:
      description: Free-text notes.
      returned: always
      type: str
      sample: public network, bond0
    gateway:
      description: Default route installed on servers in this network, or null.
      returned: always
      type: str
      sample: 10.10.0.1
    mtu:
      description: Custom MTU, or null for the default of 1500.
      returned: always
      type: int
      sample: 9000
    poolStart:
      description: First address of the DHCP pool, or null.
      returned: always
      type: str
      sample: 192.168.100.100
    poolEnd:
      description: Last address of the DHCP pool, or null.
      returned: always
      type: str
      sample: 192.168.100.200
"""

from ansible.module_utils.common.text.converters import to_text

from ansible_collections.croit.ceph.plugins.module_utils.ip import ip_network
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            cidr=dict(type="str"),
            type=dict(type="str", choices=["other", "ceph_public", "ceph_internal", "croit", "ipmi"]),
        ),
        wait=False,
        warnings=False,
    )
    wanted = None
    if m.params["cidr"]:
        try:
            wanted = ip_network(to_text(m.params["cidr"]))
        except ValueError as e:
            m.module.fail_json(msg="cidr: %s" % e)

    networks = []
    for item in m.get_list("/networks"):
        try:
            net = ip_network(u"%s/%s" % (to_text(item.get("ip")), item.get("netmask")))
        except ValueError:
            net = None
        if wanted is not None and net != wanted:
            continue
        if m.params["type"] and item.get("type") != m.params["type"]:
            continue
        item = dict(item)
        item["cidr"] = str(net) if net is not None else None
        networks.append(item)
    m.exit(changed=False, networks=networks)


if __name__ == "__main__":
    main()
