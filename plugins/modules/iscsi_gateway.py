#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/iscsi
# croit-api: GET /gateways/iscsi/servers
# croit-api: GET /services/iscsi/{serviceId}
# croit-api: POST /services/iscsi
# croit-api: PATCH /services/iscsi/{serviceId}
# croit-api: POST /services/iscsi/{serviceId}
# croit-api: DELETE /services/iscsi/{serviceId}
# croit-api: DELETE /services/iscsi/{serviceId}/servers/{hostname}
# croit-api: PUT /services/iscsi/{serviceId}/target
# croit-api: GET /servers

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: iscsi_gateway
short_description: Manage the iSCSI gateway of a croit cluster
version_added: 0.1.0
description:
  - Creates, updates and deletes the cluster's iSCSI gateway service. This includes its portal servers,
    its description, and the target IQN croit manages.
  - Ceph supports a single iSCSI gateway per cluster, so this module has no name. It manages B(the)
    gateway.
  - Initiators, host groups and exported disks are managed with M(croit.ceph.iscsi_client),
    M(croit.ceph.iscsi_group) and M(croit.ceph.iscsi_disk).
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
  state:
    description:
      - Whether the gateway should exist.
      - V(absent) removes the gateway and the whole target configuration, which B(disconnects every
        initiator). It needs O(confirm_delete=true).
    type: str
    choices: [present, absent]
    default: present
  service_id:
    description:
      - croit service id of the gateway. Only needed if croit ever reports more than one iSCSI gateway; by
        default the single gateway is used.
    type: int
  description:
    description:
      - Free-text description of the gateway service, shown in croit. Left alone when not set.
    type: str
  servers:
    description:
      - The B(complete) list of portal servers. Servers not listed are taken out of the target, and listed ones
        are added.
      - Required to create the gateway. When not set, the portals are left alone.
      - A portal's IP cannot be changed in place. Remove the server and add it again in two runs.
    type: list
    elements: dict
    suboptions:
      server:
        description: Server the portal runs on, by hostname or numeric croit id. croit must manage the server.
        type: str
        required: true
      ip:
        description: Client-facing IP address of the portal. It must be configured on the server.
        type: str
        required: true
  target:
    description:
      - Target IQN croit manages. Every other iSCSI module acts on this target.
      - croit warns before selecting an IQN the ceph-iscsi configuration does not carry yet. See
        O(ignore_warnings).
    type: str
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to remove an existing gateway.
      - Also confirms croit's own warning about removing the gateway.
    type: bool
    default: false
seealso:
  - module: croit.ceph.iscsi_info
    description: Read the gateway, its portals, exported disks, host groups and initiators.
  - module: croit.ceph.iscsi_client
    description: Allow initiators onto the target and map disks to them.
  - module: croit.ceph.iscsi_group
    description: Manage host groups and the disks mapped to them.
  - module: croit.ceph.iscsi_disk
    description: Grow, unexport or delete exported disks.
  - name: Ceph iSCSI gateway
    description: Upstream documentation of the Ceph iSCSI gateway.
    link: https://docs.ceph.com/en/latest/rbd/iscsi-overview/
  - name: croit API reference
    description: The croit REST API this module talks to.
    link: https://www.croit.io/api-docs
notes:
  - O(state=absent) removes the whole ceph-iscsi target configuration and B(disconnects every initiator). The RBD
    images behind the exported disks are kept.
  - When portals change, new portals are added before old ones are removed, because the target only lets a gateway
    go while the others are online.
  - When the gateway is created with O(wait=false) and croit has not written the service yet, O(target) is selected
    on a later run.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Create the iSCSI gateway on two portals
  croit.ceph.iscsi_gateway:
    description: VMware datastores
    servers:
      - server: storage-1
        ip: 10.10.0.11
      - server: storage-2
        ip: 10.10.0.12
  register: iscsi_gw

- name: Show the target IQN croit manages
  ansible.builtin.debug:
    msg: "{{ iscsi_gw.config.selectedTarget }}"

- name: Select the target croit manages
  croit.ceph.iscsi_gateway:
    target: iqn.2001-07.com.ceph:1700000000000

- name: Preview adding a third portal
  croit.ceph.iscsi_gateway:
    servers:
      - server: storage-1
        ip: 10.10.0.11
      - server: storage-2
        ip: 10.10.0.12
      - server: storage-3
        ip: 10.10.0.13
  check_mode: true
  diff: true

- name: Remove the gateway (disconnects every initiator)
  croit.ceph.iscsi_gateway:
    state: absent
    confirm_delete: true
"""

RETURN = r"""
gateway:
  description:
    - The gateway service (C(IscsiGatewayConfigResponse) in the croit API) after the change, with its portal
      servers in C(servers).
    - Empty when the gateway does not exist. Shows the state before the change in check mode.
  returned: always
  type: dict
  contains:
    serviceId:
      description: croit service id of the gateway.
      returned: when the gateway exists
      type: int
      sample: 7
    description:
      description: Description of the gateway service.
      returned: when the gateway exists
      type: str
      sample: VMware datastores
    servers:
      description: Portal servers of the gateway (C(IscsiGatewayServerResponse)), sorted by hostname.
      returned: when the gateway exists
      type: list
      elements: dict
      contains:
        hostname:
          description: Hostname of the portal server.
          returned: always
          type: str
          sample: storage-1
        serverId:
          description: croit id of the portal server.
          returned: always
          type: int
          sample: 1
        ip:
          description: Client-facing IP address of the portal.
          returned: always
          type: str
          sample: 10.10.0.11
        healthy:
          description: Whether the gateway is healthy on that server.
          returned: always
          type: bool
          sample: true
config:
  description:
    - The ceph-iscsi configuration of the gateway (C(IscsiGatewayConfig) in the croit API) after the change.
    - CHAP passwords in C(clients) are masked as C(********).
  returned: when the gateway exists after the run
  type: dict
  contains:
    iqn:
      description: IQN of the target in the ceph-iscsi configuration.
      returned: always
      type: str
      sample: iqn.2001-07.com.ceph:1700000000000
    selectedTarget:
      description: Target IQN croit manages, see O(target).
      returned: always
      type: str
      sample: iqn.2001-07.com.ceph:1700000000000
    targets:
      description: Every target IQN the ceph-iscsi configuration carries.
      returned: always
      type: list
      elements: str
      sample: [iqn.2001-07.com.ceph:1700000000000]
    gateways:
      description: Gateways of the target, each with C(name) and C(ip).
      returned: always
      type: list
      elements: dict
      sample:
        - name: storage-1
          ip: 10.10.0.11
    clients:
      description: Initiators with their CHAP credentials (password masked), host group and disks.
      returned: always
      type: list
      elements: dict
      sample:
        - name: iqn.1998-01.com.vmware:esx01-12345678
          username: esx01-user
          password: "********"
          group: ""
          luns: []
    groups:
      description: Host groups with their C(members) and disks (C(luns)).
      returned: always
      type: list
      elements: dict
      sample:
        - name: esx-cluster
          members: [iqn.1998-01.com.vmware:esx01-12345678]
          luns: []
    disks:
      description: Exported disks, each with C(pool), C(image) and C(wwn).
      returned: always
      type: list
      elements: dict
      sample:
        - pool: iscsi
          image: datastore1
          wwn: 3f0e8c7a-0c1d-4a5e-9b6f-2d3c4b5a6f70
    gatewayVersion:
      description: Version counter of the ceph-iscsi configuration.
      returned: always
      type: int
      sample: 12
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
      sample: Add iSCSI gateway
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
from ansible_collections.croit.ceph.plugins.module_utils.lookup import list_servers, require_server
from ansible_collections.croit.ceph.plugins.module_utils.iscsi import find_service
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

MASK = "********"


def masked_config(config):
    """The ceph-iscsi configuration with every CHAP password masked."""
    if not config:
        return {}
    result = dict(config)
    result["clients"] = [
        dict(client, password=MASK if client.get("password") else client.get("password"))
        for client in config.get("clients") or []
    ]
    return result


class IscsiGatewayModule(CroitModule):
    def __init__(self):
        super(IscsiGatewayModule, self).__init__(
            dict(
                state=dict(type="str", default="present", choices=["present", "absent"]),
                service_id=dict(type="int"),
                description=dict(type="str"),
                servers=dict(
                    type="list",
                    elements="dict",
                    options=dict(server=dict(type="str", required=True), ip=dict(type="str", required=True)),
                ),
                target=dict(type="str"),
                confirm_delete=dict(type="bool", default=False),
            ),
        )

    # Reads ----------------------------------------------------------------

    def portals(self, service_id):
        return sorted(
            (s for s in self.get_list("/gateways/iscsi/servers") if s.get("serviceId") == service_id),
            key=lambda s: s.get("hostname") or "",
        )

    def read(self, service):
        """(gateway, config) for an existing service."""
        gateway = dict(service, servers=self.portals(service["serviceId"]))
        config = self.get(path_join("services", "iscsi", service["serviceId"])) or {}
        return gateway, config

    def view(self, gateway, config):
        if not gateway:
            return {}
        return dict(
            description=gateway.get("description") or "",
            servers=[dict(server=s.get("hostname"), ip=s.get("ip")) for s in gateway.get("servers") or []],
            target=config.get("selectedTarget") or None,
        )

    def desired_servers(self):
        """Resolved desired portals: list of (server dict, ip), or None when not managed."""
        wanted = self.params["servers"]
        if wanted is None:
            return None
        if not wanted:
            self.module.fail_json(msg="servers must name at least one portal; use state=absent to remove the gateway")
        known = list_servers(self)
        resolved = []
        seen = set()
        for entry in wanted:
            server = require_server(self, entry["server"], known)
            if server["id"] in seen:
                self.module.fail_json(msg="Server %s is listed twice in servers" % server.get("hostname"))
            seen.add(server["id"])
            resolved.append((server, entry["ip"]))
        return resolved

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        service = find_service(self, p["service_id"])
        if p["state"] == "absent":
            return self.absent(service)
        if service is None:
            return self.create()
        return self.update(service)

    def absent(self, service):
        if service is None:
            self.exit(changed=False, gateway={})
        gateway, config = self.read(service)
        if not self.params["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to remove the iSCSI gateway (service %s) without confirm_delete=true: it removes the "
                "whole target configuration and disconnects every initiator" % service["serviceId"]
            )
        if not self.check_mode:
            self.write("DELETE", path_join("services", "iscsi", service["serviceId"]), confirm_warnings=True)
        self.exit(changed=True, before=self.view(gateway, config), after={}, gateway={})

    def create(self):
        p = self.params
        servers = self.desired_servers()
        if not servers:
            self.module.fail_json(msg="servers is required to create the iSCSI gateway")
        body = dict(servers=[dict(serverId=s["id"], ip=ip) for s, ip in servers])
        if p["description"] is not None:
            body["description"] = p["description"]
        after = dict(
            description=p["description"] or "",
            servers=sorted((dict(server=s.get("hostname"), ip=ip) for s, ip in servers), key=lambda x: x["server"]),
            target=p["target"],
        )
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, gateway={})

        result = dict(changed=True, before={}, after=after)
        task = self.handle_task(self.write("POST", "/services/iscsi", body=body))
        if task is not None:
            result["task"] = task
        service = find_service(self, p["service_id"])
        if service is None:
            # wait=false: croit has not written the service yet; a later run converges.
            self.exit(gateway={}, **result)
        gateway, config = self.read(service)
        if p["target"] is not None and p["target"] != config.get("selectedTarget"):
            self.write("PUT", path_join("services", "iscsi", service["serviceId"], "target"), body=p["target"])
            gateway, config = self.read(service)
        self.exit(gateway=gateway, config=masked_config(config), **result)

    def update(self, service):
        p = self.params
        sid = service["serviceId"]
        gateway, config = self.read(service)
        before = self.view(gateway, config)
        after = dict(before)

        current = dict((s.get("serverId"), s) for s in gateway["servers"])
        add, remove = [], []
        servers = self.desired_servers()
        if servers is not None:
            wanted_ids = set()
            for server, ip in servers:
                wanted_ids.add(server["id"])
                existing = current.get(server["id"])
                if existing is None:
                    add.append((server, ip))
                elif existing.get("ip") != ip:
                    self.module.fail_json(
                        msg="Portal %s uses IP %s; croit cannot change a portal's IP in place. Remove the server "
                        "from servers, then add it back with the new IP." % (server.get("hostname"), existing.get("ip"))
                    )
            remove = [s for sid_, s in sorted(current.items(), key=lambda kv: kv[1].get("hostname") or "") if sid_ not in wanted_ids]
            after["servers"] = sorted(
                (dict(server=s.get("hostname"), ip=ip) for s, ip in servers), key=lambda x: x["server"]
            )

        description_change = p["description"] is not None and p["description"] != (gateway.get("description") or "")
        if description_change:
            after["description"] = p["description"]
        target_change = p["target"] is not None and p["target"] != config.get("selectedTarget")
        if target_change:
            after["target"] = p["target"]

        changed = bool(add or remove or description_change or target_change)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, gateway=gateway, config=masked_config(config))

        tasks = []
        if description_change:
            self.write("PATCH", path_join("services", "iscsi", sid), body=dict(description=p["description"]))
        # Add before removing: the target only lets a gateway go while every other one is online.
        for server, ip in add:
            task = self.handle_task(self.write("POST", path_join("services", "iscsi", sid), body=dict(serverId=server["id"], ip=ip)))
            if task is not None:
                tasks.append(task)
        for portal in remove:
            task = self.handle_task(self.write("DELETE", path_join("services", "iscsi", sid, "servers", portal["hostname"])))
            if task is not None:
                tasks.append(task)
        if target_change:
            self.write("PUT", path_join("services", "iscsi", sid, "target"), body=p["target"])

        gateway, config = self.read(service)
        result = dict(changed=True, before=before, after=after, gateway=gateway, config=masked_config(config))
        if tasks:
            result["task"] = tasks[-1]
        self.exit(**result)


def main():
    IscsiGatewayModule().run()


if __name__ == "__main__":
    main()
