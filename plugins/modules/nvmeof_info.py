#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/nvmeof
# croit-api: GET /gateways/nvmeof/services
# croit-api: GET /gateways/nvmeof/listeners
# croit-api: GET /gateways/nvmeof/subsystems
# croit-api: GET /gateways/nvmeof/disks
# croit-api: GET /gateways/nvmeof/hosts
# croit-api: GET /gateways/nvmeof/ceph-clusters

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nvmeof_info
short_description: Read the NVMe-oF configuration of a croit cluster
version_added: 0.1.0
description:
  - Returns croit's NVMe-oF clusters, target services, listeners, subsystems, exported disks, hosts and ceph
    cluster configurations, optionally for one NVMe-oF cluster only.
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
  gateway:
    description:
      - Only return what belongs to this NVMe-oF cluster, by name or numeric id.
      - Ceph cluster configurations are shared by all NVMe-oF clusters and are never filtered.
    type: str
  gather:
    description:
      - What to return.
    type: list
    elements: str
    choices: [gateways, services, listeners, subsystems, disks, hosts, ceph_clusters]
    default: [gateways, services, listeners, subsystems, disks, hosts, ceph_clusters]
  show_secrets:
    description:
      - Return the hosts' shared keys. Needs a token with the admin role; otherwise croit answers C((masked)).
      - By default every shared key is replaced by C(********).
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Everything about one NVMe-oF cluster
  croit.ceph.nvmeof_info:
    gateway: nvme-prod
  register: nvme

- name: Exported disks of all clusters
  croit.ceph.nvmeof_info:
    gather: [disks]
"""

RETURN = r"""
gateways:
  description: NVMe-oF clusters (C(NvmeOFGatewayResponse)).
  returned: when V(gateways) is gathered
  type: list
  elements: dict
services:
  description: Target services (C(NvmeOFServiceResponse)), including their listeners.
  returned: when V(services) is gathered
  type: list
  elements: dict
listeners:
  description: Listeners of all target services (C(NvmeOFListenerConfigResponse)).
  returned: when V(listeners) is gathered
  type: list
  elements: dict
subsystems:
  description: Subsystems (C(NvmeOFSubsystemResponse)).
  returned: when V(subsystems) is gathered
  type: list
  elements: dict
disks:
  description: Exported disks (C(NvmeOFDiskResponse)).
  returned: when V(disks) is gathered
  type: list
  elements: dict
hosts:
  description: Hosts allowed onto the clusters (C(NvmeOFHostResponse)); shared keys are masked unless O(show_secrets=true).
  returned: when V(hosts) is gathered
  type: list
  elements: dict
ceph_clusters:
  description: Ceph cluster configurations the targets read images through (C(NvmeOFCephClusterResponse)).
  returned: when V(ceph_clusters) is gathered
  type: list
  elements: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_one
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

SOURCES = dict(
    gateways="/gateways/nvmeof",
    services="/gateways/nvmeof/services",
    listeners="/gateways/nvmeof/listeners",
    subsystems="/gateways/nvmeof/subsystems",
    disks="/gateways/nvmeof/disks",
    hosts="/gateways/nvmeof/hosts",
    ceph_clusters="/gateways/nvmeof/ceph-clusters",
)


def main():
    choices = list(SOURCES)
    m = CroitModule(
        dict(
            gateway=dict(type="str"),
            gather=dict(type="list", elements="str", choices=choices, default=choices),
            show_secrets=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    p = m.params
    gateway_id = None
    gateways = None
    if p["gateway"] is not None:
        gateways = m.get_list(SOURCES["gateways"])
        text = str(p["gateway"])
        try:
            found = find_one(gateways, "NVMe-oF cluster", "name", text)
            if found is None and text.isdigit():
                found = find_one(gateways, "NVMe-oF cluster", "gatewayId", int(text))
        except ValueError as e:
            m.module.fail_json(msg=str(e))
        if found is None:
            m.module.fail_json(
                msg="NVMe-oF cluster %r does not exist. Known clusters: %s"
                % (p["gateway"], ", ".join("%s (%s)" % (g.get("name"), g.get("gatewayId")) for g in gateways) or "none")
            )
        gateway_id = found["gatewayId"]

    result = {}
    for key in p["gather"]:
        rows = gateways if key == "gateways" and gateways is not None else m.get_list(SOURCES[key])
        if gateway_id is not None and key != "ceph_clusters":
            rows = [r for r in rows if r.get("gatewayId") == gateway_id]
        if key == "hosts" and not p["show_secrets"]:
            rows = [dict(r, sharedKey="********") if r.get("sharedKey") else r for r in rows]
        result[key] = rows
    m.exit(changed=False, **result)


if __name__ == "__main__":
    main()
