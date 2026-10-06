#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/nvmeof
# croit-api: GET /gateways/nvmeof/disks
# croit-api: POST /gateways/nvmeof/disks
# croit-api: PATCH /gateways/nvmeof/disks/{diskId}
# croit-api: DELETE /gateways/nvmeof/disks/{diskId}
# croit-api: GET /gateways/nvmeof/subsystems
# croit-api: POST /gateways/nvmeof/subsystems/{subsystemId}/attach-disks

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nvmeof_disk
short_description: Export RBD images as NVMe-oF disks on a croit cluster
version_added: 0.1.0
description:
  - Exports an existing RBD image through a croit NVMe-oF cluster, grows it, attaches it to subsystems, and
    stops exporting it.
  - The disk is identified by its NVMe-oF cluster, pool and image.
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
      - NVMe-oF cluster that exports the disk, by name or numeric id.
    type: str
    required: true
  pool:
    description:
      - RBD pool of the image to export. Together with O(gateway) and O(image) it identifies the disk.
    type: str
    required: true
  image:
    description:
      - RBD image to export. It must exist; create it with M(croit.ceph.rbd).
    type: str
    required: true
  state:
    description:
      - Whether the image should be exported.
      - V(absent) stops exporting it, which removes the namespace from B(every connected host), and needs
        O(confirm_delete=true). The RBD image is kept unless O(delete_image=true).
    type: str
    choices: [present, absent]
    default: present
  cluster:
    description:
      - Ceph cluster configuration the targets read the image through (see O(croit.ceph.nvmeof_gateway#module:ceph_clusters)).
        croit uses, and creates on first use, its own when not set.
      - Only used when the disk is created; a different value on an existing disk fails.
    type: str
  block_size:
    description:
      - Block size of the namespace in bytes, for example V(512) or V(4096).
      - Only used when the disk is created; a different value on an existing disk fails.
    type: int
  size:
    description:
      - Size of the RBD image, as bytes or with a binary unit such as V(500G). It is rounded up to whole MiB.
      - The image is grown when it is smaller. Shrinking is refused.
    type: str
  subsystems:
    description:
      - NQNs of subsystems of the same NVMe-oF cluster to attach the disk to.
      - Listed subsystems are attached when missing; others are left alone. Detach a disk with
        M(croit.ceph.nvmeof_subsystem) and O(croit.ceph.nvmeof_subsystem#module:exclusive=true).
    type: list
    elements: str
  delete_image:
    description:
      - With O(state=absent), also B(delete the RBD image and all its data).
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to stop exporting an existing disk.
    type: bool
    default: false
seealso:
  - module: croit.ceph.rbd
    description: Create and manage the RBD image before exporting it.
  - module: croit.ceph.nvmeof_subsystem
    description: Attach and detach disks on a subsystem.
  - module: croit.ceph.nvmeof_gateway
    description: Manage the NVMe-oF cluster and its ceph cluster configurations.
  - module: croit.ceph.nvmeof_info
    description: Read the exported disks.
  - name: Ceph NVMe-oF gateway
    description: Upstream documentation of the Ceph NVMe over Fabrics gateway.
    link: https://docs.ceph.com/en/latest/rbd/nvmeof-overview/
  - name: croit API reference
    description: The croit REST API this module talks to.
    link: https://www.croit.io/api-docs
notes:
  - O(state=absent) removes the namespace from B(every connected host), so it needs O(confirm_delete=true) even when
    the RBD image is kept.
  - When a disk is created with O(wait=false), O(size) is applied on a later run.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Export an image to a subsystem
  croit.ceph.nvmeof_disk:
    gateway: nvme-prod
    pool: rbd
    image: ds1-lun0
    block_size: 4096
    subsystems:
      - nqn.2016-06.io.spdk:datastore1
  register: lun0

- name: Show the namespace UUID hosts will see
  ansible.builtin.debug:
    msg: "{{ lun0.disk.namespaceUUID }}"

- name: Grow it
  croit.ceph.nvmeof_disk:
    gateway: nvme-prod
    pool: rbd
    image: ds1-lun0
    size: 4T

- name: Stop exporting it, keep the image
  croit.ceph.nvmeof_disk:
    gateway: nvme-prod
    pool: rbd
    image: ds1-lun0
    state: absent
    confirm_delete: true

- name: Stop exporting it and delete the image with all its data
  croit.ceph.nvmeof_disk:
    gateway: nvme-prod
    pool: rbd
    image: scratch-lun
    state: absent
    delete_image: true
    confirm_delete: true
"""

RETURN = r"""
disk:
  description:
    - The exported disk as croit reports it after the change (C(NvmeOFDiskResponse) in the croit API).
    - Before the change in check mode; empty when it is not exported.
  returned: always
  type: dict
  contains:
    id:
      description: croit id of the disk.
      returned: when the disk is exported
      type: int
      sample: 7
    gatewayId:
      description: croit id of the NVMe-oF cluster.
      returned: when the disk is exported
      type: int
      sample: 1
    pool:
      description: RBD pool of the image.
      returned: when the disk is exported
      type: str
      sample: rbd
    image:
      description: RBD image name.
      returned: when the disk is exported
      type: str
      sample: ds1-lun0
    cluster:
      description: Ceph cluster configuration the targets read the image through.
      returned: when the disk is exported
      type: str
      sample: croit
    blockSize:
      description: Block size of the namespace in bytes.
      returned: when the disk is exported
      type: int
      sample: 4096
    size:
      description: Size of the disk in bytes, null when croit could not read it.
      returned: when the disk is exported
      type: int
      sample: 4398046511104
    subsystemNqns:
      description: NQNs of the subsystems the disk is attached to.
      returned: when the disk is exported
      type: list
      elements: str
      sample: [nqn.2016-06.io.spdk:datastore1]
    hosts:
      description: croit ids of the hosts attached to the same subsystems as the disk.
      returned: when the disk is exported
      type: list
      elements: int
      sample: [3]
    namespaceUUID:
      description: NVMe UUID hosts see for the namespace.
      returned: when the disk is exported
      type: str
      sample: 5b1f6a3e-2c4d-4e8f-9a0b-1c2d3e4f5a6b
    lockState:
      description:
        - Who holds the RBD exclusive lock of the image, one of C(UNKNOWN), C(UNLOCKED), C(HELD_BY_OWNER),
          C(HELD_BY_STANDBY) or C(HELD_ELSEWHERE).
      returned: when the disk is exported
      type: str
      sample: HELD_BY_OWNER
image_deleted:
  description: Whether the RBD image was (or, in check mode, would be) deleted along with the export.
  returned: when O(state=absent) removed an export
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
      sample: Add NVMe-oF disk
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
      name: Add NVMe-oF disk
      state: FINISHED
      done: true
      output: ""
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.nvmeof import require_gateway
from ansible_collections.croit.ceph.plugins.module_utils.module import ceil_mib, CroitModule, parse_size


def view(disk):
    if not disk:
        return {}
    return dict(
        pool=disk.get("pool"),
        image=disk.get("image"),
        cluster=disk.get("cluster"),
        block_size=disk.get("blockSize"),
        size=disk.get("size"),
        subsystems=sorted(disk.get("subsystemNqns") or []),
    )


class NvmeofDiskModule(CroitModule):
    def __init__(self):
        super(NvmeofDiskModule, self).__init__(
            dict(
                gateway=dict(type="str", required=True),
                pool=dict(type="str", required=True),
                image=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                cluster=dict(type="str"),
                block_size=dict(type="int"),
                size=dict(type="str"),
                subsystems=dict(type="list", elements="str"),
                delete_image=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
        )
        self.tasks = []

    def run_write(self, method, path, body=None):
        task = self.handle_task(self.write(method, path, body=body))
        if task is not None:
            self.tasks.append(task)

    def find_disk(self):
        p = self.params
        matches = [
            d
            for d in self.get_list("/gateways/nvmeof/disks")
            if d.get("gatewayId") == self.gateway["gatewayId"] and d.get("pool") == p["pool"] and d.get("image") == p["image"]
        ]
        if len(matches) > 1:
            self.module.fail_json(msg="Image %s/%s is exported %d times by this NVMe-oF cluster" % (p["pool"], p["image"], len(matches)))
        return matches[0] if matches else None

    def resolve_subsystems(self):
        wanted = self.params["subsystems"]
        if wanted is None:
            return None
        subs = [s for s in self.get_list("/gateways/nvmeof/subsystems") if s.get("gatewayId") == self.gateway["gatewayId"]]
        resolved = {}
        for nqn in wanted:
            match = next((s for s in subs if s.get("nqn") == nqn), None)
            if match is None:
                self.module.fail_json(
                    msg="NVMe-oF cluster %r has no subsystem %r. Subsystems: %s"
                    % (self.gateway["name"], nqn, ", ".join(s.get("nqn") for s in subs) or "none")
                )
            resolved[nqn] = match["id"]
        return resolved

    def desired_size(self):
        try:
            size = parse_size(self.params["size"])
        except ValueError as e:
            self.module.fail_json(msg="size: %s" % e)
        return ceil_mib(size) if size is not None else None

    def finish(self, before, after):
        result = dict(changed=True, before=before, after=after, disk=self.find_disk() or {})
        if self.tasks:
            result["task"] = self.tasks[-1]
            result["tasks"] = self.tasks
        self.exit(**result)

    def run(self):
        p = self.params
        self.gateway = require_gateway(self, p["gateway"])
        current = self.find_disk()
        if p["state"] == "absent":
            return self.absent(current)

        subsystems = self.resolve_subsystems()
        size = self.desired_size()
        if current is None:
            return self.create(subsystems, size)

        for opt, api in (("cluster", "cluster"), ("block_size", "blockSize")):
            if p[opt] is not None and p[opt] != current.get(api):
                self.module.fail_json(
                    msg="%s of the exported disk %s/%s is %r and cannot be changed to %r; stop exporting it and export it again"
                    % (opt, p["pool"], p["image"], current.get(api), p[opt])
                )

        before = view(current)
        after = dict(before)
        resize = None
        if size is not None:
            if current.get("size") is None:
                self.module.fail_json(
                    msg="croit cannot read the size of %s/%s: %s"
                    % (p["pool"], p["image"], "; ".join(h.get("message", "") for h in current.get("hints") or []) or "no reason given")
                )
            if size < current["size"]:
                self.module.fail_json(msg="Cannot shrink %s/%s from %d to %d bytes" % (p["pool"], p["image"], current["size"], size))
            if size > current["size"]:
                resize = size
                after["size"] = size
        attach = []
        if subsystems is not None:
            have = set(current.get("subsystemNqns") or [])
            attach = sorted(nqn for nqn in subsystems if nqn not in have)
            after["subsystems"] = sorted(have | set(attach))

        if resize is None and not attach:
            self.exit(changed=False, before=before, after=after, disk=current)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, disk=current)
        if resize is not None:
            self.run_write("PATCH", path_join("gateways", "nvmeof", "disks", current["id"]), body=dict(size=resize))
        for nqn in attach:
            self.run_write(
                "POST", path_join("gateways", "nvmeof", "subsystems", subsystems[nqn], "attach-disks"), body=dict(disks=[current["id"]])
            )
        self.finish(before, after)

    def create(self, subsystems, size):
        p = self.params
        body = dict(gatewayId=self.gateway["gatewayId"], type="CEPH", pool=p["pool"], image=p["image"])
        if p["cluster"] is not None:
            body["cluster"] = p["cluster"]
        if p["block_size"] is not None:
            body["blockSize"] = p["block_size"]
        if subsystems:
            body["subsystems"] = sorted(subsystems.values())
        after = dict(
            pool=p["pool"],
            image=p["image"],
            cluster=p["cluster"],
            block_size=p["block_size"],
            size=size,
            subsystems=sorted(subsystems or []),
        )
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, disk={})
        self.run_write("POST", "/gateways/nvmeof/disks", body=body)
        if size is not None:
            if not p["wait"]:
                self.module.warn("size of the new disk is applied on the next run, because wait=false")
                self.finish({}, after)
            created = self.find_disk()
            if created is not None and created.get("size") is not None:
                if size < created["size"]:
                    self.module.fail_json(
                        msg="Exported %s/%s, but the image is %d bytes and cannot shrink to %d" % (p["pool"], p["image"], created["size"], size),
                        disk=created,
                    )
                if size > created["size"]:
                    self.run_write("PATCH", path_join("gateways", "nvmeof", "disks", created["id"]), body=dict(size=size))
        self.finish({}, after)

    def absent(self, current):
        p = self.params
        if current is None:
            self.exit(changed=False, disk={})
        if not p["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to stop exporting %s/%s without confirm_delete=true; it removes the namespace from every "
                "connected host" % (p["pool"], p["image"])
            )
        before = view(current)
        if not self.check_mode:
            self.run_write("DELETE", path_join("gateways", "nvmeof", "disks", current["id"]), body=dict(deleteData=p["delete_image"]))
        result = dict(changed=True, before=before, after={}, disk={}, image_deleted=p["delete_image"])
        if self.tasks:
            result["task"] = self.tasks[-1]
            result["tasks"] = self.tasks
        self.exit(**result)


def main():
    NvmeofDiskModule().run()


if __name__ == "__main__":
    main()
