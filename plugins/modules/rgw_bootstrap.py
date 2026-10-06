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
  - Gives a cluster its S3 surface once. croit creates the pools the object gateways store their data in, the
    realm, zonegroup and zone, and one object gateway on each server in O(servers).
  - croit only bootstraps a cluster that runs no object gateway yet. If the cluster already runs one, the module
    reports no change and does not compare O(servers). Use M(croit.ceph.rgw_service) to add or remove gateways
    afterwards.
  - A cluster that joined a multisite setup as a secondary (M(croit.ceph.s3_multisite)) must not be bootstrapped.
    The module refuses to bootstrap it; add its gateways with M(croit.ceph.rgw_service) instead.
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
    details:
      - The diff shows whether the cluster gets bootstrapped and with which servers, realm, zonegroup and zone.
options:
  servers:
    description:
      - Servers to deploy the first object gateways on, by hostname or numeric id. At least one is required.
      - Only used when bootstrapping; on a cluster that already runs a gateway this list is not compared.
    type: list
    elements: str
    required: true
  realm:
    description:
      - Realm to bootstrap in. When not set, croit uses the ceph configuration, then the realm the cluster already
        has, then V(default).
      - Only used when bootstrapping. The realm cannot be read back and is not compared afterwards.
    type: str
  zonegroup:
    description:
      - Zonegroup to bootstrap in, with the same defaults as O(realm).
      - Only used when bootstrapping. The zonegroup cannot be read back and is not compared afterwards.
    type: str
  zone:
    description:
      - Zone to bootstrap in, with the same defaults as O(realm).
      - On a cluster that is already bootstrapped, a gateway that is configured for another zone than this one
        fails the task, because the zone cannot be changed here.
    type: str
notes:
  - Bootstrapping creates pools and starts gateways. It cannot be undone with this module; remove gateways with
    M(croit.ceph.rgw_service) and pools with M(croit.ceph.pool).
seealso:
  - module: croit.ceph.rgw_service
    description: Add, remove and configure object gateways after the bootstrap.
  - module: croit.ceph.s3_multisite
    description: Make the cluster a multisite primary or join another site as a secondary.
  - module: croit.ceph.s3_placement
    description: Manage the placement rules and storage classes of the zone.
  - name: croit API reference
    description: The croit REST API, including the C(/s3/bootstrap) endpoint this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph Object Gateway
    description: Upstream documentation of the Ceph object gateway (RGW).
    link: https://docs.ceph.com/en/latest/radosgw/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Bootstrap S3 with gateways on two nodes
  croit.ceph.rgw_bootstrap:
    servers:
      - node1
      - node2

- name: Bootstrap S3 in a named realm, zonegroup and zone
  croit.ceph.rgw_bootstrap:
    servers:
      - node1
      - node2
    realm: company
    zonegroup: eu
    zone: dc1
  register: bootstrap

- name: List the gateways the cluster now runs
  ansible.builtin.debug:
    msg: "{{ bootstrap.gateways | map(attribute='serverHostname') | list }}"
"""

RETURN = r"""
gateways:
  description:
    - The object gateway services (C(MultiServerServiceResponse) rows of type V(radosgw)) after the run.
    - Empty in check mode when the cluster would be bootstrapped.
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description: The service's id.
      returned: always
      type: int
      sample: 31
    name:
      description: The full systemd service name.
      returned: always
      type: str
      sample: ceph-radosgw@rgw.node1
    type:
      description: The service type, always V(radosgw) here.
      returned: always
      type: str
      sample: radosgw
    server:
      description: The id of the server the gateway runs on.
      returned: always
      type: int
      sample: 3
    serverHostname:
      description: The hostname of the server the gateway runs on.
      returned: always
      type: str
      sample: node1
    multiServer:
      description: Every server id the service runs on, for a gateway service that spans several servers.
      returned: always
      type: list
      elements: int
      sample: []
    running:
      description: Whether the gateway is running.
      returned: always
      type: bool
      sample: true
    state:
      description: croit's state of the service.
      returned: always
      type: str
      sample: ENABLED
task:
  description:
    - The croit background task the change ran as (C(ManagedTask) in the croit API).
    - With O(wait=true) this is the finished task; with O(wait=false) it may still be running.
  returned: when the cluster was bootstrapped
  type: dict
  contains:
    id:
      description: The task's id, usable with M(croit.ceph.task) and M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as croit's task list shows it.
      returned: always
      type: str
      sample: Bootstrap S3
    state:
      description: The task's state, one of V(WAITING), V(RUNNING), V(FINISHED), V(FAILED) or V(CANCELED).
      returned: always
      type: str
      sample: FINISHED
    done:
      description: Whether the task has ended.
      returned: always
      type: bool
      sample: true
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: Creating user backup ... done
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
