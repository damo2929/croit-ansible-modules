#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /services
# croit-api: GET /servers
# croit-api: GET /servers/ha-groups
# croit-api: GET /services/{serviceId}/rgw-config
# croit-api: POST /s3/services
# croit-api: PATCH /services/{serviceId}
# croit-api: DELETE /services/{serviceId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: rgw_service
short_description: Manage the S3 object gateways (RGW) of a croit cluster
version_added: 0.1.0
description:
  - Makes sure the servers in O(servers) run an object gateway, or do not, and manages each gateway's own
    listening ports, DNS name and zone.
  - New gateways join the realm, zonegroup and zone the cluster was bootstrapped with. A cluster without S3
    is bootstrapped with M(croit.ceph.rgw_bootstrap), not with this module. This module also adds the
    gateways of a cluster that joined a multisite setup as a secondary (M(croit.ceph.s3_multisite)).
  - Changing a gateway's ports, DNS name or zone restarts that gateway.
  - Starting, stopping and restarting gateways is done with M(croit.ceph.service) (O(croit.ceph.service#module:type=radosgw)).
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
      - Servers by hostname or numeric id.
    type: list
    elements: str
    required: true
  state:
    description:
      - V(present) adds a gateway to every server in O(servers) that has none.
      - V(absent) removes the gateways of the servers in O(servers). No data is lost, but clients of those
        gateways lose access. croit asks before removing the gateways of every node at once, which needs
        O(ignore_warnings=true).
    type: str
    choices: [present, absent]
    default: present
  exclusive:
    description:
      - With O(state=present), also remove the gateways of servers not in O(servers).
    type: bool
    default: false
  ha_groups:
    description:
      - HA groups (by name or numeric id) whose HA Proxy backend set new gateways are added to.
      - Only used when a gateway is created. croit adds them best-effort.
    type: list
    elements: str
  port:
    description:
      - Plain HTTP port of each gateway in O(servers). Only managed when set.
    type: int
  ssl_port:
    description:
      - TLS port of each gateway in O(servers). Only managed when set.
    type: int
  dns_name:
    description:
      - DNS name each gateway in O(servers) answers S3 requests for. Only managed when set.
    type: str
  zone:
    description:
      - RGW zone each gateway in O(servers) serves. Only managed when set.
    type: str
"""

EXAMPLES = r"""
- name: Gateways on three nodes, listening on 8080
  croit.ceph.rgw_service:
    servers: [node1, node2, node3]
    port: 8080
    ha_groups: [s3-vip]

- name: Exactly these gateways, remove any others
  croit.ceph.rgw_service:
    servers: [node1, node2]
    exclusive: true
    ignore_warnings: true

- name: Remove the gateway of a node
  croit.ceph.rgw_service:
    servers: [node3]
    state: absent
"""

RETURN = r"""
gateways:
  description: The object gateway services (C(MultiServerServiceResponse) rows of type C(radosgw)) after the run.
  returned: always
  type: list
  elements: dict
config:
  description: Each gateway's own configuration after the run, keyed by server hostname (C(RgwServiceConfigResponse)).
  returned: when O(port), O(ssl_port), O(dns_name) or O(zone) is set
  type: dict
tasks:
  description: The croit tasks the change ran as.
  returned: when a change ran
  type: list
  elements: dict
task:
  description: The last croit task the change ran as.
  returned: when a change ran as a task
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import list_servers, require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

RGW_TYPE = "radosgw"

# Ansible option -> (RgwServiceConfigResponse field, ServiceUpdateRequest field).
CONFIG_FIELDS = dict(
    port=("port", "port"),
    ssl_port=("sslPort", "sslPort"),
    dns_name=("dnsName", "rgwDnsName"),
    zone=("zone", "rgwZone"),
)


def gateway_servers(gateway):
    """Server ids a gateway service runs on."""
    ids = list(gateway.get("multiServer") or [])
    if gateway.get("server") is not None and gateway["server"] >= 0 and gateway["server"] not in ids:
        ids.append(gateway["server"])
    return ids


class RgwServiceModule(CroitModule):
    def __init__(self):
        super(RgwServiceModule, self).__init__(
            dict(
                servers=dict(type="list", elements="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                exclusive=dict(type="bool", default=False),
                ha_groups=dict(type="list", elements="str"),
                port=dict(type="int"),
                ssl_port=dict(type="int"),
                dns_name=dict(type="str"),
                zone=dict(type="str"),
            ),
        )
        self.tasks = []

    # Lookups --------------------------------------------------------------

    def gateways(self):
        return [s for s in self.get_list("/services") if s.get("type") == RGW_TYPE]

    def by_server(self, gateways):
        """Server id -> gateway service running there."""
        mapping = {}
        for gateway in gateways:
            for server_id in gateway_servers(gateway):
                mapping[server_id] = gateway
        return mapping

    def resolve_ha_groups(self):
        names = self.params["ha_groups"]
        if not names:
            return []
        groups = self.get_list("/servers/ha-groups")
        ids = []
        for name in names:
            matches = [g for g in groups if g.get("description") == name]
            if not matches and str(name).isdigit():
                matches = [g for g in groups if g.get("id") == int(name)]
            if len(matches) != 1:
                self.module.fail_json(
                    msg="HA group %r %s. Known groups: %s"
                    % (
                        name,
                        "is ambiguous" if matches else "does not exist",
                        ", ".join("%s (%s)" % (g.get("description"), g.get("id")) for g in groups) or "none",
                    )
                )
            ids.append(matches[0]["id"])
        return ids

    def desired_config(self):
        return dict((opt, self.params[opt]) for opt in CONFIG_FIELDS if self.params[opt] is not None)

    def read_config(self, gateway):
        config = self.get(path_join("services", gateway["id"], "rgw-config")) or {}
        return dict((opt, config.get(api)) for opt, (api, _req) in CONFIG_FIELDS.items())

    def run_task(self, data):
        task = self.handle_task(data)
        if task is not None:
            self.tasks.append(task)

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        servers = list_servers(self)
        names = dict((s["id"], s["hostname"]) for s in servers)
        targets = []
        for name in p["servers"]:
            server = require_server(self, name, servers)
            if server["id"] not in targets:
                targets.append(server["id"])

        gateways = self.gateways()
        mapping = self.by_server(gateways)
        before_servers = sorted(names.get(i, str(i)) for i in mapping)

        if p["state"] == "absent":
            remove = [i for i in targets if i in mapping]
            add = []
        else:
            add = [i for i in targets if i not in mapping]
            remove = [i for i in mapping if p["exclusive"] and i not in targets]
        ha_group_ids = self.resolve_ha_groups() if add else []

        desired = self.desired_config() if p["state"] == "present" else {}
        before = dict(servers=before_servers)
        kept = set(before_servers) - set(names.get(i, str(i)) for i in remove)
        after = dict(servers=sorted(kept | set(names[i] for i in add)))
        patches = []
        if desired:
            before["config"] = {}
            after["config"] = {}
            for server_id in targets:
                hostname = names[server_id]
                if server_id in mapping:
                    current = self.read_config(mapping[server_id])
                    view = dict((opt, current.get(opt)) for opt in desired)
                    before["config"][hostname] = view
                    after["config"][hostname] = dict(view, **desired)
                    if view != after["config"][hostname]:
                        patches.append(server_id)
                else:
                    after["config"][hostname] = dict(desired)

        changed = bool(add or remove or patches)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, gateways=gateways, **self.config_result(desired, mapping, names, targets))

        if add:
            body = dict(serverIds=add)
            if ha_group_ids:
                body["haGroupIds"] = ha_group_ids
            self.run_task(self.write("POST", "/s3/services", body=body))
        for server_id in remove:
            gateway = mapping[server_id]
            query = dict(server=server_id) if len(gateway_servers(gateway)) > 1 else None
            self.run_task(self.write("DELETE", path_join("services", gateway["id"]), query=query))

        if desired:
            mapping = self.by_server(self.gateways())
            for server_id in targets:
                gateway = mapping.get(server_id)
                if gateway is None:
                    continue
                if server_id in add or server_id in patches:
                    current = self.read_config(gateway)
                    body = dict(
                        (CONFIG_FIELDS[opt][1], value) for opt, value in desired.items() if current.get(opt) != value
                    )
                    if body:
                        self.run_task(self.write("PATCH", path_join("services", gateway["id"]), body=body))

        gateways = self.gateways()
        result = dict(changed=True, before=before, after=after, gateways=gateways)
        result.update(self.config_result(desired, self.by_server(gateways), names, targets))
        if self.tasks:
            result["tasks"] = self.tasks
            result["task"] = self.tasks[-1]
        self.exit(**result)

    def config_result(self, desired, mapping, names, targets):
        if not desired:
            return {}
        config = {}
        for server_id in targets:
            if server_id in mapping:
                gateway = mapping[server_id]
                config[names[server_id]] = self.get(path_join("services", gateway["id"], "rgw-config")) or {}
        return dict(config=config)


def main():
    RgwServiceModule().run()


if __name__ == "__main__":
    main()
