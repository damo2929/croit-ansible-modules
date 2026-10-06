#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/nfs
# croit-api: POST /services/nfs-gateways
# croit-api: GET /services/nfs-gateways/{serviceId}
# croit-api: PATCH /services/nfs-gateways/{serviceId}
# croit-api: PATCH /services/nfs-gateways/{serviceId}/implementation
# croit-api: GET /services/nfs-gateways/{serviceId}/ha
# croit-api: PUT /services/nfs-gateways/{serviceId}/ha
# croit-api: DELETE /services/nfs-gateways/{serviceId}/ha
# croit-api: DELETE /services/{serviceId}
# croit-api: GET /servers
# croit-api: GET /servers/{serverId}/nics

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nfs_cluster
short_description: Manage NFS gateway clusters on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete croit NFS gateway clusters (nfs-ganesha or croit-nfs) that export CephFS.
  - A cluster is identified by O(name), which croit stores as the cluster's description.
  - Manages the member servers, the NFS implementation and, for croit-nfs, the floating virtual IPs.
  - Exports are managed with M(croit.ceph.nfs_export).
  - Only options that are set are managed; anything left out keeps its current value.
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
  name:
    description:
      - Name of the NFS cluster (its croit description). Must be unique.
    type: str
    required: true
  state:
    description:
      - Whether the NFS cluster should exist.
      - V(absent) removes the gateways from every server, which disconnects B(every NFS client) of the cluster,
        and needs O(confirm_delete=true). The exported CephFS data is not touched.
    type: str
    choices: [present, absent]
    default: present
  servers:
    description:
      - The complete list of servers running the cluster, by hostname or croit id.
      - Required to create a cluster. A server dropped from the list stops serving NFS.
    type: list
    elements: str
  implementation:
    description:
      - NFS implementation serving the cluster. croit uses V(ganesha) when a cluster is created without it.
      - Switching an existing cluster restarts the NFS service, briefly interrupting connected clients, and needs
        O(confirm_action=true). Exports are kept.
    type: str
    choices: [ganesha, croit_nfs]
  vip_reconciliation:
    description:
      - Only used when switching back to V(ganesha) while the croit-nfs virtual IP differs from the dormant HA group's.
      - V(adopt) moves the HA group to the croit-nfs VIP, V(keep) keeps the group's own VIP.
    type: str
    choices: [adopt, keep]
  vips:
    description:
      - Every floating virtual IP the cluster should serve, for example V(10.0.0.250/24). Order does not matter.
      - Only for V(croit_nfs) clusters with at least two servers; nfs-ganesha clusters use M(croit.ceph.ha_group).
      - An empty list removes all virtual IPs; connected clients of removed addresses are disconnected.
    type: list
    elements: str
  vip_interfaces:
    description:
      - The complete list of interfaces the members bind virtual IPs on, one per server.
      - Needed together with O(vips) when virtual IPs are first configured.
    type: list
    elements: dict
    suboptions:
      server:
        description: Server hostname or croit id.
        type: str
        required: true
      nic:
        description: Interface by croit name, Linux name, MAC address or croit id.
        type: str
        required: true
      vlan:
        description: VLAN tag on the interface; leave unset for the untagged interface.
        type: int
  confirm_action:
    description:
      - Must be V(true) to switch the O(implementation) of an existing cluster, which restarts its NFS service.
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing cluster and disconnect all its clients.
      - Also confirms croit's warning about removing a gateway from every node.
    type: bool
    default: false
notes:
  - Croit offers no rename; changing O(name) creates a new cluster.
"""

EXAMPLES = r"""
- name: croit-nfs cluster on three nodes with two floating IPs
  croit.ceph.nfs_cluster:
    name: nfs-prod
    implementation: croit_nfs
    servers: [node1, node2, node3]
    vips: [10.0.0.250/24, 10.0.0.251/24]
    vip_interfaces:
      - {server: node1, nic: eth1}
      - {server: node2, nic: eth1}
      - {server: node3, nic: eth1}

- name: Add a fourth node
  croit.ceph.nfs_cluster:
    name: nfs-prod
    servers: [node1, node2, node3, node4]

- name: Switch an existing cluster to croit-nfs (restarts the NFS service)
  croit.ceph.nfs_cluster:
    name: nfs-legacy
    implementation: croit_nfs
    confirm_action: true

- name: Delete a cluster (disconnects every client)
  croit.ceph.nfs_cluster:
    name: nfs-old
    state: absent
    confirm_delete: true
"""

RETURN = r"""
cluster:
  description:
    - The cluster as croit reports it after the change (C(NfsGatewayService) plus C(serviceId), C(description)
      and C(implementation)). Before the change in check mode; empty when the cluster does not exist.
  returned: always
  type: dict
  sample:
    serviceId: 41
    description: nfs-prod
    implementation: croit_nfs
    servers: [1, 2, 3]
ha:
  description: The croit-nfs HA view (C(CroitNfsHaView)) after the change, when O(vips) or O(vip_interfaces) is set.
  returned: when O(vips) or O(vip_interfaces) is set and the cluster exists
  type: dict
task:
  description: The last croit background task the change ran as.
  returned: when a task ran
  type: dict
"""

import ipaddress

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_one, require_server, resolve_interface
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def normalise_vip(value):
    """Canonical text for a VIP with or without prefix length; unparsable values compare verbatim."""
    text = str(value).strip()
    try:
        if "/" in text:
            return str(ipaddress.ip_interface(text))
        return str(ipaddress.ip_address(text))
    except ValueError:
        return text


class NfsClusterModule(CroitModule):
    def __init__(self):
        super(NfsClusterModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                servers=dict(type="list", elements="str"),
                implementation=dict(type="str", choices=["ganesha", "croit_nfs"]),
                vip_reconciliation=dict(type="str", choices=["adopt", "keep"]),
                vips=dict(type="list", elements="str"),
                vip_interfaces=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        server=dict(type="str", required=True),
                        nic=dict(type="str", required=True),
                        vlan=dict(type="int"),
                    ),
                ),
                confirm_action=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
        )
        self._servers = None
        self._nics = {}
        self.tasks = []

    # Lookups --------------------------------------------------------------

    def servers(self):
        if self._servers is None:
            self._servers = self.get_list("/servers")
        return self._servers

    def hostname(self, server_id):
        for server in self.servers():
            if server.get("id") == server_id:
                return server.get("hostname")
        return str(server_id)

    def nics(self, server_id):
        if server_id not in self._nics:
            self._nics[server_id] = self.get_list(path_join("servers", server_id, "nics"))
        return self._nics[server_id]

    def find_cluster(self, name):
        try:
            return find_one(self.get_list("/gateways/nfs"), "NFS cluster", "description", name)
        except ValueError as e:
            self.module.fail_json(msg=str(e))

    def server_ids(self, names):
        return sorted(set(require_server(self, s, self.servers())["id"] for s in names))

    def resolve_interface(self, item):
        server = require_server(self, item["server"], self.servers())
        server, nic, vlan_id = resolve_interface(
            self, server["id"], item["nic"], item.get("vlan"), servers=self.servers(), nics=self.nics(server["id"])
        )
        return (server["id"], nic["id"], vlan_id)

    def describe_interface(self, key):
        server_id, nic_id, vlan_id = key
        view = dict(server=self.hostname(server_id), nic=nic_id)
        for nic in self.nics(server_id):
            if nic.get("id") == nic_id:
                view["nic"] = nic.get("name")
                for vlan in nic.get("vlans") or []:
                    if vlan.get("id") == vlan_id:
                        view["vlan"] = vlan.get("vlan")
        if vlan_id is not None and "vlan" not in view:
            view["vlan"] = vlan_id
        return view

    def interface_view(self, keys):
        return sorted((self.describe_interface(k) for k in keys), key=lambda v: (v["server"], str(v["nic"]), v.get("vlan") or 0))

    # Desired --------------------------------------------------------------

    def desired_vips(self):
        if self.params["vips"] is None:
            return None
        return sorted(set(normalise_vip(v) for v in self.params["vips"]))

    def desired_interfaces(self):
        if self.params["vip_interfaces"] is None:
            return None
        keys = [self.resolve_interface(i) for i in self.params["vip_interfaces"]]
        per_server = {}
        for key in keys:
            per_server.setdefault(key[0], set()).add(key)
        doubled = [self.hostname(s) for s, ks in per_server.items() if len(ks) > 1]
        if doubled:
            self.module.fail_json(msg="vip_interfaces names more than one interface for %s" % ", ".join(sorted(doubled)))
        return sorted(set(keys), key=lambda k: (k[0], k[1], k[2] or 0))

    def manages_ha(self):
        return self.params["vips"] is not None or self.params["vip_interfaces"] is not None

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        current = self.find_cluster(p["name"])
        if p["state"] == "absent":
            return self.absent(current)
        if current is None:
            return self.create()
        return self.update(current)

    def details(self, summary):
        cluster = dict(self.get(path_join("services", "nfs-gateways", summary["serviceId"])) or {})
        cluster.update(serviceId=summary["serviceId"], description=summary.get("description"))
        cluster.setdefault("implementation", summary.get("implementation"))
        return cluster

    def view(self, cluster):
        if not cluster:
            return {}
        return dict(
            name=cluster.get("description"),
            servers=sorted(self.hostname(s) for s in cluster.get("servers") or []),
            implementation=cluster.get("implementation"),
        )

    def absent(self, current):
        p = self.params
        if current is None:
            self.exit(changed=False, cluster={})
        if not p["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to delete NFS cluster %r and disconnect all its clients without confirm_delete=true" % p["name"]
            )
        cluster = self.details(current)
        before = self.view(cluster)
        result = dict(cluster={})
        if not self.check_mode:
            task = self.handle_task(self.write("DELETE", path_join("services", current["serviceId"]), confirm_warnings=True))
            if task is not None:
                result["task"] = task
        self.exit(changed=True, before=before, after={}, **result)

    def create(self):
        p = self.params
        if not p["servers"]:
            self.module.fail_json(msg="servers is required to create NFS cluster %r" % p["name"])
        server_ids = self.server_ids(p["servers"])
        vips = self.desired_vips()
        interfaces = self.desired_interfaces()
        implementation = p["implementation"]
        if self.manages_ha() and implementation != "croit_nfs":
            self.module.fail_json(msg="vips and vip_interfaces need implementation=croit_nfs; nfs-ganesha uses croit.ceph.ha_group")
        if vips and not interfaces:
            self.module.fail_json(msg="vip_interfaces is required to configure vips on a new cluster")
        if vips and len(server_ids) < 2:
            self.module.fail_json(msg="Virtual IPs need at least two servers in the cluster")

        body = dict(description=p["name"], servers=server_ids, exports=[])
        if implementation:
            body["implementation"] = implementation
        after = dict(name=p["name"], servers=sorted(self.hostname(s) for s in server_ids), implementation=implementation or "ganesha")
        if self.manages_ha():
            after["vips"] = vips or []
            after["vip_interfaces"] = self.interface_view(interfaces or [])
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, cluster={})

        result = dict(changed=True, before={}, after=after)
        self.track(self.write("POST", "/services/nfs-gateways", body=body))
        created = self.find_cluster(p["name"])
        if created is None:
            if not p["wait"]:
                self.exit(cluster={}, **self.with_task(result))
            self.module.fail_json(msg="croit reported NFS cluster %r created, but it is not listed" % p["name"])
        if vips:
            if not p["wait"]:
                self.module.warn("wait=false: the virtual IPs are configured on the next run, once the cluster exists")
            else:
                self.put_ha(created["serviceId"], vips, interfaces)
        result["cluster"] = self.details(created)
        if self.manages_ha():
            result["ha"] = self.get(path_join("services", "nfs-gateways", created["serviceId"], "ha"))
        self.exit(**self.with_task(result))

    def update(self, summary):
        p = self.params
        service_id = summary["serviceId"]
        cluster = self.details(summary)
        before = self.view(cluster)
        after = dict(before)
        result = dict(cluster=cluster)

        servers_change = None
        if p["servers"] is not None:
            if not p["servers"]:
                self.module.fail_json(msg="servers must name at least one server")
            wanted = self.server_ids(p["servers"])
            if wanted != sorted(cluster.get("servers") or []):
                servers_change = wanted
                after["servers"] = sorted(self.hostname(s) for s in wanted)

        current_impl = cluster.get("implementation")
        impl_change = p["implementation"] if p["implementation"] and p["implementation"] != current_impl else None
        if impl_change:
            if not p["confirm_action"]:
                self.module.fail_json(
                    msg="Switching NFS cluster %r from %s to %s restarts its NFS service and briefly interrupts clients; "
                    "set confirm_action=true to do it" % (p["name"], current_impl, impl_change)
                )
            after["implementation"] = impl_change

        ha_put = None
        ha_delete = False
        if self.manages_ha():
            effective_impl = impl_change or current_impl
            if effective_impl != "croit_nfs":
                self.module.fail_json(msg="vips and vip_interfaces need implementation=croit_nfs; nfs-ganesha uses croit.ceph.ha_group")
            ha = self.get(path_join("services", "nfs-gateways", service_id, "ha")) or {}
            result["ha"] = ha
            current_vips = sorted(set(normalise_vip(v) for v in ha.get("vips") or []))
            current_ifaces = sorted(
                set(
                    (m.get("server"), m.get("nic"), m.get("vlan"))
                    for m in ha.get("members") or []
                    if m.get("nic") is not None
                ),
                key=lambda k: (k[0], k[1], k[2] or 0),
            )
            before["vips"] = current_vips
            before["vip_interfaces"] = self.interface_view(current_ifaces)
            vips = self.desired_vips()
            ifaces = self.desired_interfaces()
            want_vips = current_vips if vips is None else vips
            want_ifaces = current_ifaces if ifaces is None else ifaces
            after["vips"] = want_vips
            after["vip_interfaces"] = self.interface_view(want_ifaces)
            if (want_vips, want_ifaces) != (current_vips, current_ifaces):
                if not want_vips and vips is not None and ifaces is None:
                    ha_delete = bool(current_vips)
                    after["vip_interfaces"] = before["vip_interfaces"]
                else:
                    if want_vips and not want_ifaces:
                        self.module.fail_json(msg="vip_interfaces is required to configure vips")
                    if want_vips and servers_change is None and impl_change is None and ha.get("haPossible") is False:
                        self.module.fail_json(
                            msg="NFS cluster %r cannot serve virtual IPs: it needs at least %s servers"
                            % (p["name"], ha.get("minimumMembers") or 2)
                        )
                    ha_put = (want_vips, want_ifaces)

        changed = bool(servers_change is not None or impl_change or ha_put or ha_delete)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, **result)

        if servers_change is not None:
            self.write("PATCH", path_join("services", "nfs-gateways", service_id), body=dict(servers=servers_change))
        if impl_change:
            body = dict(implementation=impl_change)
            if p["vip_reconciliation"]:
                body["vipReconciliation"] = p["vip_reconciliation"]
            self.track(self.write("PATCH", path_join("services", "nfs-gateways", service_id, "implementation"), body=body))
        if ha_put:
            self.put_ha(service_id, ha_put[0], ha_put[1])
        if ha_delete:
            self.write("DELETE", path_join("services", "nfs-gateways", service_id, "ha"))

        refreshed = self.find_cluster(p["name"])
        result["cluster"] = self.details(refreshed) if refreshed else cluster
        if self.manages_ha():
            result["ha"] = self.get(path_join("services", "nfs-gateways", service_id, "ha"))
        self.exit(changed=True, before=before, after=after, **self.with_task(result))

    def put_ha(self, service_id, vips, interfaces):
        body = dict(
            vips=list(vips),
            interfaces=[dict(server=s, nic=n, vlan=v) for s, n, v in interfaces],
        )
        self.write("PUT", path_join("services", "nfs-gateways", service_id, "ha"), body=body)

    # Tasks ----------------------------------------------------------------

    def track(self, data):
        task = self.handle_task(data)
        if task is not None:
            self.tasks.append(task)
        return task

    def with_task(self, result):
        if self.tasks:
            result["task"] = self.tasks[-1]
        return result


def main():
    NfsClusterModule().run()


if __name__ == "__main__":
    main()
