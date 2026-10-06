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
  - Optionally filters by cluster O(name) and adds the croit-nfs HA view (virtual IPs, placement and Raft state).
  - This module only reads and never changes anything, so it is safe in check mode.
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
      - When not set, every NFS cluster is returned. A name that matches no cluster returns an empty list.
    type: str
  ha:
    description:
      - Also read the croit-nfs HA view (virtual IPs, placement and Raft state) of every croit-nfs cluster returned.
      - nfs-ganesha clusters never get an HA view; their floating IPs are read with M(croit.ceph.ha_group).
    type: bool
    default: false
seealso:
  - module: croit.ceph.nfs_cluster
    description: Manage NFS clusters.
  - module: croit.ceph.nfs_export
    description: Manage the exports of an NFS cluster.
  - name: croit API reference
    description: The croit REST API this module uses (NFS gateways).
    link: https://www.croit.io/api-docs
  - name: CephFS and NFS
    description: Upstream Ceph documentation on exporting CephFS over NFS.
    link: https://docs.ceph.com/en/latest/cephfs/nfs/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Read all NFS clusters with their exports
  croit.ceph.nfs_info:
  register: nfs

- name: List the exported paths of every cluster
  ansible.builtin.debug:
    msg: "{{ item.name }}: {{ item.exports | map(attribute='nfsPath') | list }}"
  loop: "{{ nfs.clusters }}"
  loop_control:
    label: "{{ item.name }}"

- name: Read one cluster, including its virtual IPs
  croit.ceph.nfs_info:
    name: nfs-prod
    ha: true
  register: prod

- name: Check that every member of the cluster is healthy
  ansible.builtin.assert:
    that: prod.clusters[0].servers | rejectattr('healthy') | list | length == 0
"""

RETURN = r"""
clusters:
  description:
    - The NFS clusters (C(NfsGatewayConfigResponse)), each with C(name), C(exports) and C(servers) added, and C(ha) with
      O(ha=true) for croit-nfs clusters.
  returned: always
  type: list
  elements: dict
  contains:
    serviceId:
      description: croit's id of the NFS service.
      returned: always
      type: int
      sample: 41
    name:
      description: The cluster's name, the same as C(description).
      returned: always
      type: str
      sample: nfs-prod
    description:
      description: The cluster's croit description.
      returned: always
      type: str
      sample: nfs-prod
    implementation:
      description: NFS implementation serving the cluster, V(ganesha) or V(croit_nfs).
      returned: always
      type: str
      sample: croit_nfs
    exports:
      description:
        - The cluster's exports (C(NfsGatewayExportResponse)), each with C(id), C(nfsPath), C(path), C(volume),
          C(access) and C(protocols).
      returned: always
      type: list
      elements: dict
      sample: [{id: 7, nfsPath: /projects, path: /volumes/_nogroup/projects, volume: null,
                access: [{subnet: 10.0.0.0/24, rw: true}], protocols: {nfs3: false, nfs4: true}}]
    servers:
      description:
        - The servers running the cluster (C(NfsGatewayServerResponse)), each with C(serverId), C(hostname), C(ip) and
          C(healthy).
      returned: always
      type: list
      elements: dict
      sample: [{serverId: 1, hostname: node1, ip: 10.0.0.11, healthy: true}]
    ha:
      description:
        - The croit-nfs HA view (C(CroitNfsHaView)) with C(vips), C(members), C(haPossible) and C(quorumHealthy).
      returned: with O(ha=true) for croit-nfs clusters
      type: dict
      sample: {vips: [10.0.0.250/24], haPossible: true, quorumHealthy: true, members: []}
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
