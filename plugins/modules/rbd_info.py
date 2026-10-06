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
  - Returns RBD images, filtered by pool, namespace and name. This module never changes anything.
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
seealso:
  - module: croit.ceph.rbd
    description: Create, grow, clone and delete RBD images.
  - module: croit.ceph.rbd_snapshot
    description: Manage the snapshots of an image.
  - name: croit API reference
    description: The C(/rbds) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: All images in a pool
  croit.ceph.rbd_info:
    pool: rbd-ssd
  register: images

- name: Show the images larger than 1 TiB
  ansible.builtin.debug:
    msg: "{{ images.images | selectattr('size', 'gt', 1099511627776) | map(attribute='name') | list }}"

- name: One image with its snapshots
  croit.ceph.rbd_info:
    pool: rbd-ssd
    name: vm-disk-01
  register: disk

- name: Just the names of every image on the cluster
  croit.ceph.rbd_info:
    details: false
  register: names
"""

RETURN = r"""
images:
  description:
    - The images (C(RbdImageResponse) in the croit API). Empty when nothing matches.
    - With O(details=false), each entry only has C(pool), C(namespace) and C(rbd), the image name.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: The image's name.
      returned: when O(details=true)
      type: str
      sample: vm-disk-01
    rbd:
      description: The image's name.
      returned: when O(details=false)
      type: str
      sample: vm-disk-01
    pool:
      description: The pool the image is in.
      returned: always
      type: str
      sample: rbd-ssd
    namespace:
      description: The namespace the image is in, or V(null) for the pool's default namespace.
      returned: always
      type: str
      sample: null
    size:
      description: The image's size in bytes, or V(-1) where croit could not read it.
      returned: when O(details=true)
      type: int
      sample: 107374182400
    features:
      description: The enabled rbd features, as croit spells them.
      returned: when O(details=true)
      type: list
      elements: str
      sample: [LAYERING, EXCLUSIVE_LOCK]
    parent:
      description: The snapshot the image was cloned from, or V(null).
      returned: when O(details=true)
      type: dict
      sample: null
    mirrorInfo:
      description: How the image is mirrored (C(RbdMirrorImageInfo) in the croit API).
      returned: when O(details=true)
      type: dict
      sample:
        imageMirrorMode: DISABLED
        mirrorState: DISABLED
    snaps:
      description: The image's snapshots, each with C(id), C(name) and C(protect).
      returned: when O(name) is set
      type: list
      elements: dict
      sample: []
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
