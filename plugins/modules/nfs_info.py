#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/nfs
# croit-api: GET /gateways/nfs/exports
# croit-api: GET /gateways/nfs/servers
# croit-api: GET /services/nfs-gateways/{serviceId}/ha

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nfs_info
short_description: Read NFS gateway clusters, their exports and servers from a croit cluster
version_added: 0.1.0
description:
  - Returns croit's NFS clusters, each with its exports and the servers running it.
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
  name:
    description:
      - Only return the NFS cluster with this name (its croit description).
    type: str
  ha:
    description:
      - Also read the croit-nfs HA view (virtual IPs, placement, Raft state) of every croit-nfs cluster returned.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: All NFS clusters with their exports
  croit.ceph.nfs_info:
  register: nfs

- name: One cluster, including its virtual IPs
  croit.ceph.nfs_info:
    name: nfs-prod
    ha: true
"""

RETURN = r"""
clusters:
  description:
    - The NFS clusters (C(NfsGatewayConfigResponse)), each with C(name), C(exports) (C(NfsGatewayExportResponse))
      and C(servers) (C(NfsGatewayServerResponse)) added, and C(ha) (C(CroitNfsHaView)) with O(ha=true).
  returned: always
  type: list
  elements: dict
  sample:
    - serviceId: 41
      name: nfs-prod
      description: nfs-prod
      implementation: croit_nfs
      exports: [{id: 7, nfsPath: /projects, path: /volumes/_nogroup/projects}]
      servers: [{serverId: 1, hostname: node1, healthy: true}]
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(dict(name=dict(type="str"), ha=dict(type="bool", default=False)), wait=False, warnings=False)
    p = m.params
    clusters = [c for c in m.get_list("/gateways/nfs") if p["name"] is None or c.get("description") == p["name"]]
    if clusters:
        exports = m.get_list("/gateways/nfs/exports")
        servers = m.get_list("/gateways/nfs/servers")
    else:
        exports = servers = []
    result = []
    for cluster in clusters:
        item = dict(cluster)
        item["name"] = cluster.get("description")
        item["exports"] = [e for e in exports if e.get("serviceId") == cluster.get("serviceId")]
        item["servers"] = [s for s in servers if s.get("serviceId") == cluster.get("serviceId")]
        if p["ha"] and cluster.get("implementation") == "croit_nfs":
            item["ha"] = m.get(path_join("services", "nfs-gateways", cluster["serviceId"], "ha"))
        result.append(item)
    m.exit(changed=False, clusters=result)


if __name__ == "__main__":
    main()
