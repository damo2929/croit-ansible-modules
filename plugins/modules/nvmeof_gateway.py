#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/nvmeof
# croit-api: POST /gateways/nvmeof
# croit-api: PATCH /gateways/nvmeof/{gatewayId}
# croit-api: DELETE /gateways/nvmeof/{gatewayId}
# croit-api: POST /gateways/nvmeof/{gatewayId}
# croit-api: PATCH /gateways/nvmeof/{gatewayId}/services/{serviceId}
# croit-api: POST /gateways/nvmeof/{gatewayId}/reconfigure
# croit-api: GET /gateways/nvmeof/services
# croit-api: GET /gateways/nvmeof/ceph-clusters
# croit-api: POST /gateways/nvmeof/ceph-clusters
# croit-api: DELETE /gateways/nvmeof/ceph-clusters/{name}
# croit-api: GET /servers

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nvmeof_gateway
short_description: Manage NVMe-oF gateway clusters and their target services on a croit cluster
version_added: 0.1.0
description:
  - Creates, updates and deletes a croit NVMe over Fabrics cluster (a set of C(nvmf_tgt) target services
    that serve the same subsystems), its transport defaults and its target services.
  - Also manages the cluster-wide list of ceph cluster configurations the targets read RBD images through.
  - Only options that are set are managed; anything left out keeps its current value.
  - Subsystems, exported disks, hosts and listeners have their own modules
    (M(croit.ceph.nvmeof_subsystem), M(croit.ceph.nvmeof_disk), M(croit.ceph.nvmeof_host),
    M(croit.ceph.nvmeof_listener)).
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
      - Name of the NVMe-oF cluster in croit. This is how the module finds it.
      - croit does not require names to be unique; if several clusters share the name the module fails.
    type: str
    required: true
  state:
    description:
      - Whether the NVMe-oF cluster should exist.
      - V(absent) stops and removes every target service of the cluster and deletes its subsystems, hosts,
        exported disks and listeners, which B(disconnects every host). It needs O(confirm_delete=true).
        The RBD images behind the exported disks are kept.
    type: str
    choices: [present, absent]
    default: present
  description:
    description:
      - Description of the cluster shown in croit.
    type: str
  force_secure:
    description:
      - Force TLS on every listener of the cluster, whatever a listener's own setting says.
    type: bool
  transport_defaults:
    description:
      - Default settings per fabric, which target services inherit unless they set their own.
      - This is the B(complete) list; fabrics left out lose their defaults. V([]) removes all of them.
    type: list
    elements: dict
    suboptions:
      type:
        description: Fabric the settings apply to.
        type: str
        choices: [tcp, rdma]
        required: true
      in_capsule_data_size:
        description: In-capsule data size. SPDK's default when not set.
        type: int
      io_unit_size:
        description: I/O unit size in bytes. SPDK's default when not set.
        type: int
      max_io_qpairs_per_ctrlr:
        description: Maximum I/O queue pairs per controller. SPDK's default when not set.
        type: int
      max_io_size:
        description: Maximum I/O size in bytes. SPDK's default when not set.
        type: int
  services:
    description:
      - Target services of the cluster, one per server.
      - Listed services are created when missing and updated when they differ. Services that are not listed
        are left alone; remove a target service with M(croit.ceph.service).
      - Listeners are managed with M(croit.ceph.nvmeof_listener).
    type: list
    elements: dict
    suboptions:
      server:
        description: Server (hostname or id) the target service runs on.
        type: str
        required: true
      description:
        description: Description of the service shown in croit.
        type: str
      nr_hugepages:
        description: Number of hugepages to reserve on the server. This overwrites the server's setting.
        type: int
      cpu_cores:
        description:
          - CPU cores the target runs on, as a list such as V(1-3,5). V("") derives them from the server's CPUs.
          - Applied at the target's next start.
        type: str
      ana_state:
        description: Access state every listener of the service advertises.
        type: str
        choices: [optimized, non_optimized, inaccessible]
      transports:
        description:
          - Per-fabric settings of this service, overriding the cluster's O(transport_defaults).
          - This is the B(complete) list for the service. V([]) removes the service's own settings.
        type: list
        elements: dict
        suboptions:
          type:
            description: Fabric the settings apply to.
            type: str
            choices: [tcp, rdma]
            required: true
          in_capsule_data_size:
            description: In-capsule data size. SPDK's default when not set.
            type: int
          io_unit_size:
            description: I/O unit size in bytes. SPDK's default when not set.
            type: int
          max_io_qpairs_per_ctrlr:
            description: Maximum I/O queue pairs per controller. SPDK's default when not set.
            type: int
          max_io_size:
            description: Maximum I/O size in bytes. SPDK's default when not set.
            type: int
  ceph_clusters:
    description:
      - Ceph cluster configurations the target services read RBD images through, and the ceph client each
        authenticates as. These are B(shared by all NVMe-oF clusters) in croit.
      - Only the listed configurations are managed. A configuration cannot be changed once it exists, so a
        different O(ceph_clusters[].client_id) fails; croit also refuses to delete one that exported disks use.
      - Applied before the NVMe-oF cluster is created, and after it is deleted.
    type: list
    elements: dict
    suboptions:
      name:
        description: Name of the ceph cluster configuration.
        type: str
        required: true
      client_id:
        description: Ceph client the targets authenticate as. croit's own client when not set at creation.
        type: str
      state:
        description: Whether the configuration should exist.
        type: str
        choices: [present, absent]
        default: present
  reconfigure:
    description:
      - Push the cluster's configuration to every server it runs on again, for example after a target and croit
        drifted apart.
      - This is a one-shot action. It always reports a change and is skipped in check mode.
    type: bool
    default: false
  reconfigure_from_scratch:
    description:
      - With O(reconfigure=true), rebuild the targets' configuration from scratch instead of applying changes.
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing NVMe-oF cluster.
      - It also confirms croit's warning about deleting the cluster.
    type: bool
    default: false
notes:
  - Creating the cluster also makes croit create one subsystem for it; manage it with
    M(croit.ceph.nvmeof_subsystem).
  - Follow-up changes after a creation (for example O(services[].ana_state) of a new service) are only
    applied with O(wait=true).
"""

EXAMPLES = r"""
- name: NVMe-oF cluster on two servers
  croit.ceph.nvmeof_gateway:
    name: nvme-prod
    description: VMware datastores
    transport_defaults:
      - type: tcp
        max_io_qpairs_per_ctrlr: 127
    services:
      - server: nvme1
        nr_hugepages: 4096
      - server: nvme2
        nr_hugepages: 4096
        ana_state: non_optimized

- name: Ceph cluster configuration used by exported disks
  croit.ceph.nvmeof_gateway:
    name: nvme-prod
    ceph_clusters:
      - name: ceph-nvmeof
        client_id: nvmeof

- name: Push the configuration to the targets again
  croit.ceph.nvmeof_gateway:
    name: nvme-prod
    reconfigure: true

- name: Delete the cluster (disconnects every host)
  croit.ceph.nvmeof_gateway:
    name: nvme-old
    state: absent
    confirm_delete: true
"""

RETURN = r"""
gateway:
  description:
    - The NVMe-oF cluster as croit reports it after the change (C(NvmeOFGatewayResponse)).
    - Before the change in check mode; empty when it does not exist.
  returned: always
  type: dict
  sample:
    gatewayId: 1
    name: nvme-prod
    description: VMware datastores
    forceSecure: false
    transportDefaults: []
services:
  description: The cluster's target services (C(NvmeOFServiceResponse)).
  returned: always
  type: list
  elements: dict
ceph_clusters:
  description: All ceph cluster configurations, when O(ceph_clusters) is set.
  returned: when O(ceph_clusters) is set
  type: list
  elements: dict
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
from ansible_collections.croit.ceph.plugins.module_utils.lookup import list_servers, require_server
from ansible_collections.croit.ceph.plugins.module_utils.nvmeof import find_gateway, require_gateway
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

TRANSPORT_OPTIONS = dict(
    type=dict(type="str", required=True, choices=["tcp", "rdma"]),
    in_capsule_data_size=dict(type="int"),
    io_unit_size=dict(type="int"),
    max_io_qpairs_per_ctrlr=dict(type="int"),
    max_io_size=dict(type="int"),
)
TRANSPORT_FIELDS = dict(
    in_capsule_data_size="inCapsuleDataSize",
    io_unit_size="ioUnitSize",
    max_io_qpairs_per_ctrlr="maxIoQpairsPerCtrlr",
    max_io_size="maxIoSize",
)
SERVICE_FIELDS = dict(description="description", nr_hugepages="nrHugepages", cpu_cores="cpuCores", ana_state="anaState")
EMPTY_IS_UNSET = ("description", "cpu_cores")


def transports_view(rows):
    """croit transport rows -> {fabric: {option: value}}, comparable with transports_desired()."""
    return dict(
        (row["type"].lower(), dict((opt, row.get(api)) for opt, api in TRANSPORT_FIELDS.items())) for row in rows or []
    )


def transports_desired(items):
    if items is None:
        return None
    view = {}
    for item in items:
        if item["type"] in view:
            return item["type"]
        view[item["type"]] = dict((opt, item.get(opt)) for opt in TRANSPORT_FIELDS)
    return view


def transports_request(view):
    return [
        dict([("type", fabric.upper())] + [(api, view[fabric][opt]) for opt, api in TRANSPORT_FIELDS.items() if view[fabric][opt] is not None])
        for fabric in sorted(view)
    ]


def gateway_view(gateway):
    if not gateway:
        return {}
    return dict(
        name=gateway.get("name"),
        description=gateway.get("description") or "",
        force_secure=bool(gateway.get("forceSecure")),
        transport_defaults=transports_view(gateway.get("transportDefaults")),
    )


def service_view(service):
    view = dict((opt, service.get(api)) for opt, api in SERVICE_FIELDS.items())
    for opt in EMPTY_IS_UNSET:
        view[opt] = view[opt] or ""
    view["transports"] = transports_view(service.get("transports"))
    return view


class NvmeofGatewayModule(CroitModule):
    def __init__(self):
        transport = dict(type="list", elements="dict", options=TRANSPORT_OPTIONS)
        super(NvmeofGatewayModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                description=dict(type="str"),
                force_secure=dict(type="bool"),
                transport_defaults=transport,
                services=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        server=dict(type="str", required=True),
                        description=dict(type="str"),
                        nr_hugepages=dict(type="int"),
                        cpu_cores=dict(type="str"),
                        ana_state=dict(type="str", choices=["optimized", "non_optimized", "inaccessible"]),
                        transports=dict(type="list", elements="dict", options=TRANSPORT_OPTIONS),
                    ),
                ),
                ceph_clusters=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        name=dict(type="str", required=True),
                        client_id=dict(type="str"),
                        state=dict(type="str", default="present", choices=["present", "absent"]),
                    ),
                ),
                reconfigure=dict(type="bool", default=False),
                reconfigure_from_scratch=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
        )
        self.tasks = []
        self.changed = False
        self.before = {}
        self.after = {}

    # Helpers --------------------------------------------------------------

    def run_write(self, method, path, body=None, query=None, confirm_warnings=False):
        task = self.handle_task(self.write(method, path, body=body, query=query, confirm_warnings=confirm_warnings))
        if task is not None:
            self.tasks.append(task)
        return task

    def gateway_services(self, gateway_id):
        return [s for s in self.get_list("/gateways/nvmeof/services") if s.get("gatewayId") == gateway_id]

    def desired_transports(self, items, what):
        view = transports_desired(items)
        if isinstance(view, str):
            self.module.fail_json(msg="%s lists fabric %r more than once" % (what, view))
        return view

    # Ceph cluster configurations -----------------------------------------

    def plan_ceph_clusters(self):
        wanted = self.params["ceph_clusters"]
        if wanted is None:
            return []
        current = dict((c.get("name"), c) for c in self.get_list("/gateways/nvmeof/ceph-clusters"))
        before = dict((name, c.get("clientId")) for name, c in current.items())
        after = dict(before)
        plan = []
        seen = set()
        for item in wanted:
            name = item["name"]
            if name in seen:
                self.module.fail_json(msg="ceph_clusters lists %r more than once" % name)
            seen.add(name)
            existing = current.get(name)
            if item["state"] == "absent":
                if existing is not None:
                    plan.append(("DELETE", name, None))
                    after.pop(name, None)
                continue
            if existing is None:
                body = dict(name=name)
                if item["client_id"] is not None:
                    body["clientId"] = item["client_id"]
                plan.append(("POST", name, body))
                after[name] = item["client_id"]
            elif item["client_id"] is not None and (existing.get("clientId") or "") != item["client_id"]:
                self.module.fail_json(
                    msg="Ceph cluster configuration %r uses client %r and cannot be changed to %r; croit has no update "
                    "for it. Delete it (state=absent) and create it again." % (name, existing.get("clientId"), item["client_id"])
                )
        if plan:
            self.changed = True
        self.before["ceph_clusters"] = before
        self.after["ceph_clusters"] = after
        return plan

    def apply_ceph_clusters(self, plan):
        for method, name, body in plan:
            if method == "POST":
                self.run_write("POST", "/gateways/nvmeof/ceph-clusters", body=body)
            else:
                self.run_write("DELETE", path_join("gateways", "nvmeof", "ceph-clusters", name))

    # Desired state --------------------------------------------------------

    def desired_gateway(self):
        p = self.params
        desired = {}
        if p["description"] is not None:
            desired["description"] = p["description"]
        if p["force_secure"] is not None:
            desired["force_secure"] = p["force_secure"]
        transports = self.desired_transports(p["transport_defaults"], "transport_defaults")
        if transports is not None:
            desired["transport_defaults"] = transports
        return desired

    def desired_services(self):
        items = self.params["services"]
        if items is None:
            return None
        servers = list_servers(self)
        result = []
        seen = set()
        for item in items:
            server = require_server(self, item["server"], servers)
            if server["id"] in seen:
                self.module.fail_json(msg="services lists server %s more than once" % server["hostname"])
            seen.add(server["id"])
            desired = dict((opt, item[opt]) for opt in SERVICE_FIELDS if item[opt] is not None)
            transports = self.desired_transports(item["transports"], "services[%s].transports" % server["hostname"])
            if transports is not None:
                desired["transports"] = transports
            result.append((server, desired))
        return result

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        if p["state"] == "absent" and p["reconfigure"]:
            self.module.fail_json(msg="reconfigure cannot be combined with state=absent")
        gateways = self.get_list("/gateways/nvmeof")
        current = find_gateway(self, p["name"], gateways)
        if p["state"] == "absent":
            return self.absent(current)
        plan = self.plan_ceph_clusters()
        if current is None:
            return self.create(plan)
        return self.update(current, plan)

    def finish(self, gateway, services):
        result = dict(changed=self.changed, before=self.before, after=self.after, gateway=gateway or {}, services=services)
        if self.params["ceph_clusters"] is not None:
            result["ceph_clusters"] = self.get_list("/gateways/nvmeof/ceph-clusters")
        if self.tasks:
            result["task"] = self.tasks[-1]
            result["tasks"] = self.tasks
        self.exit(**result)

    def absent(self, current):
        p = self.params
        if current is not None:
            if not p["confirm_delete"]:
                self.module.fail_json(
                    msg="Refusing to delete NVMe-oF cluster %r without confirm_delete=true; it disconnects every host "
                    "and removes its subsystems, hosts, exported disks and listeners" % current["name"]
                )
            self.changed = True
            self.before["gateway"] = gateway_view(current)
            self.after["gateway"] = {}
        plan = self.plan_ceph_clusters()
        if not self.check_mode:
            if current is not None:
                self.run_write("DELETE", path_join("gateways", "nvmeof", current["gatewayId"]), confirm_warnings=True)
            self.apply_ceph_clusters(plan)
        self.finish({}, [])

    def create(self, plan):
        p = self.params
        desired = self.desired_gateway()
        services = self.desired_services() or []
        self.changed = True
        self.before["gateway"] = {}
        self.after["gateway"] = dict(
            name=p["name"],
            description=desired.get("description", ""),
            force_secure=desired.get("force_secure", False),
            transport_defaults=desired.get("transport_defaults", {}),
        )
        self.before["services"] = {}
        self.after["services"] = dict((server["hostname"], desired_svc) for server, desired_svc in services)
        if self.check_mode:
            self.finish({}, [])

        self.apply_ceph_clusters(plan)
        body = dict(name=p["name"])
        if "description" in desired:
            body["description"] = desired["description"]
        if "force_secure" in desired:
            body["forceSecure"] = desired["force_secure"]
        if "transport_defaults" in desired:
            body["transportDefaults"] = transports_request(desired["transport_defaults"])
        if services:
            body["services"] = [self.service_create_body(server, svc) for server, svc in services]
        self.run_write("POST", "/gateways/nvmeof", body=body)

        if not p["wait"]:
            if any("ana_state" in svc for _server, svc in services):
                self.module.warn("ana_state of the new services is applied on the next run, because wait=false")
            self.finish(find_gateway(self, p["name"], self.get_list("/gateways/nvmeof")) or {}, [])
        gateway = require_gateway(self, p["name"])
        current_services = self.gateway_services(gateway["gatewayId"])
        for server, svc in services:
            existing = next((s for s in current_services if s.get("serverId") == server["id"]), None)
            if existing is not None and "ana_state" in svc and existing.get("anaState") != svc["ana_state"]:
                self.patch_service(gateway, existing, dict(anaState=svc["ana_state"]))
        if p["reconfigure"]:
            self.reconfigure(gateway)
        self.finish(gateway, self.gateway_services(gateway["gatewayId"]))

    def update(self, current, plan):
        p = self.params
        desired = self.desired_gateway()
        before = gateway_view(current)
        changes = dict((k, v) for k, v in desired.items() if before.get(k) != v)
        after = dict(before)
        after.update(changes)
        self.before["gateway"] = before
        self.after["gateway"] = after

        services = self.desired_services()
        current_services = self.gateway_services(current["gatewayId"])
        service_plan = []
        if services is not None:
            self.before["services"] = {}
            self.after["services"] = {}
            for server, svc in services:
                existing = next((s for s in current_services if s.get("serverId") == server["id"]), None)
                if existing is None:
                    self.after["services"][server["hostname"]] = svc
                    service_plan.append((server, None, svc))
                    continue
                view = service_view(existing)
                svc_changes = dict((k, v) for k, v in svc.items() if view.get(k) != v)
                self.before["services"][server["hostname"]] = dict((k, view.get(k)) for k in svc)
                self.after["services"][server["hostname"]] = dict(self.before["services"][server["hostname"]], **svc_changes)
                if svc_changes:
                    service_plan.append((server, existing, svc_changes))

        if changes or service_plan:
            self.changed = True
        if p["reconfigure"]:
            self.changed = True
        if self.check_mode:
            self.finish(current, current_services)

        self.apply_ceph_clusters(plan)
        gateway_path = path_join("gateways", "nvmeof", current["gatewayId"])
        if changes:
            body = {}
            if "description" in changes:
                body["description"] = changes["description"]
            if "force_secure" in changes:
                body["forceSecure"] = changes["force_secure"]
            if "transport_defaults" in changes:
                body["transportDefaults"] = transports_request(changes["transport_defaults"])
            self.run_write("PATCH", gateway_path, body=body)
        for server, existing, svc in service_plan:
            if existing is None:
                self.run_write("POST", gateway_path, body=self.service_create_body(server, svc))
                if "ana_state" in svc and p["wait"]:
                    created = next((s for s in self.gateway_services(current["gatewayId"]) if s.get("serverId") == server["id"]), None)
                    if created is not None and created.get("anaState") != svc["ana_state"]:
                        self.patch_service(current, created, dict(anaState=svc["ana_state"]))
            else:
                self.patch_service(current, existing, self.service_patch_body(svc))
        if p["reconfigure"]:
            self.reconfigure(current)
        gateway = find_gateway(self, p["name"], self.get_list("/gateways/nvmeof")) or current
        self.finish(gateway, self.gateway_services(current["gatewayId"]))

    # Requests -------------------------------------------------------------

    @staticmethod
    def service_create_body(server, svc):
        body = dict(serverId=server["id"])
        for opt, api in SERVICE_FIELDS.items():
            if opt in svc and opt != "ana_state":
                body[api] = svc[opt]
        if "transports" in svc:
            body["transports"] = transports_request(svc["transports"])
        return body

    @staticmethod
    def service_patch_body(changes):
        body = dict((SERVICE_FIELDS[opt], value) for opt, value in changes.items() if opt in SERVICE_FIELDS)
        if "transports" in changes:
            body["transports"] = transports_request(changes["transports"])
        return body

    def patch_service(self, gateway, service, body):
        self.run_write(
            "PATCH", path_join("gateways", "nvmeof", gateway["gatewayId"], "services", service["serviceId"]), body=body
        )

    def reconfigure(self, gateway):
        query = dict(fromScratch=True) if self.params["reconfigure_from_scratch"] else None
        self.run_write("POST", path_join("gateways", "nvmeof", gateway["gatewayId"], "reconfigure"), query=query)


def main():
    NvmeofGatewayModule().run()


if __name__ == "__main__":
    main()
