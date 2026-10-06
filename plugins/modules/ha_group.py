#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /servers/ha-groups
# croit-api: POST /servers/ha-groups
# croit-api: PUT /servers/ha-groups/{haGroupId}
# croit-api: DELETE /servers/ha-groups/{haGroupId}
# croit-api: GET /servers
# croit-api: GET /servers/{serverId}/nics

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: ha_group
short_description: Manage high availability groups and floating IPs on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete croit high availability (HA) groups. A group moves one or more virtual
    IPs (VIPs) between member servers, optionally behind HA Proxy fronting the object gateways.
  - Groups are identified by O(name), which croit stores as the group's description.
  - croit replaces a group's whole configuration on every update. This module reads the current
    configuration, merges the options that are set, and sends the result, so options that are not set
    keep their current value.
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
seealso:
  - module: croit.ceph.rgw_service
    description: Add the S3 gateways a group fronts with HA Proxy.
  - module: croit.ceph.nfs_cluster
    description: croit-nfs clusters manage their own virtual IPs.
  - module: croit.ceph.server_nic
    description: Manage the interfaces the virtual IPs move between.
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
options:
  name:
    description:
      - Name of the group (croit's group description). Must be unique.
    type: str
    required: true
  state:
    description:
      - Whether the group should exist.
      - V(absent) removes the group and releases its VIPs. No data is lost, but clients using the VIPs lose
        access until another group holds them.
    type: str
    choices: [present, absent]
    default: present
  service:
    description:
      - The service the group fronts. Required when the group is created.
    type: str
    choices: [nfs, rgw, smb, iscsi, none]
  backend:
    description:
      - VIP manager of the group. croit uses V(keepalived) when not set.
      - V(keepalived) supports exactly one VIP; V(keepafloatd) supports several.
      - Cannot be changed after the group exists.
    type: str
    choices: [keepalived, keepafloatd]
  vips:
    description:
      - Virtual IPs of the group. Compared as a set, after normalising the address notation.
    type: list
    elements: str
  servers:
    description:
      - The servers that can hold the VIPs, with the interface each binds them on.
      - With HA Proxy enabled these are the HA Proxy nodes, otherwise the service nodes.
      - The members of a V(keepafloatd) group cannot be changed after creation; recreate the group instead.
    type: list
    elements: dict
    suboptions:
      server:
        description: Hostname or numeric id of the server.
        type: str
        required: true
      nic:
        description: Interface the VIPs are bound on, by croit NIC name, Linux interface name or numeric id.
        type: str
        required: true
      vlan:
        description: VLAN tag on that interface, when the VIPs are bound on a VLAN.
        type: int
  backend_servers:
    description:
      - Servers running the object gateway that HA Proxy forwards to, by hostname or id.
      - Required by croit when O(haproxy=true); ignored otherwise.
    type: list
    elements: str
  haproxy:
    description:
      - Whether HA Proxy fronts the group's VIPs.
    type: bool
  haproxy_port:
    description:
      - Port HA Proxy binds on each VIP. croit uses 443 when not set.
    type: int
  proxy_mode:
    description:
      - V(tcp) passes the stream through; V(http) terminates TLS with the cluster's RGW certificate.
    type: str
    choices: [tcp, http]
  failback:
    description:
      - Switch back to the original server after it recovers.
    type: bool
  failover_time:
    description:
      - Seconds until a failover is triggered after a fault is detected.
    type: int
  failback_time:
    description:
      - Seconds until the service fails back to the original server after it recovers.
    type: int
  evict_nfs_clients_on_failback:
    description:
      - Force disconnect NFS clients from a secondary when failing back.
    type: bool
  tuning:
    description:
      - Advanced HA Proxy tuning. Only the sub-options that are set are managed; unset values use the
        cluster default.
    type: dict
    suboptions:
      balance:
        description: How sessions are spread over the backend gateways.
        type: str
        choices: [static_rr, leastconn, source]
      check_interval_ms:
        description: Backend health check interval in milliseconds.
        type: int
      client_timeout_ms:
        description: Client inactivity timeout in milliseconds.
        type: int
      connect_timeout_ms:
        description: Backend connect timeout in milliseconds.
        type: int
      server_timeout_ms:
        description: Backend inactivity timeout in milliseconds.
        type: int
      frontend_max_conn:
        description: Client connections the frontend accepts.
        type: int
      server_max_conn:
        description: Connections opened to each backend gateway before queueing.
        type: int
      full_request_log:
        description: Log every request, not only failed ones.
        type: bool
notes:
  - Deleting a group releases its virtual IPs, so clients using them lose access until they are configured
    elsewhere. No data is lost, so no confirmation is needed.
  - O(backend) cannot be changed after creation, and the members of a C(keepafloatd) group cannot be
    changed; croit refuses both, so the module fails instead of recreating the group.
  - Creating or updating a group can make croit ask whether an object gateway may be moved off the port
    HA Proxy needs. The task then waits for an answer; answer it with M(croit.ceph.task) or in the croit UI.
  - The O(servers[].vlan) tag is resolved to croit's VLAN record on the given interface.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: S3 behind HA Proxy on two VIPs
  croit.ceph.ha_group:
    name: s3-frontend
    service: rgw
    backend: keepafloatd
    vips: [10.0.0.100, 10.0.0.101]
    servers:
      - {server: gw1, nic: bond0}
      - {server: gw2, nic: bond0}
    haproxy: true
    haproxy_port: 443
    backend_servers: [rgw1, rgw2, rgw3]
  register: s3_ha

- name: Show where the VIPs are held
  ansible.builtin.debug:
    msg: "{{ s3_ha.ha_group.vipHolders }}"

- name: NFS floating IP on a VLAN
  croit.ceph.ha_group:
    name: nfs-vip
    service: nfs
    vips: [192.168.50.10]
    servers:
      - {server: nfs1, nic: eth1, vlan: 50}
      - {server: nfs2, nic: eth1, vlan: 50}
    failback: true
    failback_time: 60

- name: Remove a group (releases its VIPs)
  croit.ceph.ha_group:
    name: nfs-vip
    state: absent
"""

RETURN = r"""
ha_group:
  description:
    - The group as croit reports it after the change (C(HaGroupResponse) in the croit API).
    - Before the change in check mode; empty when the group does not exist.
  returned: always
  type: dict
  contains:
    id:
      description: croit's numeric group id.
      returned: when the group exists
      type: int
      sample: 3
    description:
      description: The group's name (O(name)).
      returned: when the group exists
      type: str
      sample: s3-frontend
    service:
      description: The service the group fronts.
      returned: when the group exists
      type: str
      sample: rgw
    backend:
      description: The HA backend.
      returned: when the group exists
      type: str
      sample: keepafloatd
    vips:
      description: The group's virtual IPs.
      returned: when the group exists
      type: list
      elements: str
      sample: ["10.0.0.100", "10.0.0.101"]
    servers:
      description: Member servers, each with croit's C(server), C(nic) and C(vlan) record ids.
      returned: when the group exists
      type: list
      elements: dict
      sample: [{server: 11, nic: 52, vlan: null}]
    haproxy:
      description: Whether HA Proxy fronts the backend servers.
      returned: when the group exists
      type: bool
      sample: true
    vipHolders:
      description: Which server currently holds each virtual IP, as croit reports it.
      returned: when the group exists
      type: dict
      sample: {}
task:
  description: The croit background task the change ran as, when there was one (C(TaskResponse) in the croit API).
  returned: when a task ran
  type: dict
  contains:
    id:
      description: Task id, usable with M(croit.ceph.task) and M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as croit's task list shows it.
      returned: always
      type: str
      sample: Update server
    state:
      description: V(WAITING), V(RUNNING), V(FINISHED), V(FAILED) or V(CANCELED).
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
      sample: "done"
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.ip import normalise_ip
from ansible_collections.croit.ceph.plugins.module_utils.lookup import list_servers, require_server, resolve_interface
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

# Ansible option -> croit field, compared 1:1.
FIELDS = dict(
    service="service",
    haproxy="haproxy",
    haproxy_port="haproxyPort",
    proxy_mode="proxyMode",
    failback="failback",
    failover_time="failoverTime",
    failback_time="failbackTime",
    evict_nfs_clients_on_failback="evictNfsClientsOnFailback",
)
TUNING = dict(
    balance="balance",
    check_interval_ms="checkIntervalMs",
    client_timeout_ms="clientTimeoutMs",
    connect_timeout_ms="connectTimeoutMs",
    server_timeout_ms="serverTimeoutMs",
    frontend_max_conn="frontendMaxConn",
    server_max_conn="serverMaxConn",
    full_request_log="fullRequestLog",
)
# Fields of a HaGroupWriteRequest that are copied from the current group on update.
WRITE_FIELDS = (
    "description",
    "service",
    "backend",
    "vips",
    "servers",
    "backendServers",
    "haproxy",
    "haproxyPort",
    "proxyMode",
    "failback",
    "failoverTime",
    "failbackTime",
    "evictNfsClientsOnFailback",
    "tuning",
)


def member_key(member):
    return (member.get("server"), member.get("nic"), member.get("vlan"))


class HaGroupModule(CroitModule):
    def __init__(self):
        super(HaGroupModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                service=dict(type="str", choices=["nfs", "rgw", "smb", "iscsi", "none"]),
                backend=dict(type="str", choices=["keepalived", "keepafloatd"]),
                vips=dict(type="list", elements="str"),
                servers=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        server=dict(type="str", required=True),
                        nic=dict(type="str", required=True),
                        vlan=dict(type="int"),
                    ),
                ),
                backend_servers=dict(type="list", elements="str"),
                haproxy=dict(type="bool"),
                haproxy_port=dict(type="int"),
                proxy_mode=dict(type="str", choices=["tcp", "http"]),
                failback=dict(type="bool"),
                failover_time=dict(type="int"),
                failback_time=dict(type="int"),
                evict_nfs_clients_on_failback=dict(type="bool"),
                tuning=dict(
                    type="dict",
                    options=dict(
                        balance=dict(type="str", choices=["static_rr", "leastconn", "source"]),
                        check_interval_ms=dict(type="int"),
                        client_timeout_ms=dict(type="int"),
                        connect_timeout_ms=dict(type="int"),
                        server_timeout_ms=dict(type="int"),
                        frontend_max_conn=dict(type="int"),
                        server_max_conn=dict(type="int"),
                        full_request_log=dict(type="bool"),
                    ),
                ),
            ),
        )
        self._servers = None
        self._nics = {}

    # Lookups --------------------------------------------------------------

    def servers(self):
        if self._servers is None:
            self._servers = list_servers(self)
        return self._servers

    def hostname(self, server_id):
        for s in self.servers():
            if s.get("id") == server_id:
                return s.get("hostname")
        return server_id

    def nics(self, server_id):
        if server_id not in self._nics:
            self._nics[server_id] = self.get_list(path_join("servers", server_id, "nics"))
        return self._nics[server_id]

    def find_group(self, name):
        matches = [g for g in self.get_list("/servers/ha-groups") if g.get("description") == name]
        if len(matches) > 1:
            self.module.fail_json(msg="%d HA groups are named %r; names must be unique" % (len(matches), name))
        return matches[0] if matches else None

    def resolve_member(self, member):
        server = require_server(self, member["server"], self.servers())
        server, nic, vlan_id = resolve_interface(
            self, server["id"], member["nic"], member.get("vlan"), servers=self.servers(), nics=self.nics(server["id"])
        )
        return dict(server=server["id"], nic=nic["id"], vlan=vlan_id)

    def describe_member(self, member):
        """Readable form of a croit member for diffs."""
        server_id = member.get("server")
        nic_name = member.get("nic")
        vlan_tag = member.get("vlan")
        for nic in self.nics(server_id):
            if nic.get("id") == member.get("nic"):
                nic_name = nic.get("name")
                for vlan in nic.get("vlans") or []:
                    if vlan.get("id") == member.get("vlan"):
                        vlan_tag = vlan.get("vlan")
        view = dict(server=self.hostname(server_id), nic=nic_name)
        if vlan_tag is not None:
            view["vlan"] = vlan_tag
        return view

    # Views ----------------------------------------------------------------

    def view(self, group):
        if not group:
            return {}
        view = dict((opt, group.get(api)) for opt, api in FIELDS.items())
        view["backend"] = group.get("backend")
        view["vips"] = sorted(normalise_ip(v) for v in group.get("vips") or [])
        view["servers"] = sorted(
            (self.describe_member(m) for m in group.get("servers") or []), key=lambda m: (str(m["server"]), str(m["nic"]))
        )
        view["backend_servers"] = sorted(str(self.hostname(i)) for i in group.get("backendServers") or [])
        tuning = group.get("tuning") or {}
        view["tuning"] = dict((opt, tuning.get(api)) for opt, api in TUNING.items())
        return view

    # Desired state --------------------------------------------------------

    def desired(self):
        """croit-shaped values for the options that are set."""
        p = self.params
        desired = dict((api, p[opt]) for opt, api in FIELDS.items() if p[opt] is not None)
        if p["vips"] is not None:
            desired["vips"] = [normalise_ip(v) for v in p["vips"]]
        if p["servers"] is not None:
            desired["servers"] = [self.resolve_member(m) for m in p["servers"]]
        if p["backend_servers"] is not None:
            desired["backendServers"] = [require_server(self, s, self.servers())["id"] for s in p["backend_servers"]]
        if p["tuning"] is not None:
            desired["tuning"] = dict((api, p["tuning"][opt]) for opt, api in TUNING.items() if p["tuning"][opt] is not None)
        return desired

    def differs(self, current, desired):
        """Fields of ``desired`` that differ from ``current`` (croit-shaped)."""
        changed = []
        for key, value in desired.items():
            have = current.get(key)
            if key == "vips":
                same = set(value) == set(normalise_ip(v) for v in have or [])
            elif key == "servers":
                same = set(member_key(m) for m in value) == set(member_key(m) for m in have or [])
            elif key == "backendServers":
                same = set(value) == set(have or [])
            elif key == "tuning":
                have = have or {}
                same = all(have.get(k) == v for k, v in value.items())
            else:
                same = have == value
            if not same:
                changed.append(key)
        return changed

    def write_request(self, current, desired):
        body = dict((k, current.get(k)) for k in WRITE_FIELDS if current.get(k) is not None)
        body["servers"] = [
            dict((k, v) for k, v in (("server", m.get("server")), ("nic", m.get("nic")), ("vlan", m.get("vlan"))) if v is not None)
            for m in current.get("servers") or []
        ]
        for key, value in desired.items():
            if key == "tuning":
                merged = dict(current.get("tuning") or {})
                merged.update(value)
                body["tuning"] = merged
            elif key == "servers":
                body["servers"] = [dict((k, v) for k, v in m.items() if v is not None) for m in value]
            else:
                body[key] = value
        body["description"] = self.params["name"]
        return body

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        current = self.find_group(p["name"])
        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, ha_group={})
            before = self.view(current)
            if not self.check_mode:
                self.write("DELETE", path_join("servers", "ha-groups", current["id"]))
            self.exit(changed=True, before=before, after={}, ha_group={})
        if current is None:
            self.create()
        self.update(current)

    def create(self):
        p = self.params
        if p["service"] is None or not p["servers"]:
            self.module.fail_json(msg="service and servers are required to create HA group %r" % p["name"])
        desired = self.desired()
        body = dict(desired)
        body["description"] = p["name"]
        if p["backend"] is not None:
            body["backend"] = p["backend"]
        body["servers"] = [dict((k, v) for k, v in m.items() if v is not None) for m in body["servers"]]
        after = self.view(dict(body, servers=desired["servers"]))
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, ha_group={})
        task = self.handle_task(self.write("POST", "/servers/ha-groups", body=body))
        result = dict(changed=True, before={}, after=after, ha_group=self.find_group(p["name"]) or {})
        if task is not None:
            result["task"] = task
        self.exit(**result)

    def update(self, current):
        p = self.params
        if p["backend"] is not None and p["backend"] != current.get("backend"):
            self.module.fail_json(
                msg="backend of HA group %r is %r and cannot be changed to %r; recreate the group"
                % (p["name"], current.get("backend"), p["backend"])
            )
        desired = self.desired()
        changed = self.differs(current, desired)
        if "servers" in changed and current.get("backend") == "keepafloatd":
            self.module.fail_json(
                msg="The members of keepafloatd HA group %r cannot be changed; recreate the group" % p["name"]
            )
        before = self.view(current)
        if not changed:
            self.exit(changed=False, before=before, after=before, ha_group=current)
        body = self.write_request(current, dict((k, desired[k]) for k in changed))
        after = self.view(dict(current, **body))
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, ha_group=current)
        task = self.handle_task(self.write("PUT", path_join("servers", "ha-groups", current["id"]), body=body))
        result = dict(changed=True, before=before, after=after, ha_group=self.find_group(p["name"]) or {})
        if task is not None:
            result["task"] = task
        self.exit(**result)


def main():
    HaGroupModule().run()


if __name__ == "__main__":
    main()
