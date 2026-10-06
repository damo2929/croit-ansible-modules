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
  - This module only reads; it never changes anything and supports check mode.
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
      - Which information to gather. Each value adds the return value of the same name.
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
seealso:
  - module: croit.ceph.iscsi_gateway
    description: Manage the iSCSI gateway and its portals.
  - module: croit.ceph.iscsi_client
    description: Manage initiators and their disks.
  - module: croit.ceph.iscsi_group
    description: Manage host groups.
  - module: croit.ceph.iscsi_disk
    description: Grow, unexport or delete exported disks.
  - name: Ceph iSCSI gateway
    description: Upstream documentation of the Ceph iSCSI gateway.
    link: https://docs.ceph.com/en/latest/rbd/iscsi-overview/
  - name: croit API reference
    description: The croit REST API this module talks to.
    link: https://www.croit.io/api-docs
notes:
  - With O(show_secrets=true) the CHAP passwords are returned in clear text. Set the task's C(no_log) keyword to
    keep them out of logs.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Read the iSCSI setup
  croit.ceph.iscsi_info:
  register: iscsi

- name: List the IQNs of the initiators
  ansible.builtin.debug:
    msg: "{{ iscsi.hosts | map(attribute='iqn') | list }}"

- name: Only the exported disks
  croit.ceph.iscsi_info:
    gather: [disks]
  register: iscsi_disks

- name: Show which hosts use each disk
  ansible.builtin.debug:
    msg: "{{ item.pool }}/{{ item.image }}: {{ item.hosts | join(', ') }}"
  loop: "{{ iscsi_disks.disks }}"

- name: Raw ceph-iscsi configuration including CHAP passwords
  croit.ceph.iscsi_info:
    gather: [config]
    show_secrets: true
  no_log: true
  register: iscsi_config
"""

RETURN = r"""
gateways:
  description: iSCSI gateway services (C(IscsiGatewayConfigResponse) in the croit API).
  returned: when V(gateways) is in O(gather)
  type: list
  elements: dict
  contains:
    serviceId:
      description: croit service id of the gateway.
      returned: always
      type: int
      sample: 7
    description:
      description: Description of the gateway service.
      returned: always
      type: str
      sample: VMware datastores
servers:
  description: Portal servers of the gateways (C(IscsiGatewayServerResponse)).
  returned: when V(servers) is in O(gather)
  type: list
  elements: dict
  contains:
    serviceId:
      description: croit service id of the gateway the portal belongs to.
      returned: always
      type: int
      sample: 7
    serverId:
      description: croit id of the portal server.
      returned: always
      type: int
      sample: 1
    hostname:
      description: Hostname of the portal server.
      returned: always
      type: str
      sample: storage-1
    ip:
      description: Client-facing IP address of the portal.
      returned: always
      type: str
      sample: 10.10.0.11
    healthy:
      description: Whether the gateway is healthy on that server.
      returned: always
      type: bool
      sample: true
disks:
  description: Exported disks with the hosts and groups using them (C(IscsiGatewayDisksResponse)).
  returned: when V(disks) is in O(gather)
  type: list
  elements: dict
  contains:
    serviceId:
      description: croit service id of the gateway.
      returned: always
      type: int
      sample: 7
    pool:
      description: RBD pool of the disk.
      returned: always
      type: str
      sample: iscsi
    image:
      description: RBD image name of the disk.
      returned: always
      type: str
      sample: datastore1
    wwn:
      description: WWN of the disk on the target.
      returned: always
      type: str
      sample: 3f0e8c7a-0c1d-4a5e-9b6f-2d3c4b5a6f70
    lunId:
      description: LUN id of the disk, when croit knows it.
      returned: always
      type: int
      sample: 0
    hosts:
      description: IQNs of the initiators the disk is mapped to.
      returned: always
      type: list
      elements: str
      sample: [iqn.1998-01.com.vmware:esx01-12345678]
    groups:
      description: Host groups the disk is mapped to.
      returned: always
      type: list
      elements: str
      sample: [esx-cluster]
groups:
  description: Host groups (C(IscsiGatewayGroupsResponse)).
  returned: when V(groups) is in O(gather)
  type: list
  elements: dict
  contains:
    serviceId:
      description: croit service id of the gateway.
      returned: always
      type: int
      sample: 7
    group:
      description: Name of the host group.
      returned: always
      type: str
      sample: esx-cluster
    members:
      description: IQNs of the initiators in the group.
      returned: always
      type: list
      elements: str
      sample: [iqn.1998-01.com.vmware:esx01-12345678]
    luns:
      description: Disks mapped to the group, with the same fields as RV(disks).
      returned: always
      type: list
      elements: dict
      sample: []
hosts:
  description: Initiators (C(IscsiGatewayHostsResponse)).
  returned: when V(hosts) is in O(gather)
  type: list
  elements: dict
  contains:
    serviceId:
      description: croit service id of the gateway.
      returned: always
      type: int
      sample: 7
    iqn:
      description: IQN of the initiator.
      returned: always
      type: str
      sample: iqn.1998-01.com.vmware:esx01-12345678
    username:
      description: CHAP username.
      returned: always
      type: str
      sample: esx01-user
    password:
      description: CHAP password, masked as C(********) unless O(show_secrets=true).
      returned: always
      type: str
      sample: "********"
    group:
      description: Host group of the initiator, or an empty string.
      returned: always
      type: str
      sample: ""
    luns:
      description: Disks mapped to the initiator, with the same fields as RV(disks).
      returned: always
      type: list
      elements: dict
      sample: []
config:
  description:
    - The ceph-iscsi configuration (C(IscsiGatewayConfig) in the croit API) of each gateway, keyed by the gateway's
      service id as a string.
    - Client passwords are masked as C(********) unless O(show_secrets=true).
  returned: when V(config) is in O(gather)
  type: dict
  sample:
    "7":
      iqn: iqn.2001-07.com.ceph:1700000000000
      selectedTarget: iqn.2001-07.com.ceph:1700000000000
      targets: [iqn.2001-07.com.ceph:1700000000000]
      gateways:
        - name: storage-1
          ip: 10.10.0.11
      clients: []
      groups: []
      disks: []
      gatewayVersion: 12
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
