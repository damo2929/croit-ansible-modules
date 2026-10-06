#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /rbds/rbd-names
# croit-api: GET /rbds/rbd-infos
# croit-api: GET /pools/{pool}/rbds/{rbd}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: rbd_info
short_description: Read RBD images from a croit cluster
version_added: 0.1.0
description:
  - Returns RBD images, filtered by pool, namespace and name.
  - With O(name) set, the image is read from the cluster and includes its snapshots. Otherwise the images
    are read in batches, without snapshots.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: N/A
options:
  pool:
    description:
      - Only return images in this pool. Required with O(name).
    type: str
  namespace:
    description:
      - Only return images in this RBD namespace. Use an empty string for the pool's default namespace.
      - When not set, images in every namespace are returned.
    type: str
  name:
    description:
      - Only return this image. An image that does not exist returns an empty list.
    type: str
  details:
    description:
      - Read each image's details (size, features, parent, mirroring).
      - With V(false) only C(pool), C(namespace) and C(rbd) (the image name) are returned, which is much
        cheaper on large clusters.
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: All images in a pool
  croit.ceph.rbd_info:
    pool: rbd-ssd
  register: images

- name: One image with its snapshots
  croit.ceph.rbd_info:
    pool: rbd-ssd
    name: vm-disk-01
  register: disk

- name: Just the names of every image on the cluster
  croit.ceph.rbd_info:
    details: false
"""

RETURN = r"""
images:
  description:
    - The images (C(RbdImageResponse) in the croit API), or C(RbdNameResponse) entries with O(details=false).
  returned: always
  type: list
  elements: dict
  sample:
    - name: vm-disk-01
      pool: rbd-ssd
      namespace: null
      size: 107374182400
      features: [LAYERING, EXCLUSIVE_LOCK]
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

BATCH = 50


def image_ref(entry):
    parts = [entry["pool"]]
    if entry.get("namespace"):
        parts.append(entry["namespace"])
    parts.append(entry["rbd"])
    return "/".join(parts)


def main():
    m = CroitModule(
        dict(
            pool=dict(type="str"),
            namespace=dict(type="str"),
            name=dict(type="str"),
            details=dict(type="bool", default=True),
        ),
        wait=False,
        warnings=False,
        required_by=dict(name="pool"),
    )
    p = m.params
    entries = m.get_list("/rbds/rbd-names")
    if p["pool"] is not None:
        entries = [e for e in entries if e.get("pool") == p["pool"]]
    if p["namespace"] is not None:
        wanted = p["namespace"] or None
        entries = [e for e in entries if (e.get("namespace") or None) == wanted]
    if p["name"] is not None:
        entries = [e for e in entries if e.get("rbd") == p["name"]]

    if not p["details"]:
        m.exit(changed=False, images=entries)

    if p["name"] is not None:
        images = []
        for entry in entries:
            query = dict(namespace=entry["namespace"]) if entry.get("namespace") else None
            images.append(m.get(path_join("pools", entry["pool"], "rbds", entry["rbd"]), query=query))
        m.exit(changed=False, images=images)

    images = []
    refs = [image_ref(e) for e in entries]
    for start in range(0, len(refs), BATCH):
        chunk = refs[start:start + BATCH]
        found = m.get("/rbds/rbd-infos", query=dict(image=chunk)) or {}
        images.extend(found[ref] for ref in chunk if ref in found)
    m.exit(changed=False, images=images)


if __name__ == "__main__":
    main()
