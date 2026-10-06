#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/nvmeof
# croit-api: GET /gateways/nvmeof/services
# croit-api: POST /gateways/nvmeof/{gatewayId}/services/{serviceId}/listeners
# croit-api: PATCH /gateways/nvmeof/{gatewayId}/services/{serviceId}/listeners/{listenerId}
# croit-api: DELETE /gateways/nvmeof/{gatewayId}/services/{serviceId}/listeners/{listenerId}
# croit-api: GET /servers/{serverId}/nics

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nvmeof_listener
short_description: Manage the addresses NVMe-oF target services listen on in a croit cluster
version_added: 0.1.0
description:
  - Adds, changes and removes one listener of a croit NVMe-oF target service.
  - A listener is identified by its NVMe-oF cluster, target service, interface (and VLAN), fabric and port.
    Only O(secure) can change in place; to move a listener to another port, add the new one and remove the
    old one.
  - Per-fabric transport settings are managed with M(croit.ceph.nvmeof_gateway)
    (O(croit.ceph.nvmeof_gateway#module:transport_defaults) and
    O(croit.ceph.nvmeof_gateway#module:services[].transports)).
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
  gateway:
    description:
      - NVMe-oF cluster of the target service, by name or numeric id.
    type: str
    required: true
  service:
    description:
      - Target service, by the hostname of its server, its service name or its numeric id.
    type: str
    required: true
  nic:
    description:
      - Interface on the service's server, by croit name, Linux name, MAC address or numeric id.
    type: str
    required: true
  vlan:
    description:
      - VLAN tag on O(nic) to listen on instead of the interface itself. The VLAN must exist
        (see M(croit.ceph.server_vlan)).
    type: int
  type:
    description:
      - Fabric the listener speaks, NVMe/TCP or NVMe/RDMA.
    type: str
    choices: [tcp, rdma]
    default: tcp
  port:
    description:
      - Port to listen on, for example V(4420).
    type: int
    required: true
  secure:
    description:
      - Use TLS on this listener. The NVMe-oF cluster's O(croit.ceph.nvmeof_gateway#module:force_secure) wins
        when it is set.
    type: bool
  state:
    description:
      - Whether the listener should exist.
      - V(absent) stops accepting connections on the address; hosts connected through it lose that path.
    type: str
    choices: [present, absent]
    default: present
seealso:
  - module: croit.ceph.nvmeof_gateway
    description: Manage the NVMe-oF cluster, its target services and transport settings.
  - module: croit.ceph.server_vlan
    description: Create the VLAN interface a listener uses.
  - module: croit.ceph.nvmeof_info
    description: Read the listeners of every target service.
  - name: Ceph NVMe-oF target configuration
    description: Upstream guide to configuring NVMe-oF targets and listeners.
    link: https://docs.ceph.com/en/latest/rbd/nvmeof-target-configure/
  - name: croit API reference
    description: The croit REST API this module talks to.
    link: https://www.croit.io/api-docs
notes:
  - Removing a listener only affects connections through that address; hosts with other paths keep them, so
    O(state=absent) needs no confirmation.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Listen on the storage VLAN of both targets
  croit.ceph.nvmeof_listener:
    gateway: nvme-prod
    service: "{{ item }}"
    nic: eth1
    vlan: 50
    port: 4420
  loop: [nvme1, nvme2]
  register: listeners

- name: Show the listener ids
  ansible.builtin.debug:
    msg: "{{ listeners.results | map(attribute='listener.listenerId') | list }}"

- name: Require TLS on a listener
  croit.ceph.nvmeof_listener:
    gateway: nvme-prod
    service: nvme1
    nic: eth1
    vlan: 50
    port: 4420
    secure: true

- name: Remove the old listener
  croit.ceph.nvmeof_listener:
    gateway: nvme-prod
    service: nvme1
    nic: eth0
    port: 4420
    state: absent
"""

RETURN = r"""
listener:
  description:
    - The listener as croit reports it after the change (C(NvmeOFListenerConfigResponse) in the croit API).
    - Before the change in check mode; empty when it does not exist.
  returned: always
  type: dict
  contains:
    listenerId:
      description: croit id of the listener.
      returned: when the listener exists
      type: int
      sample: 9
    gatewayId:
      description: croit id of the NVMe-oF cluster.
      returned: when the listener exists
      type: int
      sample: 1
    serviceId:
      description: croit id of the target service.
      returned: when the listener exists
      type: int
      sample: 21
    type:
      description: Fabric of the listener, C(TCP) or C(RDMA).
      returned: when the listener exists
      type: str
      sample: TCP
    nicId:
      description: croit id of the interface.
      returned: when the listener exists
      type: int
      sample: 11
    nicName:
      description: Name of the interface.
      returned: when the listener exists
      type: str
      sample: eth1
    vlan:
      description: VLAN tag the listener uses, null when it listens on the interface itself.
      returned: when the listener exists
      type: int
      sample: 50
    vlanId:
      description: croit id of the VLAN record, null when no VLAN is used.
      returned: when the listener exists
      type: int
      sample: 5
    port:
      description: Port of the listener, null when the cluster's default port is used.
      returned: when the listener exists
      type: int
      sample: 4420
    secure:
      description: Whether the listener uses TLS.
      returned: when the listener exists
      type: bool
      sample: false
task:
  description:
    - The last croit background task the change ran as (C(ManagedTask) in the croit API).
    - With O(wait=true) this is the task's final state. With O(wait=false) it may still be running; follow it
      with M(croit.ceph.task).
  returned: when the change ran as a croit background task
  type: dict
  contains:
    id:
      description: croit task id, for use with M(croit.ceph.task) and M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as the croit task list shows it.
      returned: always
      type: str
      sample: Add NVMe-oF listener
    state:
      description: State of the task, one of C(WAITING), C(RUNNING), C(FINISHED), C(FAILED) or C(CANCELED).
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
      sample: ""
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_nic
from ansible_collections.croit.ceph.plugins.module_utils.nvmeof import find_service, require_gateway
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def view(listener):
    if not listener:
        return {}
    return dict(
        nic=listener.get("nicName"),
        vlan=listener.get("vlan"),
        type=(listener.get("type") or "").lower(),
        port=listener.get("port"),
        secure=bool(listener.get("secure")),
    )


class NvmeofListenerModule(CroitModule):
    def __init__(self):
        super(NvmeofListenerModule, self).__init__(
            dict(
                gateway=dict(type="str", required=True),
                service=dict(type="str", required=True),
                nic=dict(type="str", required=True),
                vlan=dict(type="int"),
                type=dict(type="str", default="tcp", choices=["tcp", "rdma"]),
                port=dict(type="int", required=True),
                secure=dict(type="bool"),
                state=dict(type="str", default="present", choices=["present", "absent"]),
            ),
        )

    def require_service(self):
        services = [s for s in self.get_list("/gateways/nvmeof/services") if s.get("gatewayId") == self.gateway["gatewayId"]]
        try:
            service = find_service(services, self.params["service"])
        except ValueError as e:
            self.module.fail_json(msg=str(e))
        if service is None:
            self.module.fail_json(
                msg="NVMe-oF cluster %r has no target service %r. Services: %s"
                % (self.gateway["name"], self.params["service"], ", ".join(s.get("serverHostname") for s in services) or "none")
            )
        return service

    def require_nic(self, service):
        p = self.params
        nics = self.get_list(path_join("servers", service["serverId"], "nics"))
        nic = find_nic(self, nics, p["nic"])
        if nic is None and str(p["nic"]).isdigit():
            nic = next((n for n in nics if n.get("id") == int(p["nic"])), None)
        if nic is None:
            self.module.fail_json(
                msg="Server %s has no interface %r. Known interfaces: %s"
                % (service.get("serverHostname"), p["nic"], ", ".join("%s (%s)" % (n.get("name"), n.get("mac")) for n in nics))
            )
        vlan_id = None
        if p["vlan"] is not None:
            vlan = next((v for v in nic.get("vlans") or [] if v.get("vlan") == p["vlan"]), None)
            if vlan is None:
                self.module.fail_json(msg="Interface %s on %s has no VLAN %s" % (nic.get("name"), service.get("serverHostname"), p["vlan"]))
            vlan_id = vlan["id"]
        return nic, vlan_id

    def run(self):
        p = self.params
        self.gateway = require_gateway(self, p["gateway"])
        service = self.require_service()
        nic, vlan_id = self.require_nic(service)
        fabric = p["type"].upper()
        current = next(
            (
                lst
                for lst in service.get("listeners") or []
                if lst.get("nicId") == nic["id"]
                and lst.get("vlanId") == vlan_id
                and (lst.get("type") or "").upper() == fabric
                and lst.get("port") == p["port"]
            ),
            None,
        )
        service_path = path_join("gateways", "nvmeof", self.gateway["gatewayId"], "services", service["serviceId"], "listeners")
        before = view(current)

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, listener={})
            task = None
            if not self.check_mode:
                task = self.handle_task(self.write("DELETE", "%s/%s" % (service_path, current["listenerId"])))
            self.finish(True, before, {}, {}, task)

        if current is None:
            after = dict(nic=nic.get("name"), vlan=p["vlan"], type=p["type"], port=p["port"], secure=bool(p["secure"]))
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, listener={})
            body = dict(type=fabric, nicId=nic["id"], port=p["port"])
            if vlan_id is not None:
                body["vlanId"] = vlan_id
            if p["secure"] is not None:
                body["secure"] = p["secure"]
            task = self.handle_task(self.write("POST", service_path, body=body))
            self.finish(True, before, after, self.reread(service, nic, vlan_id), task)

        after = dict(before)
        if p["secure"] is None or bool(current.get("secure")) == p["secure"]:
            self.exit(changed=False, before=before, after=after, listener=current)
        after["secure"] = p["secure"]
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, listener=current)
        task = self.handle_task(self.write("PATCH", "%s/%s" % (service_path, current["listenerId"]), body=dict(secure=p["secure"])))
        self.finish(True, before, after, self.reread(service, nic, vlan_id), task)

    def reread(self, service, nic, vlan_id):
        p = self.params
        for svc in self.get_list("/gateways/nvmeof/services"):
            if svc.get("serviceId") != service["serviceId"]:
                continue
            for lst in svc.get("listeners") or []:
                if (
                    lst.get("nicId") == nic["id"]
                    and lst.get("vlanId") == vlan_id
                    and (lst.get("type") or "").upper() == p["type"].upper()
                    and lst.get("port") == p["port"]
                ):
                    return lst
        return {}

    def finish(self, changed, before, after, listener, task):
        result = dict(changed=changed, before=before, after=after, listener=listener)
        if task is not None:
            result["task"] = task
        self.exit(**result)


def main():
    NvmeofListenerModule().run()


if __name__ == "__main__":
    main()
