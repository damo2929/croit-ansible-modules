#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /services
# croit-api: GET /servers
# croit-api: GET /s3/multisite/status
# croit-api: GET /services/{serviceId}/rgw-config
# croit-api: POST /s3/bootstrap

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: rgw_bootstrap
short_description: Bootstrap S3 (RGW) on a croit cluster
version_added: 0.1.0
description:
  - Gives a cluster its S3 surface once. croit creates the pools the object gateways store in, the realm,
    zonegroup and zone, and one object gateway on each server in O(servers).
  - croit only bootstraps a cluster that runs no object gateway yet. If the cluster already runs one, the
    module reports no change and does not compare O(servers). Use M(croit.ceph.rgw_service) to add or remove
    gateways afterwards.
  - A cluster that joined a multisite setup as a secondary (M(croit.ceph.s3_multisite)) must not be
    bootstrapped. Its gateways are added with M(croit.ceph.rgw_service) instead, and the module refuses
    to bootstrap it.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  servers:
    description:
      - Servers to deploy the first object gateways on, by hostname or numeric id. At least one.
    type: list
    elements: str
    required: true
  realm:
    description:
      - Realm to bootstrap in. When not set, croit uses the ceph configuration, then the realm the
        cluster already has, then V(default).
      - Only used when bootstrapping. On a bootstrapped cluster, a gateway that is itself configured for
        another zone than O(zone) fails the task. The realm and zonegroup cannot be read back and are not
        compared.
    type: str
  zonegroup:
    description:
      - Zonegroup to bootstrap in, with the same defaults as O(realm).
    type: str
  zone:
    description:
      - Zone to bootstrap in, with the same defaults as O(realm).
    type: str
"""

EXAMPLES = r"""
- name: Bootstrap S3 with gateways on two nodes
  croit.ceph.rgw_bootstrap:
    servers: [node1, node2]
    zone: dc1

- name: Add a third gateway later
  croit.ceph.rgw_service:
    servers: [node3]
"""

RETURN = r"""
gateways:
  description: The object gateway services (C(MultiServerServiceResponse) rows of type C(radosgw)) after the run.
  returned: always
  type: list
  elements: dict
task:
  description: The croit task the bootstrap ran as.
  returned: when the cluster was bootstrapped
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import list_servers, require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

RGW_TYPE = "radosgw"


def rgw_gateways(croit_module):
    return [s for s in croit_module.get_list("/services") if s.get("type") == RGW_TYPE]


class RgwBootstrapModule(CroitModule):
    def __init__(self):
        super(RgwBootstrapModule, self).__init__(
            dict(
                servers=dict(type="list", elements="str", required=True),
                realm=dict(type="str"),
                zonegroup=dict(type="str"),
                zone=dict(type="str"),
            ),
        )

    def run(self):
        p = self.params
        if not p["servers"]:
            self.module.fail_json(msg="servers must name at least one server")
        servers = list_servers(self)
        targets = []
        for name in p["servers"]:
            server = require_server(self, name, servers)
            if server not in targets:
                targets.append(server)

        gateways = rgw_gateways(self)
        if gateways:
            self.check_zone(gateways)
            self.exit(changed=False, gateways=gateways)

        status = self.get("/s3/multisite/status") or {}
        if status.get("enabled") and status.get("type") != "PRIMARY":
            self.module.fail_json(
                msg="This cluster joined a multisite setup as a secondary; do not bootstrap it. "
                "Add its gateways with croit.ceph.rgw_service."
            )

        after = dict(
            bootstrapped=True,
            servers=sorted(s["hostname"] for s in targets),
            realm=p["realm"],
            zonegroup=p["zonegroup"],
            zone=p["zone"],
        )
        before = dict(bootstrapped=False)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, gateways=[])

        body = dict(serverIds=[s["id"] for s in targets])
        for opt in ("realm", "zonegroup", "zone"):
            if p[opt] is not None:
                body[opt] = p[opt]
        task = self.handle_task(self.write("POST", "/s3/bootstrap", body=body))
        result = dict(changed=True, before=before, after=after, gateways=rgw_gateways(self))
        if task is not None:
            result["task"] = task
        self.exit(**result)

    def check_zone(self, gateways):
        zone = self.params["zone"]
        if zone is None:
            return
        for gateway in gateways:
            config = self.get(path_join("services", gateway["id"], "rgw-config")) or {}
            if config.get("zone") not in (None, zone):
                self.module.fail_json(
                    msg="S3 is already bootstrapped and gateway %s serves zone %r, not %r; croit.ceph.rgw_bootstrap "
                    "cannot change it" % (gateway.get("name") or gateway["id"], config.get("zone"), zone)
                )


def main():
    RgwBootstrapModule().run()


if __name__ == "__main__":
    main()
