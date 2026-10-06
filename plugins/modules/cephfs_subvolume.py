#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /cephfs/subvolumes
# croit-api: GET /cephfs/subvolumes/{subvolumeName}
# croit-api: POST /cephfs/subvolumes/{subvolumeName}
# croit-api: POST /cephfs/subvolumes/{subvolumeName}/resize
# croit-api: DELETE /cephfs/subvolumes/{subvolumeName}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: cephfs_subvolume
short_description: Manage CephFS subvolumes on a croit cluster
version_added: 0.1.0
description:
  - Create, resize and delete CephFS subvolumes through the croit API. A subvolume is identified by
    O(volume), O(group) and O(name).
  - Only options that are set are managed; anything left out keeps its current value.
  - O(uid), O(gid), O(mode), O(pool_layout) and O(namespace_isolated) can only be set when the subvolume
    is created. They are compared afterwards, and a difference fails the task instead of recreating the
    subvolume.
  - A subvolume that was removed with its snapshots retained (state C(snapshot-retained)) counts as absent.
  - Removing a subvolume deletes its data and needs O(confirm_delete=true).
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
      - Name of the subvolume, for example V(pvc-0042).
    type: str
    required: true
  volume:
    description:
      - CephFS volume the subvolume is in. croit's own CephFS volume is used when not set.
    type: str
  group:
    description:
      - Subvolume group the subvolume is in. ceph's default group is used when not set.
    type: str
  state:
    description:
      - Whether the subvolume should exist.
      - V(absent) removes the subvolume and B(all data in it), and needs O(confirm_delete=true).
    type: str
    choices: [present, absent]
    default: present
  size:
    description:
      - Quota of the subvolume, as bytes or with a binary unit such as V(100G) or V(2T).
      - V(unlimited) (or V(0)) removes the quota. When not set, the current quota is kept, and a new
        subvolume is created without one.
      - The task fails, before anything is changed, instead of shrinking the quota below what the
        subvolume already uses.
    type: str
  uid:
    description:
      - Owner uid of the subvolume directory. Only set when the subvolume is created; a different value
        on an existing subvolume fails the task.
    type: int
  gid:
    description:
      - Owner gid of the subvolume directory. Only set when the subvolume is created; a different value
        on an existing subvolume fails the task.
    type: int
  mode:
    description:
      - Permissions of the subvolume directory in octal, for example V('755') or V('0750'). Quote the
        value so YAML keeps it a string.
      - Only set when the subvolume is created; a different value on an existing subvolume fails the task.
    type: str
  pool_layout:
    description:
      - Data pool the subvolume's data is stored in. When not set, the group's or volume's data pool is used.
      - Only set when the subvolume is created; a different value on an existing subvolume fails the task.
    type: str
  namespace_isolated:
    description:
      - Store the subvolume in its own RADOS namespace, so a client key can be limited to it.
      - Only set when the subvolume is created; a different value on an existing subvolume fails the task.
    type: bool
  retain_snapshots:
    description:
      - With O(state=absent), keep the subvolume's snapshots. ceph then keeps an entry in state
        C(snapshot-retained), which this module treats as absent.
      - Ignored with O(state=present).
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to remove an existing subvolume and its data. Without it the
        task fails, in check mode too.
    type: bool
    default: false
notes:
  - It is assumed that ceph cannot change the owner, mode, data pool or namespace isolation of an
    existing subvolume, and that ceph lists C(snapshot-retained) subvolumes and allows one to be created
    again with the same name. Neither has been verified against a live croit cluster.
seealso:
  - module: croit.ceph.cephfs_subvolume_group
    description: Manage the group a subvolume lives in.
  - module: croit.ceph.cephfs_volume
    description: Manage the CephFS volume.
  - module: croit.ceph.ceph_key
    description: Create a key limited to the subvolume's path or namespace.
  - module: croit.ceph.snapshot_schedule
    description: Schedule snapshots of the subvolume's directory.
  - name: croit API reference
    description: The croit REST API, including the C(/cephfs/subvolumes) endpoints.
    link: https://www.croit.io/api-docs
  - name: CephFS subvolumes
    description: Upstream documentation of CephFS subvolume groups and subvolumes.
    link: https://docs.ceph.com/en/latest/cephfs/fs-volumes/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: 100 GiB subvolume in the csi group
  croit.ceph.cephfs_subvolume:
    volume: cephfs
    group: csi
    name: pvc-0042
    size: 100G
    namespace_isolated: true
  register: pvc

- name: Show the path clients mount
  ansible.builtin.debug:
    msg: "Mount {{ pvc.subvolume.path }}"

- name: Grow it
  croit.ceph.cephfs_subvolume:
    volume: cephfs
    group: csi
    name: pvc-0042
    size: 200G

- name: Remove it and its data, keeping its snapshots
  croit.ceph.cephfs_subvolume:
    volume: cephfs
    group: csi
    name: pvc-0042
    state: absent
    retain_snapshots: true
    confirm_delete: true
"""

RETURN = r"""
subvolume:
  description:
    - The subvolume as croit reports it after the change (C(SubvolumeInfoResponse) in the croit API).
    - Before the change in check mode; empty when the subvolume does not exist.
  returned: always
  type: dict
  contains:
    path:
      description: Absolute CephFS path of the subvolume, which clients mount.
      returned: when the subvolume exists
      type: str
      sample: /volumes/csi/pvc-0042/0b6c4a8e-7c1f-4b8e-9c55-2f0a5d1b9e10
    dataPool:
      description: Data pool the subvolume's data is stored in.
      returned: when the subvolume exists
      type: str
      sample: cephfs.cephfs.data
    poolNamespace:
      description: RADOS namespace of the subvolume, or null when it is not namespace isolated.
      returned: when the subvolume exists
      type: str
      sample: fsvolumens_pvc-0042
    bytesUsed:
      description: Bytes the subvolume uses.
      returned: when the subvolume exists
      type: int
      sample: 1048576
    quotaMaxBytes:
      description: Quota in bytes, or null when there is none.
      returned: when the subvolume exists
      type: int
      sample: 107374182400
    uid:
      description: Owner uid of the subvolume directory.
      returned: when the subvolume exists
      type: int
      sample: 0
    gid:
      description: Owner gid of the subvolume directory.
      returned: when the subvolume exists
      type: int
      sample: 0
    mode:
      description: Mode of the subvolume directory as a decimal integer, including the file type bits.
      returned: when the subvolume exists
      type: int
      sample: 16877
    state:
      description: C(complete), or C(snapshot-retained) for a subvolume removed with its snapshots kept.
      returned: when the subvolume exists
      type: str
      sample: complete
    type:
      description: C(subvolume) or C(clone).
      returned: when the subvolume exists
      type: str
      sample: subvolume
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule, parse_quota, parse_mode

RETAINED = "snapshot-retained"


def managed_view(info):
    if not info:
        return {}
    mode = info.get("mode")
    return dict(
        size=info.get("quotaMaxBytes") or 0,
        uid=info.get("uid"),
        gid=info.get("gid"),
        mode="%04o" % (mode & 0o7777) if isinstance(mode, int) else None,
        pool_layout=info.get("dataPool"),
        namespace_isolated=bool(info.get("poolNamespace")),
    )


class SubvolumeModule(CroitModule):
    def __init__(self):
        super(SubvolumeModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                volume=dict(type="str"),
                group=dict(type="str"),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                size=dict(type="str"),
                uid=dict(type="int"),
                gid=dict(type="int"),
                mode=dict(type="str"),
                pool_layout=dict(type="str"),
                namespace_isolated=dict(type="bool"),
                retain_snapshots=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
            wait=False,
            warnings=False,
        )
        self.size = None
        self.mode = None

    @property
    def query(self):
        return dict(volume=self.params["volume"], groupName=self.params["group"])

    @property
    def subvolume_path(self):
        return path_join("cephfs", "subvolumes", self.params["name"])

    def find_subvolume(self):
        names = [s.get("name") for s in self.get_list("/cephfs/subvolumes", query=self.query)]
        if self.params["name"] not in names:
            return None
        info = self.get(self.subvolume_path, query=self.query) or {}
        if info.get("state") == RETAINED:
            return None
        return info

    def run(self):
        p = self.params
        try:
            self.size = parse_quota(p["size"])
            self.mode = parse_mode(p["mode"])
        except ValueError as e:
            self.module.fail_json(msg=str(e))

        current = self.find_subvolume()
        if p["state"] == "absent":
            return self.absent(current)
        if current is None:
            return self.create()
        return self.update(current)

    def absent(self, current):
        if current is None:
            self.exit(changed=False, subvolume={})
        if not self.params["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to remove subvolume %r and all its data without confirm_delete=true" % self.params["name"]
            )
        if not self.check_mode:
            query = dict(self.query)
            if self.params["retain_snapshots"]:
                query["retainSnapshots"] = True
            self.write("DELETE", self.subvolume_path, query=query)
        self.exit(changed=True, before=managed_view(current), after={}, subvolume={})

    def wanted_immutable(self):
        p = self.params
        return dict(
            uid=p["uid"],
            gid=p["gid"],
            mode="%04o" % self.mode if self.mode is not None else None,
            pool_layout=p["pool_layout"],
            namespace_isolated=p["namespace_isolated"],
        )

    def create(self):
        p = self.params
        body = dict(uid=p["uid"], gid=p["gid"], poolLayout=p["pool_layout"], namespaceIsolated=p["namespace_isolated"])
        if self.mode is not None:
            body["mode"] = "%o" % self.mode
        if self.size:
            body["size"] = self.size
        body = dict((k, v) for k, v in body.items() if v is not None)
        after = self.wanted_immutable()
        after["size"] = self.size or 0
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, subvolume={})
        self.write("POST", self.subvolume_path, body=body, query=self.query)
        self.exit(changed=True, before={}, after=after, subvolume=self.find_subvolume() or {})

    def update(self, current):
        p = self.params
        before = managed_view(current)
        for opt, value in self.wanted_immutable().items():
            if value is not None and value != before[opt]:
                self.module.fail_json(
                    msg="%s of subvolume %r is %r and can only be set when the subvolume is created (wanted %r)"
                    % (opt, p["name"], before[opt], value)
                )

        after = dict(before)
        if self.size is None or self.size == before["size"]:
            self.exit(changed=False, before=before, after=after, subvolume=current)

        used = current.get("bytesUsed") or 0
        if self.size and self.size < used:
            self.module.fail_json(
                msg="Refusing to shrink the quota of subvolume %r to %d bytes: it already uses %d bytes"
                % (p["name"], self.size, used)
            )
        after["size"] = self.size
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, subvolume=current)
        body = dict(newSize=self.size) if self.size else {}
        self.write("POST", self.subvolume_path + "/resize", body=body, query=self.query)
        self.exit(changed=True, before=before, after=after, subvolume=self.find_subvolume() or {})


def main():
    SubvolumeModule().run()


if __name__ == "__main__":
    main()
