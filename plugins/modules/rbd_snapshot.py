#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /pools/{pool}/rbds/{rbd}
# croit-api: PUT /pools/{pool}/rbds/{rbd}/snapshots/{snap}
# croit-api: PATCH /pools/{pool}/rbds/{rbd}/snapshots/{snap}
# croit-api: DELETE /pools/{pool}/rbds/{rbd}/snapshots/{snap}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: rbd_snapshot
short_description: Manage snapshots of RBD images on a croit cluster
version_added: 0.1.0
description:
  - Take, protect, unprotect and delete snapshots of an RBD image.
  - To clone a snapshot into a new image, use the O(croit.ceph.rbd#module:clone_from) option of M(croit.ceph.rbd).
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
  pool:
    description:
      - Pool the image is in.
    type: str
    required: true
  namespace:
    description:
      - RBD namespace the image is in. Leave unset for the pool's default namespace.
    type: str
  image:
    description:
      - Name of the image. It must exist.
    type: str
    required: true
  name:
    description:
      - Name of the snapshot.
    type: str
    required: true
  state:
    description:
      - Whether the snapshot should exist.
      - V(absent) deletes the snapshot and needs O(confirm_delete=true). A protected snapshot is unprotected
        first; croit refuses that while clones still depend on it.
    type: str
    choices: [present, absent]
    default: present
  protected:
    description:
      - Whether the snapshot is protected from deletion. Leave unset to keep the current protection.
      - Clones on clusters that still allow pre-Mimic clients need a protected parent snapshot.
    type: bool
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing snapshot.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Snapshot before an upgrade
  croit.ceph.rbd_snapshot:
    pool: rbd-ssd
    image: vm-disk-01
    name: pre-upgrade

- name: Protected golden snapshot for clones
  croit.ceph.rbd_snapshot:
    pool: rbd-ssd
    image: golden
    name: v1
    protected: true

- name: Delete a snapshot
  croit.ceph.rbd_snapshot:
    pool: rbd-ssd
    image: vm-disk-01
    name: pre-upgrade
    state: absent
    confirm_delete: true
"""

RETURN = r"""
snapshot:
  description:
    - The snapshot after the change (C(RbdImageSnapshot) in the croit API). Before it in check mode;
      empty when the snapshot does not exist.
  returned: always
  type: dict
  sample:
    id: 12
    name: pre-upgrade
    protect: false
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


class SnapshotModule(CroitModule):
    def __init__(self):
        super(SnapshotModule, self).__init__(
            dict(
                pool=dict(type="str", required=True),
                namespace=dict(type="str"),
                image=dict(type="str", required=True),
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                protected=dict(type="bool"),
                confirm_delete=dict(type="bool", default=False),
            ),
            wait=False,
            warnings=False,
        )
        p = self.params
        namespace = p["namespace"] or None
        self.query = dict(namespace=namespace) if namespace else None
        self.image_path = path_join("pools", p["pool"], "rbds", p["image"])
        self.snap_path = path_join("pools", p["pool"], "rbds", p["image"], "snapshots", p["name"])

    def find(self):
        image = self.get_or_none(self.image_path, query=self.query)
        if image is None:
            self.module.fail_json(msg="Image %r does not exist in pool %r" % (self.params["image"], self.params["pool"]))
        for snap in image.get("snaps") or []:
            if snap.get("name") == self.params["name"]:
                return snap
        return None

    @staticmethod
    def view(snap):
        return dict(name=snap["name"], protected=bool(snap.get("protect"))) if snap else {}

    def run(self):
        p = self.params
        snap = self.find()
        before = self.view(snap)

        if p["state"] == "absent":
            if snap is None:
                self.exit(changed=False, before={}, after={}, snapshot={})
            if not p["confirm_delete"]:
                self.module.fail_json(
                    msg="Refusing to delete snapshot %r of image %r without confirm_delete=true" % (p["name"], p["image"])
                )
            if not self.check_mode:
                if snap.get("protect"):
                    self.write("PATCH", self.snap_path, body=dict(protect=False), query=self.query)
                self.write("DELETE", self.snap_path, query=self.query)
            self.exit(changed=True, before=before, after={}, snapshot={})

        if snap is None:
            after = dict(name=p["name"], protected=bool(p["protected"]))
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, snapshot={})
            self.write("PUT", self.snap_path, query=self.query)
            if p["protected"]:
                self.write("PATCH", self.snap_path, body=dict(protect=True), query=self.query)
            self.exit(changed=True, before={}, after=after, snapshot=self.find() or {})

        if p["protected"] is None or bool(snap.get("protect")) == p["protected"]:
            self.exit(changed=False, before=before, after=before, snapshot=snap)
        after = dict(before, protected=p["protected"])
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, snapshot=snap)
        self.write("PATCH", self.snap_path, body=dict(protect=p["protected"]), query=self.query)
        self.exit(changed=True, before=before, after=after, snapshot=self.find() or {})


def main():
    SnapshotModule().run()


if __name__ == "__main__":
    main()
