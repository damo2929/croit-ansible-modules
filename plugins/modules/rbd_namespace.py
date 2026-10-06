#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /pools/{pool}/rbd-namespaces
# croit-api: PUT /pools/{pool}/rbd-namespaces/{namespace}
# croit-api: DELETE /pools/{pool}/rbd-namespaces/{namespace}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: rbd_namespace
short_description: Manage RBD namespaces on a croit cluster
version_added: 0.1.0
description:
  - Creates and deletes RBD namespaces in a pool. A namespace is identified by O(pool) and O(name).
  - croit refuses to delete a namespace that still holds images, so deleting one never destroys data.
  - Requires Ceph Nautilus or later.
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
      - Pool the namespace is in. It must exist.
    type: str
    required: true
  name:
    description:
      - Name of the namespace within O(pool).
    type: str
    required: true
  state:
    description:
      - Whether the namespace should exist.
      - V(absent) needs no confirmation, because croit refuses to delete a namespace that still holds images.
    type: str
    choices: [present, absent]
    default: present
seealso:
  - module: croit.ceph.rbd
    description: Create images in a namespace.
  - module: croit.ceph.rbd_info
    description: Read the images in a namespace.
  - name: croit API reference
    description: The C(/pools/{pool}/rbd-namespaces) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph RBD namespaces
    description: Upstream documentation of RBD namespaces.
    link: https://docs.ceph.com/en/latest/man/8/rbd/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Namespace per tenant
  croit.ceph.rbd_namespace:
    pool: rbd-ssd
    name: tenant-a
  register: ns

- name: Show every namespace in the pool
  ansible.builtin.debug:
    msg: "{{ ns.namespaces }}"

- name: Remove an empty namespace
  croit.ceph.rbd_namespace:
    pool: rbd-ssd
    name: tenant-old
    state: absent
"""

RETURN = r"""
namespaces:
  description: The names of the pool's RBD namespaces after the change (before it in check mode).
  returned: always
  type: list
  elements: str
  sample: [tenant-a, tenant-b]
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            pool=dict(type="str", required=True),
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["present", "absent"]),
        ),
        wait=False,
        warnings=False,
    )
    p = m.params
    list_path = path_join("pools", p["pool"], "rbd-namespaces")
    names = sorted(ns["name"] for ns in m.get_list(list_path))
    exists = p["name"] in names
    want = p["state"] == "present"

    before = dict(namespace=p["name"]) if exists else {}
    after = dict(namespace=p["name"]) if want else {}
    if exists == want:
        m.exit(changed=False, before=before, after=after, namespaces=names)
    if m.check_mode:
        m.exit(changed=True, before=before, after=after, namespaces=names)

    m.write("PUT" if want else "DELETE", path_join("pools", p["pool"], "rbd-namespaces", p["name"]))
    names = sorted(ns["name"] for ns in m.get_list(list_path))
    m.exit(changed=True, before=before, after=after, namespaces=names)


if __name__ == "__main__":
    main()
