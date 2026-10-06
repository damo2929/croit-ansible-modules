#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/nvmeof
# croit-api: GET /gateways/nvmeof/services
# croit-api: GET /gateways/nvmeof/subsystems
# croit-api: POST /gateways/nvmeof/subsystems
# croit-api: PATCH /gateways/nvmeof/subsystems/{subsystemId}
# croit-api: DELETE /gateways/nvmeof/subsystems/{subsystemId}
# croit-api: POST /gateways/nvmeof/subsystems/{subsystemId}/attach-disks
# croit-api: POST /gateways/nvmeof/subsystems/{subsystemId}/detach-disks
# croit-api: POST /gateways/nvmeof/subsystems/{subsystemId}/attach-hosts
# croit-api: POST /gateways/nvmeof/subsystems/{subsystemId}/detach-hosts
# croit-api: GET /gateways/nvmeof/disks
# croit-api: GET /gateways/nvmeof/hosts

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nvmeof_subsystem
short_description: Manage NVMe-oF subsystems and what is attached to them on a croit cluster
version_added: 0.1.0
description:
  - Creates, updates and deletes an NVMe-oF subsystem of a croit NVMe-oF cluster, identified by its NQN.
  - Attaches exported disks (namespaces) and allowed hosts to it, and optionally detaches the ones that are
    not listed.
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
  gateway:
    description:
      - NVMe-oF cluster the subsystem belongs to, by name or numeric id.
    type: str
    required: true
  nqn:
    description:
      - NQN of the subsystem, unique within the NVMe-oF cluster.
    type: str
    required: true
  state:
    description:
      - Whether the subsystem should exist.
      - V(absent) deletes the subsystem, which B(disconnects every host) from its namespaces, and needs
        O(confirm_delete=true). The exported disks and the RBD images behind them are kept.
    type: str
    choices: [present, absent]
    default: present
  serial_number:
    description:
      - Serial number the subsystem reports.
    type: str
  model_number:
    description:
      - Model name the subsystem reports.
    type: str
  max_namespaces:
    description:
      - Maximum number of disks that can be attached.
    type: int
  ana_states:
    description:
      - Access state the subsystem advertises per target service, where it should differ from the service's
        own state.
      - This is the B(complete) list. V([]) makes every service advertise its own state again.
      - At most one service may be V(optimized).
    type: list
    elements: dict
    suboptions:
      service:
        description: Target service, by the hostname of its server, its service name or its numeric id.
        type: str
        required: true
      state:
        description: Access state.
        type: str
        choices: [optimized, non_optimized, inaccessible]
        required: true
  disks:
    description:
      - Exported disks to attach, as V(pool/image) or croit's numeric disk id. Export them first with
        M(croit.ceph.nvmeof_disk).
      - Listed disks are attached when missing. Disks that are not listed are only detached with
        O(exclusive=true).
    type: list
    elements: str
  hosts:
    description:
      - Host NQNs allowed to connect. Add them first with M(croit.ceph.nvmeof_host).
      - Listed hosts are attached when missing. Hosts that are not listed are only detached with
        O(exclusive=true).
    type: list
    elements: str
  exclusive:
    description:
      - Detach disks and hosts that are not in O(disks) and O(hosts). Only applies to the lists that are set.
      - Detaching a disk removes the namespace from every connected host.
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing subsystem.
    type: bool
    default: false
notes:
  - Changes after a creation (serial number, ANA states, attachments) are only applied with O(wait=true).
"""

EXAMPLES = r"""
- name: Subsystem with two namespaces, open to two ESXi hosts
  croit.ceph.nvmeof_subsystem:
    gateway: nvme-prod
    nqn: nqn.2016-06.io.spdk:datastore1
    max_namespaces: 64
    ana_states:
      - service: nvme1
        state: optimized
      - service: nvme2
        state: non_optimized
    disks:
      - rbd/ds1-lun0
      - rbd/ds1-lun1
    hosts:
      - nqn.2014-08.org.nvmexpress:uuid:esxi-01
      - nqn.2014-08.org.nvmexpress:uuid:esxi-02

- name: Make exactly these hosts allowed
  croit.ceph.nvmeof_subsystem:
    gateway: nvme-prod
    nqn: nqn.2016-06.io.spdk:datastore1
    hosts:
      - nqn.2014-08.org.nvmexpress:uuid:esxi-01
    exclusive: true

- name: Delete the subsystem (disconnects every host)
  croit.ceph.nvmeof_subsystem:
    gateway: nvme-prod
    nqn: nqn.2016-06.io.spdk:old
    state: absent
    confirm_delete: true
"""

RETURN = r"""
subsystem:
  description:
    - The subsystem as croit reports it after the change (C(NvmeOFSubsystemResponse)).
    - Before the change in check mode; empty when it does not exist.
  returned: always
  type: dict
  sample:
    id: 4
    gatewayId: 1
    nqn: nqn.2016-06.io.spdk:datastore1
    maxNamespaces: 64
    disks: [7, 8]
    hosts: [3]
task:
  description: The last croit background task the change ran as.
  returned: when a task ran
  type: dict
tasks:
  description: Every croit background task the change ran as, in order.
  returned: when a task ran
  type: list
  elements: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.nvmeof import find_service, require_gateway
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

FIELDS = dict(serial_number="serialNumber", model_number="modelNumber", max_namespaces="maxNamespaces")


def disk_label(disk):
    if disk.get("pool") and disk.get("image"):
        return "%s/%s" % (disk["pool"], disk["image"])
    return str(disk.get("id"))


class NvmeofSubsystemModule(CroitModule):
    def __init__(self):
        super(NvmeofSubsystemModule, self).__init__(
            dict(
                gateway=dict(type="str", required=True),
                nqn=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                serial_number=dict(type="str"),
                model_number=dict(type="str"),
                max_namespaces=dict(type="int"),
                ana_states=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        service=dict(type="str", required=True),
                        state=dict(type="str", required=True, choices=["optimized", "non_optimized", "inaccessible"]),
                    ),
                ),
                disks=dict(type="list", elements="str"),
                hosts=dict(type="list", elements="str"),
                exclusive=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
        )
        self.tasks = []

    def run_write(self, method, path, body=None):
        task = self.handle_task(self.write(method, path, body=body))
        if task is not None:
            self.tasks.append(task)

    # Lookups --------------------------------------------------------------

    def find_subsystem(self):
        matches = [
            s
            for s in self.get_list("/gateways/nvmeof/subsystems")
            if s.get("gatewayId") == self.gateway["gatewayId"] and s.get("nqn") == self.params["nqn"]
        ]
        return matches[0] if matches else None

    def resolve_disks(self):
        wanted = self.params["disks"]
        if wanted is None:
            return None
        resolved = {}
        for ident in wanted:
            text = str(ident)
            match = next((d for d in self.all_disks if disk_label(d) == text), None)
            if match is None and text.isdigit():
                match = next((d for d in self.all_disks if d.get("id") == int(text)), None)
            if match is None:
                self.module.fail_json(
                    msg="Disk %r is not exported by NVMe-oF cluster %r; export it with croit.ceph.nvmeof_disk first. "
                    "Exported disks: %s" % (ident, self.gateway["name"], ", ".join(disk_label(d) for d in self.all_disks) or "none")
                )
            resolved[match["id"]] = disk_label(match)
        return resolved

    def resolve_hosts(self):
        wanted = self.params["hosts"]
        if wanted is None:
            return None
        resolved = {}
        for nqn in wanted:
            match = next((h for h in self.all_hosts if h.get("nqn") == nqn), None)
            if match is None:
                self.module.fail_json(
                    msg="Host %r is not known to NVMe-oF cluster %r; add it with croit.ceph.nvmeof_host first"
                    % (nqn, self.gateway["name"])
                )
            resolved[match["id"]] = nqn
        return resolved

    def resolve_ana_states(self):
        wanted = self.params["ana_states"]
        if wanted is None:
            return None
        result = {}
        for item in wanted:
            try:
                service = find_service(self.services, item["service"])
            except ValueError as e:
                self.module.fail_json(msg=str(e))
            if service is None:
                self.module.fail_json(
                    msg="NVMe-oF cluster %r has no target service %r. Services: %s"
                    % (self.gateway["name"], item["service"], ", ".join(s.get("serverHostname") for s in self.services) or "none")
                )
            if service["serviceId"] in result:
                self.module.fail_json(msg="ana_states lists service %r more than once" % item["service"])
            result[service["serviceId"]] = item["state"]
        if list(result.values()).count("optimized") > 1:
            self.module.fail_json(msg="At most one service may be optimized for a subsystem")
        return result

    # Views ----------------------------------------------------------------

    def service_label(self, service_id):
        service = next((s for s in self.services if s.get("serviceId") == service_id), None)
        return service.get("serverHostname") if service else str(service_id)

    def disk_labels(self, ids):
        labels = dict((d["id"], disk_label(d)) for d in self.all_disks)
        return sorted(labels.get(i, str(i)) for i in ids)

    def host_labels(self, ids):
        labels = dict((h["id"], h.get("nqn")) for h in self.all_hosts)
        return sorted(labels.get(i, str(i)) for i in ids)

    def view(self, sub):
        if not sub:
            return {}
        view = dict((opt, sub.get(api)) for opt, api in FIELDS.items())
        view["ana_states"] = dict((self.service_label(a["serviceId"]), a["anaState"]) for a in sub.get("anaStates") or [])
        view["disks"] = self.disk_labels(sub.get("disks") or [])
        view["hosts"] = self.host_labels(sub.get("hosts") or [])
        return view

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        self.gateway = require_gateway(self, p["gateway"])
        gid = self.gateway["gatewayId"]
        self.services = [s for s in self.get_list("/gateways/nvmeof/services") if s.get("gatewayId") == gid]
        self.all_disks = [d for d in self.get_list("/gateways/nvmeof/disks") if d.get("gatewayId") == gid]
        self.all_hosts = [h for h in self.get_list("/gateways/nvmeof/hosts") if h.get("gatewayId") == gid]
        current = self.find_subsystem()

        if p["state"] == "absent":
            return self.absent(current)

        disks = self.resolve_disks()
        hosts = self.resolve_hosts()
        ana = self.resolve_ana_states()
        before = self.view(current)
        cur = current or dict(anaStates=[], disks=[], hosts=[])

        fields = {}
        for opt, api in FIELDS.items():
            if p[opt] is not None and (current is None or current.get(api) != p[opt]):
                fields[api] = p[opt]
        current_ana = dict((a["serviceId"], a["anaState"]) for a in cur.get("anaStates") or [])
        if ana is not None and ana != current_ana:
            fields["anaStates"] = [dict(serviceId=k, anaState=v) for k, v in sorted(ana.items())]

        plan = []
        for kind, wanted in (("disks", disks), ("hosts", hosts)):
            if wanted is None:
                continue
            have = set(cur.get(kind) or [])
            if p["exclusive"]:
                detach = sorted(have - set(wanted))
                if detach:
                    plan.append(("detach", kind, detach))
            attach = sorted(set(wanted) - have)
            if attach:
                plan.append(("attach", kind, attach))

        after = dict(before) if current else dict(
            serial_number=None, model_number=None, max_namespaces=None, ana_states={}, disks=[], hosts=[]
        )
        for opt, api in FIELDS.items():
            if api in fields:
                after[opt] = fields[api]
        if "anaStates" in fields:
            after["ana_states"] = dict((self.service_label(k), v) for k, v in ana.items())
        for op, kind, ids in plan:
            labels = self.disk_labels(ids) if kind == "disks" else self.host_labels(ids)
            if op == "attach":
                after[kind] = sorted(set(after[kind]) | set(labels))
            else:
                after[kind] = sorted(set(after[kind]) - set(labels))

        changed = current is None or bool(fields or plan)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, subsystem=current or {})

        if current is None:
            self.run_write("POST", "/gateways/nvmeof/subsystems", body=dict(gatewayId=self.gateway["gatewayId"], nqn=p["nqn"]))
            if not p["wait"]:
                if fields or plan:
                    self.module.warn("Settings and attachments of the new subsystem are applied on the next run, because wait=false")
                self.finish(before, after)
            current = self.find_subsystem()
            if current is None:
                self.module.fail_json(msg="croit created subsystem %r but does not list it" % p["nqn"], tasks=self.tasks)

        sub_path = path_join("gateways", "nvmeof", "subsystems", current["id"])
        if fields:
            self.run_write("PATCH", sub_path, body=fields)
        for op, kind, ids in plan:
            self.run_write("POST", "%s/%s-%s" % (sub_path, op, kind), body={kind: ids})
        self.finish(before, after)

    def finish(self, before, after):
        result = dict(changed=True, before=before, after=after, subsystem=self.find_subsystem() or {})
        if self.tasks:
            result["task"] = self.tasks[-1]
            result["tasks"] = self.tasks
        self.exit(**result)

    def absent(self, current):
        if current is None:
            self.exit(changed=False, subsystem={})
        if not self.params["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to delete subsystem %r without confirm_delete=true; it disconnects every host from its "
                "namespaces" % current["nqn"]
            )
        before = self.view(current)
        if not self.check_mode:
            self.run_write("DELETE", path_join("gateways", "nvmeof", "subsystems", current["id"]))
        result = dict(changed=True, before=before, after={}, subsystem={})
        if self.tasks:
            result["task"] = self.tasks[-1]
            result["tasks"] = self.tasks
        self.exit(**result)


def main():
    NvmeofSubsystemModule().run()


if __name__ == "__main__":
    main()
