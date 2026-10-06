#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /cephfs/volumes
# croit-api: POST /cephfs/volumes/{name}
# croit-api: PATCH /cephfs/volumes/{name}
# croit-api: DELETE /cephfs/volumes/{name}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: cephfs_volume
short_description: Manage CephFS volumes (filesystems) on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete CephFS volumes (filesystems) through the croit API. A volume is
    identified by its O(name).
  - Creating a volume makes its metadata and data pools and turns standby-replay on, as croit does in
    its UI. Settings that differ from croit's defaults are applied right after the volume is created.
  - Only options that are set are managed; anything left out keeps its current value.
  - Removing a volume needs O(confirm_delete=true). Its pools, and the data in them, are left in place.
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
      - Name of the CephFS volume. Creating a volume also creates its pools, named after it.
    type: str
    required: true
  state:
    description:
      - Whether the volume should exist.
      - V(absent) removes the filesystem and needs O(confirm_delete=true). Its pools, and the data in them,
        are left in place; remove them with M(croit.ceph.pool).
      - croit refuses to remove the cluster's default filesystem and the one croit itself uses.
    type: str
    choices: [present, absent]
    default: present
  max_mds:
    description:
      - Number of active MDS ranks. Must be at least V(1).
      - croit warns before this is changed on an existing volume; see O(ignore_warnings).
      - When not set, the current number of ranks is kept, and croit's default is used for a new volume.
    type: int
  allow_standby_replay:
    description:
      - Keep a standby-replay MDS daemon for each active rank, for faster failover.
      - croit turns this on when it creates a volume. When not set, the current setting is kept.
    type: bool
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to remove an existing volume. Without it the task fails,
        in check mode too.
      - It also confirms croit's warning that removing a volume is irreversible, so O(ignore_warnings)
        is not needed for that.
    type: bool
    default: false
notes:
  - When a volume is created with O(wait=false), O(max_mds) and O(allow_standby_replay) are not applied
    in the same run if they differ from croit's defaults; a later run applies them.
  - Removing a volume disconnects every client that has it mounted.
seealso:
  - module: croit.ceph.cephfs_subvolume_group
    description: Manage subvolume groups inside a volume.
  - module: croit.ceph.cephfs_subvolume
    description: Manage subvolumes inside a volume.
  - module: croit.ceph.cephfs_quota
    description: Set quotas and data layouts on CephFS directories.
  - module: croit.ceph.service
    description: Add the MDS daemons a volume needs.
  - module: croit.ceph.pool
    description: Remove the pools a deleted volume leaves behind.
  - name: croit API reference
    description: The croit REST API, including the C(/cephfs/volumes) endpoints.
    link: https://www.croit.io/api-docs
  - name: CephFS
    description: Upstream CephFS documentation.
    link: https://docs.ceph.com/en/latest/cephfs/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: CephFS volume with two active MDS ranks
  croit.ceph.cephfs_volume:
    name: projects
    max_mds: 2
    ignore_warnings: true
  register: projects

- name: Show the pools croit created for it
  ansible.builtin.debug:
    msg: "metadata {{ projects.volume.metadataPool }}, data {{ projects.volume.dataPools | join(', ') }}"

- name: Turn standby-replay off
  croit.ceph.cephfs_volume:
    name: projects
    allow_standby_replay: false

- name: Remove a volume (its pools and their data stay)
  croit.ceph.cephfs_volume:
    name: scratch
    state: absent
    confirm_delete: true
"""

RETURN = r"""
volume:
  description:
    - The volume as croit reports it after the change (C(CephFilesystemResponse) in the croit API).
    - Before the change in check mode; empty when the volume does not exist.
  returned: always
  type: dict
  contains:
    name:
      description: Name of the volume.
      returned: when the volume exists
      type: str
      sample: projects
    id:
      description: Id of the filesystem in ceph.
      returned: when the volume exists
      type: int
      sample: 2
    maxMds:
      description: Number of active MDS ranks.
      returned: when the volume exists
      type: int
      sample: 2
    allowStandbyReplay:
      description: Whether standby-replay is enabled.
      returned: when the volume exists
      type: bool
      sample: true
    metadataPool:
      description: Name of the metadata pool.
      returned: when the volume exists
      type: str
      sample: cephfs.projects.meta
    dataPools:
      description: Names of the data pools.
      returned: when the volume exists
      type: list
      elements: str
      sample: [cephfs.projects.data]
    isDefault:
      description: Whether this is the cluster's default filesystem.
      returned: when the volume exists
      type: bool
      sample: false
task:
  description: The last croit background task the change ran as.
  returned: when a task ran
  type: dict
  contains:
    id:
      description: The task's id; use it with M(croit.ceph.task) or M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as croit's task list shows it.
      returned: always
      type: str
      sample: Create CephFS volume
    state:
      description: The task's state, one of C(WAITING), C(RUNNING), C(FINISHED), C(FAILED) or C(CANCELED).
      returned: always
      type: str
      sample: FINISHED
    done:
      description: Whether the task has ended.
      returned: always
      type: bool
      sample: true
    output:
      description: The task's transcript. Empty while the task is listed without it.
      returned: always
      type: str
      sample: Creating pools...
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule, changed_fields

# Ansible option -> croit API field.
FIELDS = dict(max_mds="maxMds", allow_standby_replay="allowStandbyReplay")


def managed_view(volume):
    if not volume:
        return {}
    return dict((opt, volume.get(api)) for opt, api in FIELDS.items())


class CephfsVolumeModule(CroitModule):
    def __init__(self):
        super(CephfsVolumeModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                max_mds=dict(type="int"),
                allow_standby_replay=dict(type="bool"),
                confirm_delete=dict(type="bool", default=False),
            ),
        )

    def find_volume(self, name):
        for volume in self.get_list("/cephfs/volumes"):
            if volume.get("name") == name:
                return volume
        return None

    def desired(self):
        return dict((api, self.params[opt]) for opt, api in FIELDS.items())

    def run(self):
        p = self.params
        if p["max_mds"] is not None and p["max_mds"] < 1:
            self.module.fail_json(msg="max_mds must be at least 1")
        current = self.find_volume(p["name"])
        if p["state"] == "absent":
            return self.absent(current)
        if current is None:
            return self.create()
        return self.update(current)

    def absent(self, current):
        if current is None:
            self.exit(changed=False, volume={})
        if not self.params["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to remove CephFS volume %r without confirm_delete=true" % self.params["name"]
            )
        result = dict(changed=True, before=managed_view(current), after={}, volume={})
        if not self.check_mode:
            task = self.handle_task(self.write("DELETE", path_join("cephfs", "volumes", self.params["name"]), confirm_warnings=True))
            if task is not None:
                result["task"] = task
        self.exit(**result)

    def create(self):
        name = self.params["name"]
        desired = self.desired()
        after = dict((opt, desired[api]) for opt, api in FIELDS.items())
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, volume={})

        result = dict(changed=True, before={}, after=after)
        task = self.handle_task(self.write("POST", path_join("cephfs", "volumes", name)))
        if task is not None:
            result["task"] = task
        volume = self.find_volume(name)
        if volume is not None and self.params["wait"]:
            # croit creates the volume with its own defaults; apply the rest.
            changes = dict((k, desired[k]) for k in changed_fields(volume, desired))
            if changes:
                task = self.handle_task(self.write("PATCH", path_join("cephfs", "volumes", name), body=changes))
                if task is not None:
                    result["task"] = task
                volume = self.find_volume(name)
        result["volume"] = volume or {}
        self.exit(**result)

    def update(self, current):
        name = self.params["name"]
        desired = self.desired()
        changes = dict((k, desired[k]) for k in changed_fields(current, desired))
        before = managed_view(current)
        after = dict(before)
        for opt, api in FIELDS.items():
            if api in changes:
                after[opt] = changes[api]
        if not changes:
            self.exit(changed=False, before=before, after=after, volume=current)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, volume=current)

        result = dict(changed=True, before=before, after=after)
        task = self.handle_task(self.write("PATCH", path_join("cephfs", "volumes", name), body=changes))
        if task is not None:
            result["task"] = task
        result["volume"] = self.find_volume(name) or {}
        self.exit(**result)


def main():
    CephfsVolumeModule().run()


if __name__ == "__main__":
    main()
