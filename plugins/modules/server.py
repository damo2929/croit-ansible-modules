#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /servers
# croit-api: PATCH /servers/{serverId}
# croit-api: DELETE /servers/{serverId}
# croit-api: POST /servers/{serverId}/reboot
# croit-api: POST /servers/{serverId}/shutdown
# croit-api: POST /servers/{serverId}/redetect

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: server
short_description: Manage servers (nodes) of a croit cluster
version_added: 0.1.0
description:
  - Manages the settings croit keeps for a server it already knows, and runs one-shot actions on it.
  - Servers cannot be created through the API; a node registers itself when it boots from croit.
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
    details:
      - O(action) is never run in check mode; it is reported as a change.
  diff_mode:
    support: full
notes:
  - O(action=reboot) and O(action=shutdown) take a storage node offline; they are refused unless
    O(confirm_action=true), also in check mode.
  - Changing O(ip) to an address the node does not have would cut croit off from it, so the module checks
    the address against the server's own addresses before sending anything.
seealso:
  - module: croit.ceph.server_info
    description: Read servers and their interfaces.
  - module: croit.ceph.server_nic
    description: Manage the network interfaces of a server.
  - module: croit.ceph.ipmi
    description: Power servers on and off through their BMC.
  - module: croit.ceph.task
    description: Answer the question a reboot or shutdown asks when ceph's safety check objects.
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
options:
  server:
    description:
      - The server, by its current hostname or its numeric croit id.
      - When renaming with O(hostname), a server that already has the new hostname is accepted, so the
        task stays idempotent after the rename.
    type: str
    required: true
  state:
    description:
      - V(present) manages the server's settings.
      - V(absent) makes croit forget the server and needs O(confirm_delete=true). The node itself keeps
        running and registers again the next time it boots. croit refuses while a Ceph monitor is
        configured on it.
    type: str
    choices: [present, absent]
    default: present
  hostname:
    description:
      - New hostname of the server. croit refuses to rename an iSCSI gateway.
    type: str
  ip:
    description:
      - Management IP croit reaches the node on. Must already be one of the server's interface addresses
        (the C(ips) member of RV(server)); this selects an address, it does not configure one.
    type: str
  image:
    description:
      - Id of the OS image to boot, or V(default) to follow the cluster's default image.
      - croit warns about image changes it considers risky, see O(ignore_warnings).
    type: str
  notes:
    description:
      - Free text croit keeps about the server. An empty string clears it.
    type: str
  nr_hugepages:
    description:
      - Number of 2 MiB hugepages to configure, for services such as NVMe-oF that need them.
    type: int
  action:
    description:
      - One-shot action run after the settings are applied. Always reported as a change; skipped in check mode.
      - V(redetect) asks the node to report its hardware again.
      - V(reboot) stops the node's OSDs behind the cluster's safety check, reboots it and waits for it to
        come back. Needs O(confirm_action=true).
      - V(shutdown) stops the node's OSDs and powers it off. Nothing powers it on again. Needs O(confirm_action=true).
      - If croit's safety check finds that stopping the OSDs would leave placement groups inactive, the task
        asks a question and this module fails; answer it with M(croit.ceph.task) or in the croit UI.
    type: str
    choices: [redetect, reboot, shutdown]
  confirm_action:
    description:
      - Must be V(true) for O(action=reboot) and O(action=shutdown), which take a storage node offline.
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to make croit forget the server.
    type: bool
    default: false
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Rename a node and note its rack
  croit.ceph.server:
    server: node-07
    hostname: storage-07
    notes: rack B4, U12

- name: Pin a node to a specific image
  croit.ceph.server:
    server: storage-07
    image: "2510.0.squid"

- name: Read a node and show its state
  croit.ceph.server:
    server: storage-07
  register: node

- name: Show the node's state and management IP
  ansible.builtin.debug:
    msg: "{{ node.server.hostname }} is {{ node.server.state }} on {{ node.server.ip }}"

- name: Reboot a node behind ceph's safety check (takes the node offline)
  croit.ceph.server:
    server: storage-07
    action: reboot
    confirm_action: true
    wait_timeout: 3600

- name: Forget a decommissioned node (the node itself is not touched)
  croit.ceph.server:
    server: storage-99
    state: absent
    confirm_delete: true
"""

RETURN = r"""
server:
  description:
    - The server as croit reports it after the change (C(ServerResponse) in the croit API).
    - Before the change in check mode; empty after O(state=absent).
  returned: always
  type: dict
  contains:
    id:
      description: croit's numeric server id.
      returned: when the server exists
      type: int
      sample: 7
    hostname:
      description: Hostname of the server.
      returned: when the server exists
      type: str
      sample: storage-07
    ip:
      description: Management IP croit reaches the node on.
      returned: when the server exists
      type: str
      sample: 10.0.0.17
    ips:
      description: Every IP address the node reports.
      returned: when the server exists
      type: list
      elements: str
      sample: ["10.0.0.17", "10.1.0.17"]
    image:
      description: OS image the server boots, or V(default).
      returned: when the server exists
      type: str
      sample: default
    state:
      description: V(booting), V(running), V(offline), V(rebooting) or V(shutting_down).
      returned: when the server exists
      type: str
      sample: running
    notes:
      description: Free text croit keeps about the server.
      returned: when the server exists
      type: str
      sample: rack B4, U12
    nrHugepages:
      description: Configured number of 2 MiB hugepages.
      returned: when the server exists
      type: int
      sample: 0
    services:
      description: Number of each service type the server carries, keyed by type (C(osd), C(mon), C(rgw), ...).
      returned: when the server exists
      type: dict
      sample: {osd: 12, mon: 1, mgr: 1}
task:
  description: The croit background task of the settings change or of O(action), when there was one (C(TaskResponse) in the croit API).
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
from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_server, list_servers
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule, changed_fields

# Ansible option -> croit API field.
FIELDS = dict(hostname="hostname", ip="ip", image="image", notes="notes", nr_hugepages="nrHugepages")
CONFIRMED_ACTIONS = ("reboot", "shutdown")


def managed_view(server):
    if not server:
        return {}
    view = dict((opt, server.get(api)) for opt, api in FIELDS.items())
    view["notes"] = view["notes"] or ""
    return view


class ServerModule(CroitModule):
    def __init__(self):
        super(ServerModule, self).__init__(
            dict(
                server=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                hostname=dict(type="str"),
                ip=dict(type="str"),
                image=dict(type="str"),
                notes=dict(type="str"),
                nr_hugepages=dict(type="int"),
                action=dict(type="str", choices=["redetect", "reboot", "shutdown"]),
                confirm_action=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
        )

    def find(self):
        p = self.params
        servers = list_servers(self)
        current = find_server(self, p["server"], servers)
        if current is None and p["hostname"]:
            # Already renamed by an earlier run.
            current = find_server(self, p["hostname"], servers)
        return current

    def run(self):
        p = self.params
        current = self.find()

        if p["state"] == "absent":
            return self.absent(current)

        if current is None:
            self.module.fail_json(
                msg="croit does not know server %r. Servers cannot be created through the API; "
                "a node registers itself when it boots from croit." % p["server"]
            )
        if p["action"] in CONFIRMED_ACTIONS and not p["confirm_action"]:
            self.module.fail_json(
                msg="Refusing to %s server %r without confirm_action=true; it takes a storage node offline"
                % (p["action"], current["hostname"])
            )

        desired = dict((api, p[opt]) for opt, api in FIELDS.items())
        if desired["ip"] is not None and desired["ip"] != current.get("ip") and desired["ip"] not in (current.get("ips") or []):
            self.module.fail_json(
                msg="ip %s is not assigned to any interface of %s; known addresses: %s"
                % (desired["ip"], current["hostname"], ", ".join(current.get("ips") or []) or "none")
            )
        normalised = dict(current)
        normalised["notes"] = current.get("notes") or ""
        changes = dict((k, desired[k]) for k in changed_fields(normalised, desired))

        before = managed_view(current)
        after = dict(before)
        for opt, api in FIELDS.items():
            if api in changes:
                after[opt] = changes[api]

        changed = bool(changes) or bool(p["action"])
        result = dict(server=current)
        if self.check_mode or not changed:
            self.exit(changed=changed, before=before, after=after, **result)

        server_path = path_join("servers", current["id"])
        if changes:
            task = self.handle_task(self.write("PATCH", server_path, body=changes))
            if task is not None:
                result["task"] = task
        if p["action"]:
            data = self.write("POST", path_join("servers", current["id"], p["action"]))
            task = self.handle_task(data)
            if task is not None:
                result["task"] = task

        refreshed = find_server(self, current["id"])
        result["server"] = refreshed or current
        self.exit(changed=True, before=before, after=after, **result)

    def absent(self, current):
        if self.params["action"]:
            self.module.fail_json(msg="action cannot be combined with state=absent")
        if current is None:
            self.exit(changed=False, server={})
        if not self.params["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to make croit forget server %r without confirm_delete=true" % current["hostname"]
            )
        if not self.check_mode:
            self.write("DELETE", path_join("servers", current["id"]))
        self.exit(changed=True, before=managed_view(current), after={}, server={})


def main():
    ServerModule().run()


if __name__ == "__main__":
    main()
