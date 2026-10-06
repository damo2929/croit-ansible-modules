#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/iscsi
# croit-api: GET /gateways/iscsi/servers
# croit-api: GET /gateways/iscsi/disks
# croit-api: GET /gateways/iscsi/groups
# croit-api: GET /gateways/iscsi/hosts
# croit-api: GET /services/iscsi/{serviceId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: iscsi_info
short_description: Read the croit iSCSI gateway
version_added: 0.1.0
description:
  - Returns the cluster's iSCSI gateway, its portal servers, exported disks, host groups and initiators.
  - CHAP passwords are masked unless O(show_secrets=true).
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
  gather:
    description:
      - Which information to gather.
      - V(config) is the raw ceph-iscsi configuration of each gateway.
    type: list
    elements: str
    choices: [gateways, servers, disks, groups, hosts, config]
    default: [gateways, servers, disks, groups, hosts]
  show_secrets:
    description:
      - Return the initiators' CHAP passwords. croit only reveals them to admin tokens.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Read the iSCSI setup
  croit.ceph.iscsi_info:
  register: iscsi

- name: Initiators and their disks
  ansible.builtin.debug:
    msg: "{{ iscsi.hosts | map(attribute='iqn') | list }}"
"""

RETURN = r"""
gateways:
  description: iSCSI gateway services (C(IscsiGatewayConfigResponse)).
  returned: when V(gateways) is gathered
  type: list
  elements: dict
servers:
  description: Portal servers (C(IscsiGatewayServerResponse)).
  returned: when V(servers) is gathered
  type: list
  elements: dict
disks:
  description: Exported disks with the hosts and groups using them (C(IscsiGatewayDisksResponse)).
  returned: when V(disks) is gathered
  type: list
  elements: dict
groups:
  description: Host groups (C(IscsiGatewayGroupsResponse)).
  returned: when V(groups) is gathered
  type: list
  elements: dict
hosts:
  description: Initiators (C(IscsiGatewayHostsResponse)), with C(password) masked unless O(show_secrets=true).
  returned: when V(hosts) is gathered
  type: list
  elements: dict
config:
  description: The ceph-iscsi configuration per gateway service id, with client passwords masked unless O(show_secrets=true).
  returned: when V(config) is gathered
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

MASK = "********"
SOURCES = dict(
    gateways="/gateways/iscsi",
    servers="/gateways/iscsi/servers",
    disks="/gateways/iscsi/disks",
    groups="/gateways/iscsi/groups",
    hosts="/gateways/iscsi/hosts",
)


def mask_password(entry):
    entry = dict(entry)
    if entry.get("password"):
        entry["password"] = MASK
    return entry


def main():
    choices = list(SOURCES) + ["config"]
    m = CroitModule(
        dict(
            gather=dict(type="list", elements="str", choices=choices, default=list(SOURCES)),
            show_secrets=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    p = m.params
    result = {}
    for key in p["gather"]:
        if key == "config":
            continue
        result[key] = m.get_list(SOURCES[key])
    if "hosts" in result and not p["show_secrets"]:
        result["hosts"] = [mask_password(h) for h in result["hosts"]]
    if "config" in p["gather"]:
        services = result.get("gateways") if "gateways" in result else m.get_list(SOURCES["gateways"])
        configs = {}
        for service in services:
            config = m.get(path_join("services", "iscsi", service["serviceId"])) or {}
            if not p["show_secrets"]:
                config = dict(config, clients=[mask_password(c) for c in config.get("clients") or []])
            configs[str(service["serviceId"])] = config
        result["config"] = configs
    m.exit(changed=False, **result)


if __name__ == "__main__":
    main()
