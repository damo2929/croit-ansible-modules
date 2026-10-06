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
  - Lists the subnets croit manages, optionally filtered by CIDR or type.
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
      - Only return the network with this CIDR, for example V(10.10.0.0/24).
    type: str
  type:
    description:
      - Only return networks of this type.
    type: str
    choices: [other, ceph_public, ceph_internal, croit, ipmi]
"""

EXAMPLES = r"""
- name: All networks
  croit.ceph.network_info:
  register: nets

- name: The Ceph public network(s)
  croit.ceph.network_info:
    type: ceph_public
  register: public
"""

RETURN = r"""
networks:
  description:
    - The matching networks (C(NetworkInfo) in the croit API), each with an added C(cidr) member holding
      the canonical network, for example C(10.10.0.0/24).
  returned: always
  type: list
  elements: dict
  sample:
    - id: 4
      cidr: 10.10.0.0/24
      ip: 10.10.0.0
      netmask: 24
      type: ceph_public
      description: ""
      gateway: null
      mtu: null
      poolStart: null
      poolEnd: null
"""

import ipaddress

from ansible.module_utils.common.text.converters import to_text

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
            wanted = ipaddress.ip_network(to_text(m.params["cidr"]).strip(), strict=False)
        except ValueError as e:
            m.module.fail_json(msg="cidr: %s" % e)

    networks = []
    for item in m.get_list("/networks"):
        try:
            net = ipaddress.ip_network(u"%s/%s" % (to_text(item.get("ip")), item.get("netmask")), strict=False)
        except (ValueError, TypeError):
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
