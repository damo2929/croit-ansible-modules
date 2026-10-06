#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/smb
# croit-api: GET /gateways/smb/servers
# croit-api: GET /gateways/smb/shares
# croit-api: GET /services/smb/{serviceId}
# croit-api: GET /services/smb/{serviceId}/users
# croit-api: GET /services/smb/{serviceId}/groups
# croit-api: GET /services/smb/{serviceId}/shares/{shareId}/acl

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: smb_info
short_description: Read SMB gateway clusters, shares, users and groups from a croit cluster
version_added: 0.1.0
description:
  - Returns croit SMB clusters and, on request, their member servers, shares, managed local users and groups,
    and the on-disk ACLs of their generation-2 shares.
  - Optionally limited to one O(cluster). This module only reads and never changes anything, so it is safe in check
    mode; it never returns passwords.
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
  cluster:
    description:
      - Only this SMB cluster, by name (croit's description) or numeric service id. The task fails when it does not
        exist.
      - All clusters are returned when it is not set.
    type: str
  gather:
    description:
      - What to return besides the clusters.
      - V(servers) and V(shares) come from croit's gateway lists.
      - V(details) adds each cluster's stored configuration (C(SmbGatewayServiceResponse)) as C(detail).
      - V(users) and V(groups) are only read on generation-2 clusters without Active Directory; other clusters get
        empty lists.
      - V(acls) reads the on-disk ACL of every generation-2 share, one request per share, and implies V(shares).
    type: list
    elements: str
    choices: [servers, shares, details, users, groups, acls]
    default: [servers, shares]
seealso:
  - module: croit.ceph.smb_cluster
    description: Manage SMB clusters.
  - module: croit.ceph.smb_share
    description: Manage SMB shares and their ACLs.
  - module: croit.ceph.smb_user
    description: Manage the local users of an SMB cluster.
  - module: croit.ceph.smb_group
    description: Manage the local groups of an SMB cluster.
  - name: croit API reference
    description: The croit REST API this module uses (SMB gateways).
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Read every SMB cluster with its servers and shares
  croit.ceph.smb_info:
  register: smb

- name: List unhealthy SMB members
  ansible.builtin.debug:
    msg: "{{ smb.clusters | map(attribute='servers') | flatten | rejectattr('healthy') | map(attribute='hostname') | list }}"

- name: Read users, groups and share ACLs of one cluster
  croit.ceph.smb_info:
    cluster: smb-office
    gather: [shares, users, groups, acls]
  register: office

- name: Show who can access each share
  ansible.builtin.debug:
    msg: "{{ item.share }}: {{ item.acl.grants | map(attribute='name') | list }}"
  loop: "{{ office.clusters[0].shares }}"
  loop_control:
    label: "{{ item.share }}"
"""

RETURN = r"""
clusters:
  description:
    - The SMB clusters (C(SmbGatewayConfigResponse) in the croit API), each with the extras requested in O(gather) added.
  returned: always
  type: list
  elements: dict
  contains:
    serviceId:
      description: croit's id of the SMB service.
      returned: always
      type: int
      sample: 52
    description:
      description: The cluster's name.
      returned: always
      type: str
      sample: smb-office
    type:
      description: croit's cluster type, V(simple) or V(active-directory).
      returned: always
      type: str
      sample: simple
    configGeneration:
      description: Configuration generation; V(1) is the legacy template, V(2) or later the current one.
      returned: always
      type: int
      sample: 2
    virtualIps:
      description: The cluster's virtual IPs.
      returned: always
      type: list
      elements: str
      sample: [10.0.0.200/24]
    servers:
      description:
        - Member servers (C(SmbGatewayServerResponse)), each with C(serverId), C(hostname), C(ip), C(nic), C(vlan),
          C(virtualIps) and C(healthy).
      returned: when V(servers) is gathered
      type: list
      elements: dict
      sample: [{serverId: 1, hostname: node1, ip: 10.0.0.11, nic: eth0, vlan: null, virtualIps: [10.0.0.200/24], healthy: true}]
    shares:
      description:
        - Shares (C(SmbGatewayShareResponse)), each with C(id), C(share), C(path), C(volume) and C(aclMode), and with
          V(acls) an C(acl) (C(ShareAclReadResult) with C(grants), C(unrepresentable) and C(unresolved)) on
          generation-2 clusters.
      returned: when V(shares) or V(acls) is gathered
      type: list
      elements: dict
      sample: [{id: 3, share: projects, path: /volumes/_nogroup/projects, aclMode: WINDOWS,
                acl: {grants: [{name: admins, group: true, access: READ_WRITE}], unrepresentable: [], unresolved: []}}]
    detail:
      description: The cluster's stored configuration (C(SmbGatewayServiceResponse)).
      returned: when V(details) is gathered
      type: dict
      sample: {type: simple, customizeIdmap: false, cephSnapshots: true, idmapConfigs: []}
    users:
      description: Managed local users (C(SmbUserResponse)) with C(id), C(username), C(uid) and C(groupIds).
      returned: when V(users) is gathered
      type: list
      elements: dict
      sample: [{id: 4, username: alice, uid: 1004, groupIds: [2]}]
    groups:
      description: Managed local groups (C(SmbGroupResponse)) with C(id), C(groupname), C(gid) and C(memberIds).
      returned: when V(groups) is gathered
      type: list
      elements: dict
      sample: [{id: 2, groupname: staff, gid: 1002, memberIds: [4]}]
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.smb import (
    TYPE_SIMPLE,
    cluster_detail,
    generation,
    list_clusters,
    require_cluster,
)

CHOICES = ["servers", "shares", "details", "users", "groups", "acls"]


def main():
    m = CroitModule(
        dict(
            cluster=dict(type="str"),
            gather=dict(type="list", elements="str", choices=CHOICES, default=["servers", "shares"]),
        ),
        wait=False,
        warnings=False,
    )
    gather = set(m.params["gather"])
    clusters = list_clusters(m)
    if m.params["cluster"] is not None:
        clusters = [require_cluster(m, m.params["cluster"], clusters)]

    servers = m.get_list("/gateways/smb/servers") if "servers" in gather else []
    shares = m.get_list("/gateways/smb/shares") if "shares" in gather or "acls" in gather else []

    result = []
    for config in clusters:
        sid = config["serviceId"]
        entry = dict(config)
        base = path_join("services", "smb", sid)
        if "servers" in gather:
            entry["servers"] = [s for s in servers if s.get("serviceId") == sid]
        if "shares" in gather or "acls" in gather:
            own = [dict(s) for s in shares if s.get("serviceId") == sid]
            if "acls" in gather and generation(config) >= 2:
                for share in own:
                    share["acl"] = m.get(path_join("services", "smb", sid, "shares", share["id"], "acl"))
            entry["shares"] = own
        if "details" in gather:
            entry["detail"] = cluster_detail(m, sid)
        managed = config.get("type") == TYPE_SIMPLE and generation(config) >= 2
        if "users" in gather:
            entry["users"] = m.get_list(base + "/users") if managed else []
        if "groups" in gather:
            entry["groups"] = m.get_list(base + "/groups") if managed else []
        result.append(entry)

    m.exit(changed=False, clusters=result)


if __name__ == "__main__":
    main()
