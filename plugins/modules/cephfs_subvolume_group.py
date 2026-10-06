#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /cephfs/subvolume-groups
# croit-api: GET /cephfs/subvolume-groups/{groupName}
# croit-api: POST /cephfs/subvolume-groups/{groupName}
# croit-api: POST /cephfs/subvolume-groups/{groupName}/resize
# croit-api: DELETE /cephfs/subvolume-groups/{groupName}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: cephfs_subvolume_group
short_description: Manage CephFS subvolume groups on a croit cluster
version_added: 0.1.0
description:
  - Create, resize and delete CephFS subvolume groups through the croit API.
  - Only options that are set are managed; anything left out keeps its current value.
  - O(uid), O(gid), O(mode) and O(pool_layout) can only be set when the group is created. They are compared
    afterwards, and a difference fails the task.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  name:
    description:
      - Name of the subvolume group.
    type: str
    required: true
  volume:
    description:
      - CephFS volume the group is in. croit's own CephFS volume is used when not set.
    type: str
  state:
    description:
      - Whether the group should exist.
      - V(absent) removes the group and needs O(confirm_delete=true). ceph refuses to remove a group that
        still holds subvolumes.
    type: str
    choices: [present, absent]
    default: present
  size:
    description:
      - Quota of the group, as bytes or with a binary unit such as V(500G) or V(10T).
      - V(unlimited) (or V(0)) removes the quota.
      - The task fails instead of shrinking the quota below what the group already uses.
    type: str
  uid:
    description:
      - Owner uid of the group directory. Only set on creation.
    type: int
  gid:
    description:
      - Owner gid of the group directory. Only set on creation.
    type: int
  mode:
    description:
      - Permissions of the group directory in octal, for example V('755'). Only set on creation.
    type: str
  pool_layout:
    description:
      - Data pool the group's data is stored in. Only set on creation.
    type: str
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to remove an existing group.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Subvolume group for Kubernetes volumes, capped at 50 TiB
  croit.ceph.cephfs_subvolume_group:
    api_url: https://croit-mgmt/api
    api_token: "{{ vault_croit_token }}"
    volume: cephfs
    name: csi
    size: 50T
    mode: "755"

- name: Remove the quota
  croit.ceph.cephfs_subvolume_group:
    volume: cephfs
    name: csi
    size: unlimited

- name: Remove an empty group
  croit.ceph.cephfs_subvolume_group:
    volume: cephfs
    name: csi
    state: absent
    confirm_delete: true
"""

RETURN = r"""
subvolume_group:
  description:
    - The group as croit reports it after the change (C(SubvolumeGroupInfoResponse) in the croit API).
    - Before the change in check mode; empty when the group does not exist.
  returned: always
  type: dict
  sample:
    dataPool: cephfs.cephfs.data
    bytesUsed: 1073741824
    quotaMaxBytes: 54975581388800
    uid: 0
    gid: 0
    mode: 16877
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule, parse_quota, parse_mode


def current_quota(info):
    return info.get("quotaMaxBytes") or 0


def managed_view(info):
    if not info:
        return {}
    mode = info.get("mode")
    return dict(
        size=current_quota(info),
        uid=info.get("uid"),
        gid=info.get("gid"),
        mode="%04o" % (mode & 0o7777) if isinstance(mode, int) else None,
        pool_layout=info.get("dataPool"),
    )


class SubvolumeGroupModule(CroitModule):
    def __init__(self):
        super(SubvolumeGroupModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                volume=dict(type="str"),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                size=dict(type="str"),
                uid=dict(type="int"),
                gid=dict(type="int"),
                mode=dict(type="str"),
                pool_layout=dict(type="str"),
                confirm_delete=dict(type="bool", default=False),
            ),
            wait=False,
            warnings=False,
        )
        self.size = None
        self.mode = None

    @property
    def query(self):
        return dict(volume=self.params["volume"])

    @property
    def group_path(self):
        return path_join("cephfs", "subvolume-groups", self.params["name"])

    def find_group(self):
        names = [g.get("name") for g in self.get_list("/cephfs/subvolume-groups", query=self.query)]
        if self.params["name"] not in names:
            return None
        return self.get(self.group_path, query=self.query) or {}

    def run(self):
        p = self.params
        try:
            self.size = parse_quota(p["size"])
            self.mode = parse_mode(p["mode"])
        except ValueError as e:
            self.module.fail_json(msg=str(e))

        current = self.find_group()
        if p["state"] == "absent":
            return self.absent(current)
        if current is None:
            return self.create()
        return self.update(current)

    def absent(self, current):
        if current is None:
            self.exit(changed=False, subvolume_group={})
        if not self.params["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to remove subvolume group %r without confirm_delete=true" % self.params["name"]
            )
        if not self.check_mode:
            self.write("DELETE", self.group_path, query=self.query)
        self.exit(changed=True, before=managed_view(current), after={}, subvolume_group={})

    def create(self):
        p = self.params
        body = dict(uid=p["uid"], gid=p["gid"], poolLayout=p["pool_layout"])
        if p["mode"] is not None:
            body["mode"] = "%o" % self.mode
        if self.size:
            body["size"] = self.size
        body = dict((k, v) for k, v in body.items() if v is not None)
        after = dict(
            size=self.size or 0,
            uid=p["uid"],
            gid=p["gid"],
            mode="%04o" % self.mode if self.mode is not None else None,
            pool_layout=p["pool_layout"],
        )
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, subvolume_group={})
        self.write("POST", self.group_path, body=body, query=self.query)
        self.exit(changed=True, before={}, after=after, subvolume_group=self.find_group() or {})

    def update(self, current):
        p = self.params
        before = managed_view(current)
        immutable = dict(
            uid=p["uid"],
            gid=p["gid"],
            mode="%04o" % self.mode if self.mode is not None else None,
            pool_layout=p["pool_layout"],
        )
        for opt, value in immutable.items():
            if value is not None and value != before[opt]:
                self.module.fail_json(
                    msg="%s of subvolume group %r is %r and can only be set when the group is created (wanted %r)"
                    % (opt, p["name"], before[opt], value)
                )

        after = dict(before)
        if self.size is None or self.size == before["size"]:
            self.exit(changed=False, before=before, after=after, subvolume_group=current)

        used = current.get("bytesUsed") or 0
        if self.size and self.size < used:
            self.module.fail_json(
                msg="Refusing to shrink the quota of subvolume group %r to %d bytes: it already uses %d bytes"
                % (p["name"], self.size, used)
            )
        after["size"] = self.size
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, subvolume_group=current)
        body = dict(newSize=self.size) if self.size else {}
        self.write("POST", self.group_path + "/resize", body=body, query=self.query)
        self.exit(changed=True, before=before, after=after, subvolume_group=self.find_group() or {})


def main():
    SubvolumeGroupModule().run()


if __name__ == "__main__":
    main()
