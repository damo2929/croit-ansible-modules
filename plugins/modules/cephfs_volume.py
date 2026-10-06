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
  - Create, update and delete CephFS volumes through the croit API.
  - Creating a volume makes its metadata and data pools and turns standby-replay on, as croit does in its UI.
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
  name:
    description:
      - Name of the CephFS volume.
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
      - Number of active MDS ranks.
      - croit warns before this is changed on an existing volume, see O(ignore_warnings).
    type: int
  allow_standby_replay:
    description:
      - Keep a standby-replay MDS daemon for each rank. croit turns this on when it creates a volume.
    type: bool
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to remove an existing volume.
      - It also confirms croit's warning that removing a volume is irreversible, so O(ignore_warnings)
        is not needed for that.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: CephFS volume with two active MDS ranks
  croit.ceph.cephfs_volume:
    api_url: https://croit-mgmt/api
    api_token: "{{ vault_croit_token }}"
    name: projects
    max_mds: 2
    ignore_warnings: true

- name: Remove a volume (its pools stay)
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
  sample:
    name: projects
    id: 2
    maxMds: 2
    allowStandbyReplay: true
    metadataPool: cephfs.projects.meta
    dataPools: [cephfs.projects.data]
    isDefault: false
task:
  description: The last croit background task the change ran as, when there was one.
  returned: when a task ran
  type: dict
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
