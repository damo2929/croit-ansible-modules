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
"""

EXAMPLES = r"""
- name: Allow an ESXi host with a key
  croit.ceph.nvmeof_host:
    gateway: nvme-prod
    nqn: nqn.2014-08.org.nvmexpress:uuid:esxi-01
    shared_key: "{{ vault_esxi01_dhchap_key }}"
    subsystems:
      - nqn.2016-06.io.spdk:datastore1

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
    - The host as croit reports it after the change (C(NvmeOFHostResponse)), with the shared key replaced by
      C(********).
    - Before the change in check mode; empty when the host is not allowed.
  returned: always
  type: dict
  sample:
    id: 3
    gatewayId: 1
    nqn: nqn.2014-08.org.nvmexpress:uuid:esxi-01
    hasSharedKey: true
    sharedKey: "********"
    subsystems: [4]
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
