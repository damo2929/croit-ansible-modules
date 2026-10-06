#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/nvmeof
# croit-api: GET /gateways/nvmeof/hosts
# croit-api: POST /gateways/nvmeof/hosts
# croit-api: PUT /gateways/nvmeof/hosts/{hostId}
# croit-api: DELETE /gateways/nvmeof/hosts/{hostId}
# croit-api: GET /gateways/nvmeof/subsystems
# croit-api: POST /gateways/nvmeof/subsystems/{subsystemId}/attach-hosts

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nvmeof_host
short_description: Manage the hosts (initiators) allowed onto a croit NVMe-oF cluster
version_added: 0.1.0
description:
  - Allows an NVMe-oF initiator, identified by its host NQN, onto a croit NVMe-oF cluster, sets the key it
    authenticates with, attaches it to subsystems, and revokes its access.
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
      - NVMe-oF cluster the host is allowed onto, by name or numeric id.
    type: str
    required: true
  nqn:
    description:
      - Host NQN of the initiator, unique within the NVMe-oF cluster.
    type: str
    required: true
  state:
    description:
      - Whether the host should be allowed onto the cluster.
      - V(absent) revokes the host's access to every subsystem of the cluster. Only this host is affected, so
        no confirmation is needed.
    type: str
    choices: [present, absent]
    default: present
  shared_key:
    description:
      - DH-HMAC-CHAP shared key the host authenticates with, for example V(DHHC-1:00:...).
      - V("") removes the key, so the host connects without authenticating.
      - With an admin token croit returns the stored key and it is compared directly. Otherwise croit only
        says whether a key is set, and O(update_shared_key) decides.
    type: str
  update_shared_key:
    description:
      - When croit does not reveal the stored key, V(on_create) only sets O(shared_key) when the host has no
        key yet, and V(always) sets it on every run (always reporting a change).
    type: str
    choices: [on_create, always]
    default: on_create
  subsystems:
    description:
      - NQNs of subsystems of the same NVMe-oF cluster to attach the host to.
      - Listed subsystems are attached when missing; others are left alone. Detach a host with
        M(croit.ceph.nvmeof_subsystem) and O(croit.ceph.nvmeof_subsystem#module:exclusive=true).
    type: list
    elements: str
seealso:
  - module: croit.ceph.nvmeof_subsystem
    description: Attach and detach hosts on a subsystem.
  - module: croit.ceph.nvmeof_gateway
    description: Manage the NVMe-oF cluster.
  - module: croit.ceph.nvmeof_info
    description: Read the allowed hosts.
  - name: Ceph NVMe-oF gateway
    description: Upstream documentation of the Ceph NVMe over Fabrics gateway.
    link: https://docs.ceph.com/en/latest/rbd/nvmeof-overview/
  - name: croit API reference
    description: The croit REST API this module talks to.
    link: https://www.croit.io/api-docs
notes:
  - The shared key is never returned. RV(host.sharedKey) is replaced by C(********), and the key never appears in
    the diff.
  - Revoking a host affects only that initiator, so O(state=absent) needs no confirmation.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Allow an ESXi host with a key
  croit.ceph.nvmeof_host:
    gateway: nvme-prod
    nqn: nqn.2014-08.org.nvmexpress:uuid:esxi-01
    shared_key: "{{ vault_esxi01_dhchap_key }}"
    subsystems:
      - nqn.2016-06.io.spdk:datastore1
  register: esxi01

- name: Confirm the host authenticates with a key
  ansible.builtin.assert:
    that: esxi01.host.hasSharedKey

- name: Rotate the key
  croit.ceph.nvmeof_host:
    gateway: nvme-prod
    nqn: nqn.2014-08.org.nvmexpress:uuid:esxi-01
    shared_key: "{{ vault_esxi01_new_key }}"
    update_shared_key: always

- name: Revoke access
  croit.ceph.nvmeof_host:
    gateway: nvme-prod
    nqn: nqn.2014-08.org.nvmexpress:uuid:esxi-02
    state: absent
"""

RETURN = r"""
host:
  description:
    - The host as croit reports it after the change (C(NvmeOFHostResponse) in the croit API), with the shared key
      replaced by C(********).
    - Before the change in check mode; empty when the host is not allowed.
  returned: always
  type: dict
  contains:
    id:
      description: croit id of the host.
      returned: when the host is allowed
      type: int
      sample: 3
    gatewayId:
      description: croit id of the NVMe-oF cluster.
      returned: when the host is allowed
      type: int
      sample: 1
    nqn:
      description: Host NQN of the initiator.
      returned: when the host is allowed
      type: str
      sample: nqn.2014-08.org.nvmexpress:uuid:esxi-01
    hasSharedKey:
      description: Whether the host has a DH-HMAC-CHAP key.
      returned: when the host is allowed
      type: bool
      sample: true
    sharedKey:
      description: Always C(********) when a key is set.
      returned: when the host is allowed
      type: str
      sample: "********"
    subsystems:
      description: croit ids of the subsystems the host is attached to.
      returned: when the host is allowed
      type: list
      elements: int
      sample: [4]
    disks:
      description: croit ids of the disks attached to the same subsystems.
      returned: when the host is allowed
      type: list
      elements: int
      sample: [7, 8]
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
      sample: Add NVMe-oF host
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
tasks:
  description:
    - Every croit background task the change ran as, in the order they ran. Each entry has the same fields as
      RV(task).
  returned: when the change ran as one or more croit background tasks
  type: list
  elements: dict
  sample:
    - id: 412
      name: Add NVMe-oF host
      state: FINISHED
      done: true
      output: ""
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.nvmeof import require_gateway
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

MASK = "********"
CROIT_MASK = "(masked)"


def has_key(host):
    return bool(host.get("hasSharedKey") or host.get("sharedKey"))


def masked(host):
    """The host with its shared key hidden."""
    if not host:
        return {}
    result = dict(host)
    if result.get("sharedKey"):
        result["sharedKey"] = MASK
    return result


class NvmeofHostModule(CroitModule):
    def __init__(self):
        super(NvmeofHostModule, self).__init__(
            dict(
                gateway=dict(type="str", required=True),
                nqn=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                shared_key=dict(type="str", no_log=True),
                update_shared_key=dict(type="str", default="on_create", choices=["on_create", "always"]),
                subsystems=dict(type="list", elements="str"),
            ),
        )
        self.tasks = []

    def run_write(self, method, path, body=None):
        task = self.handle_task(self.write(method, path, body=body))
        if task is not None:
            self.tasks.append(task)

    def find_host(self):
        return next(
            (
                h
                for h in self.get_list("/gateways/nvmeof/hosts")
                if h.get("gatewayId") == self.gateway["gatewayId"] and h.get("nqn") == self.params["nqn"]
            ),
            None,
        )

    def resolve_subsystems(self):
        wanted = self.params["subsystems"]
        if wanted is None:
            return {}, {}
        subs = [s for s in self.get_list("/gateways/nvmeof/subsystems") if s.get("gatewayId") == self.gateway["gatewayId"]]
        by_nqn = {}
        for nqn in wanted:
            match = next((s for s in subs if s.get("nqn") == nqn), None)
            if match is None:
                self.module.fail_json(
                    msg="NVMe-oF cluster %r has no subsystem %r. Subsystems: %s"
                    % (self.gateway["name"], nqn, ", ".join(s.get("nqn") for s in subs) or "none")
                )
            by_nqn[nqn] = match["id"]
        return by_nqn, dict((s["id"], s.get("nqn")) for s in subs)

    def key_change(self, current):
        """Whether the shared key must be written, and the masked value to show in the diff."""
        wanted = self.params["shared_key"]
        if wanted is None:
            return False
        stored = current.get("sharedKey") if current else None
        if wanted == "":
            return bool(current and has_key(current))
        if current is None or not has_key(current):
            return True
        if stored and stored not in (CROIT_MASK, MASK):
            return stored != wanted
        return self.params["update_shared_key"] == "always"

    def finish(self, before, after):
        result = dict(changed=True, before=before, after=after, host=masked(self.find_host()))
        if self.tasks:
            result["task"] = self.tasks[-1]
            result["tasks"] = self.tasks
        self.exit(**result)

    def run(self):
        p = self.params
        self.gateway = require_gateway(self, p["gateway"])
        current = self.find_host()

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, host={})
            before = dict(nqn=current["nqn"], shared_key=MASK if has_key(current) else None)
            if not self.check_mode:
                self.run_write("DELETE", path_join("gateways", "nvmeof", "hosts", current["id"]))
            result = dict(changed=True, before=before, after={}, host={})
            if self.tasks:
                result["task"] = self.tasks[-1]
                result["tasks"] = self.tasks
            self.exit(**result)

        by_nqn, names = self.resolve_subsystems()
        write_key = self.key_change(current)
        new_key_view = None if p["shared_key"] in (None, "") else MASK + " (changed)"

        if current is None:
            after = dict(nqn=p["nqn"], shared_key=new_key_view, subsystems=sorted(by_nqn))
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, host={})
            body = dict(gatewayId=self.gateway["gatewayId"], nqn=p["nqn"])
            if p["shared_key"]:
                body["sharedKey"] = p["shared_key"]
            if by_nqn:
                body["subsystems"] = sorted(by_nqn.values())
            self.run_write("POST", "/gateways/nvmeof/hosts", body=body)
            self.finish({}, after)

        current_subs = sorted(names.get(i, str(i)) for i in current.get("subsystems") or [])
        before = dict(nqn=current["nqn"], shared_key=MASK if has_key(current) else None, subsystems=current_subs)
        after = dict(before)
        if write_key:
            after["shared_key"] = new_key_view
        attach = sorted(nqn for nqn in by_nqn if by_nqn[nqn] not in (current.get("subsystems") or []))
        after["subsystems"] = sorted(set(current_subs) | set(attach))
        if p["subsystems"] is None:
            before.pop("subsystems")
            after.pop("subsystems")

        if not write_key and not attach:
            self.exit(changed=False, before=before, after=after, host=masked(current))
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, host=masked(current))
        if write_key:
            body = dict(sharedKey=p["shared_key"]) if p["shared_key"] else {}
            self.run_write("PUT", path_join("gateways", "nvmeof", "hosts", current["id"]), body=body)
        for nqn in attach:
            self.run_write(
                "POST", path_join("gateways", "nvmeof", "subsystems", by_nqn[nqn], "attach-hosts"), body=dict(hosts=[current["id"]])
            )
        self.finish(before, after)


def main():
    NvmeofHostModule().run()


if __name__ == "__main__":
    main()
