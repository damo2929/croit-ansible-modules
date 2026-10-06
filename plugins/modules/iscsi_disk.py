#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/iscsi
# croit-api: GET /services/iscsi/{serviceId}
# croit-api: PATCH /services/iscsi/{serviceId}/disks/{wwn}
# croit-api: DELETE /services/iscsi/{serviceId}/disks/{wwn}
# croit-api: GET /pools/{pool}/rbds/{rbd}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: iscsi_disk
short_description: Manage disks exported by the croit iSCSI gateway
version_added: 0.1.0
description:
  - Grows, unexports and optionally deletes an RBD image the cluster's iSCSI target exports.
  - The croit API exports a disk only by mapping it, so a disk is exported with M(croit.ceph.iscsi_client)
    or M(croit.ceph.iscsi_group). If O(state=present) is set for a disk that is not exported, the task fails
    and says so.
  - O(state=absent) only stops the export, and the RBD image is kept. The image is only deleted with
    O(delete_image=true) and O(confirm_delete=true).
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
  pool:
    description:
      - RBD pool of the disk. Required together with O(image) unless O(wwn) is set, and mutually exclusive
        with O(wwn).
    type: str
  image:
    description:
      - RBD image name of the disk. Required together with O(pool) unless O(wwn) is set, and mutually
        exclusive with O(wwn).
    type: str
  wwn:
    description:
      - WWN of the exported disk, instead of O(pool) and O(image). It is compared case-insensitively.
    type: str
  state:
    description:
      - V(present) makes sure the exported disk has O(size).
      - V(absent) stops exporting the disk, which B(disconnects it from every initiator that maps it).
    type: str
    choices: [present, absent]
    default: present
  size:
    description:
      - Size of the image, as bytes or with a binary unit such as V(500G). The size is rounded up to whole MiB.
      - ceph-iscsi only grows images, so a smaller size fails.
    type: str
  delete_image:
    description:
      - With O(state=absent), also B(delete the RBD image and all its data). Needs O(confirm_delete=true).
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) together with O(delete_image=true). Only stopping the export does not need it.
    type: bool
    default: false
  service_id:
    description:
      - croit service id of the iSCSI gateway. Only needed if croit reports more than one.
    type: int
seealso:
  - module: croit.ceph.iscsi_client
    description: Export a disk by mapping it to an initiator.
  - module: croit.ceph.iscsi_group
    description: Export a disk by mapping it to a host group.
  - module: croit.ceph.iscsi_info
    description: List the exported disks and who uses them.
  - module: croit.ceph.rbd
    description: Manage the RBD images behind the exported disks.
  - name: Ceph iSCSI gateway
    description: Upstream documentation of the Ceph iSCSI gateway.
    link: https://docs.ceph.com/en/latest/rbd/iscsi-overview/
  - name: croit API reference
    description: The croit REST API this module talks to.
    link: https://www.croit.io/api-docs
notes:
  - Stopping an export disconnects the disk from every initiator and host group that maps it.
  - The size is compared with the RBD image size croit reports for the image.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Grow an exported disk
  croit.ceph.iscsi_disk:
    pool: iscsi
    image: datastore1
    size: 4T
  register: grown

- name: Check the new size
  ansible.builtin.assert:
    that: grown.disk.size >= 4398046511104

- name: Preview stopping an export
  croit.ceph.iscsi_disk:
    pool: iscsi
    image: old-datastore
    state: absent
  check_mode: true

- name: Stop exporting a disk, keeping the image
  croit.ceph.iscsi_disk:
    pool: iscsi
    image: old-datastore
    state: absent

- name: Stop exporting a disk and delete the image with all its data
  croit.ceph.iscsi_disk:
    wwn: 3f0e8c7a-0c1d-4a5e-9b6f-2d3c4b5a6f70
    state: absent
    delete_image: true
    confirm_delete: true
"""

RETURN = r"""
disk:
  description:
    - The exported disk (C(IscsiClientLun) in the croit API) and its C(size) after the change.
    - Empty when the disk is not exported. Shows the state before the change in check mode.
  returned: always
  type: dict
  contains:
    pool:
      description: RBD pool of the disk.
      returned: when the disk is exported
      type: str
      sample: iscsi
    image:
      description: RBD image name of the disk.
      returned: when the disk is exported
      type: str
      sample: datastore1
    wwn:
      description: WWN of the disk on the target.
      returned: when the disk is exported
      type: str
      sample: 3f0e8c7a-0c1d-4a5e-9b6f-2d3c4b5a6f70
    size:
      description: Size of the RBD image in bytes, as croit reports it.
      returned: when the disk is exported
      type: int
      sample: 4398046511104
task:
  description:
    - The last croit background task the change ran as (C(ManagedTask) in the croit API).
    - With O(wait=true) this is the task's final state. With O(wait=false) it may still be running; follow it
      with M(croit.ceph.task).
  returned: when O(state=absent) stopped an export and croit ran it as a background task
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
      sample: Delete iSCSI disk
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
from ansible_collections.croit.ceph.plugins.module_utils.iscsi import require_service
from ansible_collections.croit.ceph.plugins.module_utils.module import MIB, ceil_mib, CroitModule, parse_size


class IscsiDiskModule(CroitModule):
    def __init__(self):
        super(IscsiDiskModule, self).__init__(
            dict(
                pool=dict(type="str"),
                image=dict(type="str"),
                wwn=dict(type="str"),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                size=dict(type="str"),
                delete_image=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
                service_id=dict(type="int"),
            ),
            required_one_of=[("wwn", "image")],
            required_together=[("pool", "image")],
            mutually_exclusive=[("wwn", "image")],
        )

    def find_disk(self, config):
        p = self.params
        for disk in config.get("disks") or []:
            if p["wwn"] is not None:
                if (disk.get("wwn") or "").lower() == p["wwn"].lower():
                    return disk
            elif disk.get("pool") == p["pool"] and disk.get("image") == p["image"]:
                return disk
        return None

    def label(self):
        p = self.params
        return p["wwn"] if p["wwn"] is not None else "%s/%s" % (p["pool"], p["image"])

    def image_size(self, disk):
        image = self.get_or_none(path_join("pools", disk["pool"], "rbds", disk["image"])) or {}
        return image.get("size")

    def view(self, disk, size):
        if not disk:
            return {}
        return dict(pool=disk.get("pool"), image=disk.get("image"), wwn=disk.get("wwn"), size=size)

    def run(self):
        p = self.params
        desired_size = None
        if p["size"] is not None:
            try:
                desired_size = ceil_mib(parse_size(p["size"]))
            except ValueError as e:
                self.module.fail_json(msg="size: %s" % e)
            if desired_size == 0:
                self.module.fail_json(msg="size must be greater than 0")
        if p["state"] == "present" and p["delete_image"]:
            self.module.fail_json(msg="delete_image only applies to state=absent")

        service = require_service(self, p["service_id"])
        sid = service["serviceId"]
        config = self.get(path_join("services", "iscsi", sid)) or {}
        disk = self.find_disk(config)

        if p["state"] == "absent":
            return self.absent(sid, disk)

        if disk is None:
            self.module.fail_json(
                msg="Disk %s is not exported by the iSCSI target. Export it by mapping it with "
                "croit.ceph.iscsi_client or croit.ceph.iscsi_group." % self.label()
            )
        size = self.image_size(disk)
        before = self.view(disk, size)
        after = dict(before)
        changed = False
        if desired_size is not None:
            if size is None or size < 0:
                self.module.fail_json(msg="croit could not report the size of %s/%s" % (disk["pool"], disk["image"]))
            if desired_size < size:
                self.module.fail_json(
                    msg="Disk %s/%s is %d bytes; ceph-iscsi cannot shrink it to %d bytes"
                    % (disk["pool"], disk["image"], size, desired_size)
                )
            if desired_size > size:
                changed = True
                after["size"] = desired_size

        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, disk=before)
        self.write(
            "PATCH", path_join("services", "iscsi", sid, "disks", disk["wwn"]), body=dict(size=desired_size // MIB)
        )
        self.exit(changed=True, before=before, after=after, disk=self.view(disk, self.image_size(disk)))

    def absent(self, sid, disk):
        p = self.params
        if disk is None:
            self.exit(changed=False, disk={})
        if p["delete_image"] and not p["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to delete RBD image %s/%s and all its data without confirm_delete=true"
                % (disk["pool"], disk["image"])
            )
        before = self.view(disk, self.image_size(disk))
        result = dict(changed=True, before=before, after={}, disk={})
        if not self.check_mode:
            task = self.handle_task(
                self.write(
                    "DELETE",
                    path_join("services", "iscsi", sid, "disks", disk["wwn"]),
                    body=dict(pool=disk["pool"], image=disk["image"], deleteData=bool(p["delete_image"])),
                )
            )
            if task is not None:
                result["task"] = task
        self.exit(**result)


def main():
    IscsiDiskModule().run()


if __name__ == "__main__":
    main()
