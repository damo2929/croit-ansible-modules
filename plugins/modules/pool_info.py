#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /pools
# croit-api: GET /pools/{name}/details
# croit-api: GET /pools/{name}/compression

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: pool_info
short_description: Read Ceph pools from a croit cluster
version_added: 0.1.0
description:
  - Returns the Ceph pools of a croit cluster, or one pool by name.
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
  name:
    description:
      - Only return the pool with this name. An unknown name returns an empty list.
    type: str
  details:
    description:
      - Also read each returned pool's details and compression settings.
      - This costs two extra requests per pool, so combine it with O(name) on large clusters.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: List all pools
  croit.ceph.pool_info:
  register: pools

- name: Read one pool with its details
  croit.ceph.pool_info:
    name: rbd-ssd
    details: true
  register: rbd_pool

- name: Fail when the pool is missing
  ansible.builtin.assert:
    that: rbd_pool.pools | length == 1
"""

RETURN = r"""
pools:
  description:
    - The pools (C(CephPoolResponse) in the croit API).
    - With O(details=true) each pool also has C(details) (as croit reports it) and C(compression).
  returned: always
  type: list
  elements: dict
  sample:
    - name: rbd-ssd
      poolId: 3
      application: rbd
      size: 3
      minSize: 2
      pgNum: 128
      crushRule: 1
      erasureCoding: false
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            name=dict(type="str"),
            details=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    name = m.params["name"]
    pools = m.get_list("/pools")
    if name is not None:
        pools = [p for p in pools if p.get("name") == name]
    if m.params["details"]:
        for pool in pools:
            pool["details"] = m.get(path_join("pools", pool["name"], "details"))
            pool["compression"] = m.get(path_join("pools", pool["name"], "compression"))
    m.exit(changed=False, pools=pools)


if __name__ == "__main__":
    main()
