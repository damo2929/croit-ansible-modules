#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /rbds/rbd-names
# croit-api: GET /pools/{pool}/rbds/{rbd}
# croit-api: POST /pools/{pool}/rbds
# croit-api: PATCH /pools/{pool}/rbds/{rbd}
# croit-api: DELETE /pools/{pool}/rbds/{rbd}
# croit-api: POST /pools/{pool}/rbds/{rbd}/flatten
# croit-api: POST /pools/{pool}/rbds/{rbd}/snapshots/{snap}/clone
# croit-api: GET /pools/{pool}/rbds/{rbd}/qos
# croit-api: POST /pools/{pool}/rbds/{rbd}/qos

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: rbd
short_description: Manage RBD images on a croit cluster
version_added: 0.1.0
description:
  - Create, grow, clone, flatten and delete RBD images, and manage their features and QoS limits.
  - Only options that are set are managed; anything left out keeps its current value.
  - An image can only grow. A smaller O(size) fails the task instead of shrinking the image.
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
      - Pool the image is in.
    type: str
    required: true
  namespace:
    description:
      - RBD namespace the image is in. Leave unset for the pool's default namespace.
      - croit creates the namespace when an image is created in one that does not exist yet.
    type: str
  name:
    description:
      - Name of the image.
    type: str
    required: true
  state:
    description:
      - Whether the image should exist.
      - V(absent) deletes the image and B(all data in it), and needs O(confirm_delete=true).
        croit refuses to delete an image that still has snapshots.
    type: str
    choices: [present, absent]
    default: present
  size:
    description:
      - Size of the image, as bytes or with a binary unit such as V(100G) or V(2T).
      - croit rounds sizes up to the next MiB; the comparison does the same.
      - Required to create an image that is not a clone. A clone gets its parent's size when not set.
      - An existing image can only grow.
    type: str
  features:
    description:
      - The complete list of rbd features that should be enabled. croit enables and disables features
        to match. Changing features can interrupt clients, and croit warns first (see O(ignore_warnings)).
      - When creating without it, ceph's default features are used. An empty list enables none.
    type: list
    elements: str
    choices: [layering, exclusive_lock, object_map, fast_diff, deep_flatten, journaling]
  erasure_coded_pool:
    description:
      - Erasure coded pool to store the image's data in, keeping only metadata in O(pool).
      - Can only be set when the image is created; a different value on an existing image fails the task.
    type: str
  clone_from:
    description:
      - Create the image as a clone of a snapshot instead of an empty image.
      - Only used when the image is created. An existing image is never re-cloned.
    type: dict
    suboptions:
      pool:
        description: Pool of the parent image.
        type: str
        required: true
      namespace:
        description: Namespace of the parent image. Leave unset for the default namespace.
        type: str
      image:
        description: Name of the parent image.
        type: str
        required: true
      snapshot:
        description: Snapshot of the parent image to clone.
        type: str
        required: true
  flatten:
    description:
      - With V(true), a clone is flattened (made independent of its parent snapshot). An image that is not
        a clone is left alone. Flattening copies all shared data and may take a long time.
      - V(false) and unset do nothing; an image cannot be turned back into a clone.
    type: bool
    default: false
  qos:
    description:
      - QoS limits set on the image itself, keyed by rbd config key such as C(rbd_qos_iops_limit) or
        C(rbd_qos_bps_limit). Byte limits also accept a binary unit such as V(100M).
      - A null value removes the image's own limit, so it falls back to the pool's
        (see M(croit.ceph.pool_qos)).
      - Only the named limits are managed.
    type: dict
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing image and all its data.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: VM disk with QoS
  croit.ceph.rbd:
    pool: rbd-ssd
    name: vm-disk-01
    size: 100G
    features: [layering, exclusive_lock, object_map, fast_diff, deep_flatten]
    qos:
      rbd_qos_iops_limit: 1000

- name: Grow the disk
  croit.ceph.rbd:
    pool: rbd-ssd
    name: vm-disk-01
    size: 200G

- name: Image in a namespace with data on an erasure coded pool
  croit.ceph.rbd:
    pool: rbd-meta
    namespace: tenant-a
    name: archive
    size: 10T
    erasure_coded_pool: rbd-ec-data

- name: Clone a golden image and make it independent
  croit.ceph.rbd:
    pool: rbd-ssd
    name: vm-disk-02
    clone_from:
      pool: rbd-ssd
      image: golden
      snapshot: v1
    flatten: true

- name: Delete an image and its data
  croit.ceph.rbd:
    pool: rbd-ssd
    name: scratch
    state: absent
    confirm_delete: true
"""

RETURN = r"""
image:
  description:
    - The image as croit reads it from the cluster after the change (C(RbdImageResponse) in the croit API),
      including its snapshots.
    - Before the change in check mode; empty when the image does not exist.
  returned: always
  type: dict
  sample:
    name: vm-disk-01
    pool: rbd-ssd
    namespace: null
    size: 107374182400
    features: [LAYERING, EXCLUSIVE_LOCK, OBJECT_MAP, FAST_DIFF, DEEP_FLATTEN]
    parent: null
    snaps: []
qos:
  description: The image's QoS settings after the change (C(QosCommandsResponse) in the croit API).
  returned: when O(qos) is set and the image exists
  type: list
  elements: dict
task:
  description: The croit background task the change ran as (delete or flatten), when there was one.
  returned: when a task ran
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import ceil_mib, CroitModule, parse_size, subset
from ansible_collections.croit.ceph.plugins.module_utils.qos import qos_apply, qos_changes, qos_current, qos_desired


class RbdModule(CroitModule):
    def __init__(self):
        super(RbdModule, self).__init__(
            dict(
                pool=dict(type="str", required=True),
                namespace=dict(type="str"),
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                size=dict(type="str"),
                features=dict(
                    type="list",
                    elements="str",
                    choices=["layering", "exclusive_lock", "object_map", "fast_diff", "deep_flatten", "journaling"],
                ),
                erasure_coded_pool=dict(type="str"),
                clone_from=dict(
                    type="dict",
                    options=dict(
                        pool=dict(type="str", required=True),
                        namespace=dict(type="str"),
                        image=dict(type="str", required=True),
                        snapshot=dict(type="str", required=True),
                    ),
                ),
                flatten=dict(type="bool", default=False),
                qos=dict(type="dict"),
                confirm_delete=dict(type="bool", default=False),
            ),
        )
        self.namespace = self.params["namespace"] or None
        self.query = dict(namespace=self.namespace) if self.namespace else None
        self.image_path = path_join("pools", self.params["pool"], "rbds", self.params["name"])

    # Lookups --------------------------------------------------------------

    def exists(self):
        p = self.params
        for entry in self.get_list("/rbds/rbd-names"):
            if (
                entry.get("pool") == p["pool"]
                and entry.get("rbd") == p["name"]
                and (entry.get("namespace") or None) == self.namespace
            ):
                return True
        return False

    def read(self):
        return self.get(self.image_path, query=self.query)

    def desired_size(self):
        try:
            size = parse_size(self.params["size"])
        except ValueError as e:
            self.module.fail_json(msg="size: %s" % e)
        if size is not None:
            if size < 1:
                self.module.fail_json(msg="size must be at least 1 byte")
            size = ceil_mib(size)
        return size

    def desired_features(self):
        features = self.params["features"]
        if features is None:
            return None
        return sorted(set(f.upper() for f in features))

    # Main -----------------------------------------------------------------

    def run(self):
        exists = self.exists()
        if self.params["state"] == "absent":
            return self.absent(exists)
        if not exists:
            return self.create()
        return self.update(self.read())

    def view(self, image):
        if not image:
            return {}
        return dict(
            size=image.get("size"),
            features=sorted(image.get("features") or []),
            erasure_coded_pool=image.get("erasureCodedPool"),
            parent=image.get("parent"),
        )

    def absent(self, exists):
        if not exists:
            self.exit(changed=False, image={})
        image = self.read()
        if not self.params["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to delete image %r and all its data without confirm_delete=true" % self.params["name"]
            )
        result = dict(changed=True, before=self.view(image), after={}, image={})
        if not self.check_mode:
            task = self.handle_task(self.write("DELETE", self.image_path, query=self.query))
            if task is not None:
                result["task"] = task
        self.exit(**result)

    def create(self):
        p = self.params
        size = self.desired_size()
        features = self.desired_features()
        clone = p["clone_from"]
        if clone is None and size is None:
            self.module.fail_json(msg="size is required to create image %r" % p["name"])
        if clone is not None and p["erasure_coded_pool"] is not None:
            self.module.fail_json(msg="erasure_coded_pool cannot be set on a clone")

        after = dict(size=size, features=features, erasure_coded_pool=p["erasure_coded_pool"])
        if clone is not None:
            after["parent"] = None if p["flatten"] else dict(
                pool=clone["pool"], image=clone["image"], snapshot=clone["snapshot"]
            )
        desired_qos = qos_desired(self, p["qos"])
        if desired_qos:
            after["qos"] = desired_qos
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, image={})

        result = dict(changed=True, before={}, after=after)
        if clone is None:
            body = dict(name=p["name"], size=size)
            if self.namespace:
                body["namespace"] = self.namespace
            if features is not None:
                body["features"] = features
            if p["erasure_coded_pool"] is not None:
                body["erasureCodedPool"] = p["erasure_coded_pool"]
            self.write("POST", path_join("pools", p["pool"], "rbds"), body=body)
        else:
            body = dict(pool=p["pool"], name=p["name"])
            if self.namespace:
                body["namespace"] = self.namespace
            parent_ns = clone.get("namespace") or None
            self.write(
                "POST",
                path_join("pools", clone["pool"], "rbds", clone["image"], "snapshots", clone["snapshot"], "clone"),
                body=body,
                query=dict(namespace=parent_ns) if parent_ns else None,
            )
            # A clone starts with its parent's size and the parent's features.
            image = self.read()
            patch = {}
            if size is not None and size > image.get("size", 0):
                patch["size"] = size
            if features is not None and sorted(image.get("features") or []) != features:
                patch["features"] = features
            if patch:
                self.write("PATCH", self.image_path, body=patch, query=self.query)
            if p["flatten"]:
                task = self.handle_task(self.write("POST", self.image_path + "/flatten", query=self.query))
                if task is not None:
                    result["task"] = task

        if desired_qos:
            qos_path = self.image_path + "/qos"
            changes = qos_changes(self, qos_current(self.get_list(qos_path, query=self.query)), desired_qos)
            if changes:
                self.apply_qos(changes)
            result["qos"] = self.get_list(qos_path, query=self.query)
        result["image"] = self.read()
        self.exit(**result)

    def update(self, image):
        p = self.params
        before = self.view(image)
        after = dict(before)
        patch = {}

        ec_pool = p["erasure_coded_pool"]
        if ec_pool is not None and ec_pool != image.get("erasureCodedPool"):
            self.module.fail_json(
                msg="erasure_coded_pool of image %r is %r and cannot be changed to %r after creation"
                % (p["name"], image.get("erasureCodedPool"), ec_pool)
            )

        size = self.desired_size()
        if size is not None:
            current_size = image.get("size")
            if current_size is None or current_size < 0:
                self.module.fail_json(msg="croit could not read the size of image %r; try again" % p["name"])
            if size < current_size:
                self.module.fail_json(
                    msg="Image %r is %d bytes and cannot shrink to %d bytes" % (p["name"], current_size, size)
                )
            if size != current_size:
                patch["size"] = size
                after["size"] = size

        features = self.desired_features()
        if features is not None and features != before["features"]:
            patch["features"] = features
            after["features"] = features

        flatten = bool(p["flatten"] and image.get("parent"))
        if flatten:
            after["parent"] = None

        result = dict(image=image)
        qos_path = self.image_path + "/qos"
        qos_changed = {}
        desired_qos = qos_desired(self, p["qos"])
        if desired_qos:
            rows = self.get_list(qos_path, query=self.query)
            current_qos = qos_current(rows)
            qos_changed = qos_changes(self, current_qos, desired_qos)
            before["qos"] = subset(current_qos, desired_qos)
            after["qos"] = dict(before["qos"])
            after["qos"].update(qos_changed)
            result["qos"] = rows

        changed = bool(patch or flatten or qos_changed)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, **result)

        if patch:
            self.write("PATCH", self.image_path, body=patch, query=self.query)
        if flatten:
            task = self.handle_task(self.write("POST", self.image_path + "/flatten", query=self.query))
            if task is not None:
                result["task"] = task
        if qos_changed:
            self.apply_qos(qos_changed)
            result["qos"] = self.get_list(qos_path, query=self.query)
        result["image"] = self.read()
        self.exit(changed=True, before=before, after=after, **result)

    def apply_qos(self, changes):
        qos_apply(self, self.image_path + "/qos", changes, query=self.query)


def main():
    RbdModule().run()


if __name__ == "__main__":
    main()
