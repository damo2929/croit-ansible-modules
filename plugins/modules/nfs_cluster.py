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
  - Create, update and delete croit NFS gateway clusters, which export CephFS over NFS with either nfs-ganesha or croit-nfs.
  - A cluster is identified by O(name), which croit stores as the cluster's description. croit offers no rename, so a
    different O(name) creates a new cluster.
  - The module manages the member servers, the NFS implementation and, for croit-nfs clusters, the floating virtual IPs
    and the interfaces they are bound on. Exports are managed with M(croit.ceph.nfs_export).
  - Options that are not set keep their current value.
  - Deleting a cluster disconnects every NFS client of it and needs O(confirm_delete=true); switching the implementation
    of an existing cluster restarts its NFS service and needs O(confirm_action=true).
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
      - Name of the NFS cluster, stored as its croit description. It must be unique among the NFS clusters.
    type: str
    required: true
  state:
    description:
      - Whether the NFS cluster should exist.
      - V(absent) removes the gateways from every server, which disconnects B(every NFS client) of the cluster, and needs
        O(confirm_delete=true). The exported CephFS data is not touched.
    type: str
    choices: [present, absent]
    default: present
  servers:
    description:
      - The complete list of servers running the cluster, by hostname or croit server id. Order does not matter.
      - Required to create a cluster. A server dropped from the list stops serving NFS; an empty list is refused.
    type: list
    elements: str
  implementation:
    description:
      - NFS implementation serving the cluster. croit uses V(ganesha) when a cluster is created without it.
      - Switching an existing cluster restarts the NFS service, briefly interrupting connected clients, and needs
        O(confirm_action=true). Exports are kept.
      - O(vips) and O(vip_interfaces) need V(croit_nfs); nfs-ganesha clusters get floating IPs from M(croit.ceph.ha_group).
    type: str
    choices: [ganesha, croit_nfs]
  vip_reconciliation:
    description:
      - Which virtual IP to keep when switching an existing cluster back to V(ganesha) while the croit-nfs virtual IP
        differs from the one of the dormant HA group left by an earlier switch.
      - V(adopt) moves the HA group to the croit-nfs virtual IP, V(keep) keeps the HA group's own virtual IP.
      - Only sent together with an O(implementation) switch; ignored otherwise.
    type: str
    choices: [adopt, keep]
  vips:
    description:
      - Every floating virtual IP the cluster should serve, with or without prefix length, for example V(10.0.0.250/24).
        Order and address notation do not matter.
      - Only for V(croit_nfs) clusters with at least two servers.
      - An empty list removes all virtual IPs; clients connected through a removed address are disconnected.
      - When not set, the configured virtual IPs are left alone.
    type: list
    elements: str
  vip_interfaces:
    description:
      - The complete list of interfaces the cluster members bind virtual IPs on, with at most one interface per server.
      - Required together with O(vips) when virtual IPs are first configured, including on a new cluster. When not set,
        the configured interfaces are kept.
    type: list
    elements: dict
    suboptions:
      server:
        description:
          - Server hostname or croit server id.
        type: str
        required: true
      nic:
        description:
          - Interface by croit name, Linux name, MAC address or croit interface id.
        type: str
        required: true
      vlan:
        description:
          - VLAN tag of a VLAN on the interface to bind the virtual IPs on. Leave unset for the untagged interface.
        type: int
  confirm_action:
    description:
      - Must be V(true) to switch the O(implementation) of an existing cluster, which restarts its NFS service.
      - Not needed when a cluster is created or when the implementation does not change.
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing cluster and disconnect all its clients.
      - Also confirms croit's warning about removing a gateway from every node.
    type: bool
    default: false
notes:
  - Deleting a cluster or removing virtual IPs disconnects NFS clients; the CephFS data behind the exports is never touched.
  - With O(wait=false), virtual IPs of a new cluster are configured on a later run, once croit lists the cluster.
  - The cluster's name is croit's description and VLANs are sent as croit's VLAN record ids; both follow the croit API
    reference and have not yet been verified against a live croit cluster.
seealso:
  - module: croit.ceph.nfs_export
    description: Manage the exports of an NFS cluster.
  - module: croit.ceph.nfs_info
    description: Read NFS clusters, their exports, servers and HA state.
  - module: croit.ceph.ha_group
    description: Floating IPs for nfs-ganesha clusters.
  - name: croit API reference
    description: The croit REST API this module uses (NFS gateways).
    link: https://www.croit.io/api-docs
  - name: CephFS and NFS
    description: Upstream Ceph documentation on exporting CephFS over NFS.
    link: https://docs.ceph.com/en/latest/cephfs/nfs/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Create a croit-nfs cluster on three nodes with two floating IPs
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

- name: Preview a change in check mode and show the diff
  croit.ceph.nfs_cluster:
    name: nfs-prod
    vips: [10.0.0.250/24]
  check_mode: true
  diff: true
  register: preview

- name: Show the cluster's service id
  ansible.builtin.debug:
    msg: "nfs-prod is croit service {{ preview.cluster.serviceId }}"

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
    - The cluster as croit reports it after the change (C(NfsGatewayService) plus C(serviceId), C(description) and
      C(implementation)).
    - In check mode the cluster before the change. Empty when the cluster does not exist or was deleted.
  returned: always
  type: dict
  contains:
    serviceId:
      description: croit's id of the NFS service.
      returned: when the cluster exists
      type: int
      sample: 41
    description:
      description: The cluster's name (O(name)).
      returned: when the cluster exists
      type: str
      sample: nfs-prod
    implementation:
      description: NFS implementation serving the cluster.
      returned: when the cluster exists
      type: str
      sample: croit_nfs
    servers:
      description: croit server ids of the members.
      returned: when the cluster exists
      type: list
      elements: int
      sample: [1, 2, 3]
    exports:
      description: The cluster's exports (C(NfsGatewayExport)); see M(croit.ceph.nfs_export).
      returned: when the cluster exists
      type: list
      elements: dict
      sample: [{id: 7, nfsPath: /projects, path: /volumes/_nogroup/projects, volume: null}]
ha:
  description:
    - The croit-nfs HA view (C(CroitNfsHaView)) after the change.
  returned: when O(vips) or O(vip_interfaces) is set and the cluster exists
  type: dict
  contains:
    vips:
      description: Every virtual IP configured on the cluster.
      returned: always
      type: list
      elements: str
      sample: [10.0.0.250/24, 10.0.0.251/24]
    members:
      description:
        - One entry per member with C(server), C(nic), C(vlan) (croit's VLAN record id), C(serviceRunning),
          C(raftRole) and C(vipsHeld).
      returned: always
      type: list
      elements: dict
      sample: [{server: 1, nic: 4, vlan: null, serviceRunning: true, raftRole: leader, vipsHeld: [10.0.0.250/24]}]
    haPossible:
      description: Whether the cluster has enough members to serve virtual IPs.
      returned: always
      type: bool
      sample: true
    minimumMembers:
      description: Members needed before virtual IPs can be configured.
      returned: always
      type: int
      sample: 2
    quorumHealthy:
      description: Whether croit-nfs reports its quorum as healthy; null when no member could be read.
      returned: always
      type: bool
      sample: true
task:
  description:
    - The last croit background task the change ran as, for example the cluster creation or the implementation switch.
  returned: when a task ran
  type: dict
  contains:
    id:
      description: croit's task id.
      returned: always
      type: int
      sample: 512
    name:
      description: What the task did.
      returned: always
      type: str
      sample: Create NFS cluster
    state:
      description: Final state of the task, one of C(FINISHED), C(FAILED), C(CANCELED), or C(RUNNING) with O(wait=false).
      returned: always
      type: str
      sample: FINISHED
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: "Deploying NFS gateway on node1 ... done"
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.ip import normalise_ip
from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_one, require_server, resolve_interface
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


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
        return sorted(set(normalise_ip(v) for v in self.params["vips"]))

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
            current_vips = sorted(set(normalise_ip(v) for v in ha.get("vips") or []))
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
