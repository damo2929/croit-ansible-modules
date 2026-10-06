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
      - Only this SMB cluster, by name (croit's description) or numeric service id. Fails when it does not exist.
      - All clusters when not set.
    type: str
  gather:
    description:
      - What to return besides the clusters.
      - V(servers) and V(shares) come from croit's gateway lists.
      - V(details) adds each cluster's stored configuration (C(SmbGatewayServiceResponse)) as C(detail).
      - V(users) and V(groups) are only read on generation-2 clusters without Active Directory.
      - V(acls) reads the on-disk ACL of every generation-2 share, one request per share.
    type: list
    elements: str
    choices: [servers, shares, details, users, groups, acls]
    default: [servers, shares]
"""

EXAMPLES = r"""
- name: Every SMB cluster with its servers and shares
  croit.ceph.smb_info:
  register: smb

- name: Users, groups and share ACLs of one cluster
  croit.ceph.smb_info:
    cluster: smb-office
    gather: [shares, users, groups, acls]
"""

RETURN = r"""
clusters:
  description:
    - The SMB clusters (C(SmbGatewayConfigResponse) in the croit API). Each has the requested extras added -
      C(servers), C(shares), C(detail), C(users), C(groups) - and each generation-2 share has an C(acl) with V(acls).
  returned: always
  type: list
  elements: dict
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
