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
  - Makes sure the servers in O(servers) run an object gateway, or do not, and manages each of those gateways' own
    listening ports, DNS name and zone. Gateways are identified by the server they run on.
  - New gateways join the realm, zonegroup and zone the cluster was bootstrapped with. A cluster without S3 is
    bootstrapped with M(croit.ceph.rgw_bootstrap), not with this module. This module also adds the gateways of a
    cluster that joined a multisite setup as a secondary (M(croit.ceph.s3_multisite)).
  - O(port), O(ssl_port), O(dns_name) and O(zone) are only managed when set. Changing any of them restarts the
    affected gateway.
  - Starting, stopping and restarting gateways is done with M(croit.ceph.service) and
    O(croit.ceph.service#module:type=radosgw).
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
      - The diff shows the servers that run a gateway and, when O(port), O(ssl_port), O(dns_name) or O(zone) is set,
        the managed configuration of each gateway in O(servers).
options:
  servers:
    description:
      - Servers to act on, by hostname or numeric id.
    type: list
    elements: str
    required: true
  state:
    description:
      - V(present) adds a gateway to every server in O(servers) that has none.
      - V(absent) removes the gateways of the servers in O(servers). No data is lost, but clients of those gateways
        lose access. croit asks before removing the gateways of every node at once, which needs
        O(ignore_warnings=true).
      - For a gateway service that spans several servers, only the part on the named server is removed.
    type: str
    choices: [present, absent]
    default: present
  exclusive:
    description:
      - With O(state=present), also remove the gateways of all servers that are not in O(servers).
      - Ignored with O(state=absent).
    type: bool
    default: false
  ha_groups:
    description:
      - HA groups, by name or numeric id, whose HA Proxy backend set new gateways are added to (see M(croit.ceph.ha_group)).
      - Only used when a gateway is created; croit adds them on a best-effort basis.
    type: list
    elements: str
  port:
    description:
      - Plain HTTP port of each gateway in O(servers).
      - When unset, the port is left alone. A gateway that relies on croit's default reports no port, so setting the
        default port explicitly counts as a change once.
    type: int
  ssl_port:
    description:
      - TLS port of each gateway in O(servers).
      - When unset, the port is left alone.
    type: int
  dns_name:
    description:
      - DNS name each gateway in O(servers) answers virtual-host style S3 requests for.
      - When unset, the DNS name is left alone.
    type: str
  zone:
    description:
      - RGW zone each gateway in O(servers) serves.
      - When unset, the zone is left alone.
    type: str
notes:
  - Removing every gateway of the cluster leaves S3 unreachable until a gateway is added again.
seealso:
  - module: croit.ceph.rgw_bootstrap
    description: Give a cluster its S3 surface and first gateways.
  - module: croit.ceph.service
    description: Start, stop and restart gateways, or read their state with M(croit.ceph.service_info).
  - module: croit.ceph.ha_group
    description: Manage the HA groups and floating IPs that front the gateways.
  - name: croit API reference
    description: The croit REST API, including the C(/s3/services) and C(/services) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph Object Gateway configuration
    description: Upstream documentation of RGW frontends, ports and DNS names.
    link: https://docs.ceph.com/en/latest/radosgw/config-ref/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Run gateways on three nodes, listening on port 8080 behind an HA group
  croit.ceph.rgw_service:
    servers:
      - node1
      - node2
      - node3
    port: 8080
    ha_groups:
      - s3-vip

- name: Answer virtual-host style requests for s3.example.com
  croit.ceph.rgw_service:
    servers:
      - node1
      - node2
      - node3
    dns_name: s3.example.com
  register: rgw

- name: Show each gateway's configuration
  ansible.builtin.debug:
    var: rgw.config

- name: Run exactly these gateways and remove any others
  croit.ceph.rgw_service:
    servers:
      - node1
      - node2
    exclusive: true
    ignore_warnings: true

- name: Remove the gateway of a node
  croit.ceph.rgw_service:
    servers:
      - node3
    state: absent
"""

RETURN = r"""
gateways:
  description:
    - The object gateway services (C(MultiServerServiceResponse) rows of type V(radosgw)) after the run.
    - In check mode, the gateways as they were before.
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
config:
  description:
    - Each gateway's own configuration after the run, keyed by server hostname (C(RgwServiceConfigResponse) in the
      croit API). A null value means the gateway relies on the cluster-wide default.
  returned: when O(port), O(ssl_port), O(dns_name) or O(zone) is set
  type: dict
  sample:
    node1:
      port: 8080
      sslPort: null
      dnsName: s3.example.com
      zone: dc1
tasks:
  description: Every croit background task the change ran as, in order.
  returned: when the change ran as one or more croit background tasks
  type: list
  elements: dict
  sample:
    - id: 412
      name: Add RGW services
      state: FINISHED
      done: true
task:
  description:
    - The last croit background task the change ran as (C(ManagedTask) in the croit API).
    - With O(wait=true) this is the finished task; with O(wait=false) it may still be running.
  returned: when the change ran as a croit background task
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
      sample: Add RGW services
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
