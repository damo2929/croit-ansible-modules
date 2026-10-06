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
  - With O(details=true) it also reads each pool's details and compression settings. This module never
    changes anything.
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
      - Only return the pool with this name. An unknown name returns an empty list instead of failing.
    type: str
  details:
    description:
      - Also read each returned pool's details and compression settings.
      - This costs two extra requests per pool, so combine it with O(name) on large clusters.
    type: bool
    default: false
seealso:
  - module: croit.ceph.pool
    description: Create, update and delete pools.
  - module: croit.ceph.rbd_info
    description: Read the RBD images in a pool.
  - name: croit API reference
    description: The C(/pools) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: List all pools
  croit.ceph.pool_info:
  register: pools

- name: Show the pool names
  ansible.builtin.debug:
    msg: "{{ pools.pools | map(attribute='name') | list }}"

- name: Read one pool with its details
  croit.ceph.pool_info:
    name: rbd-ssd
    details: true
  register: rbd_pool

- name: Fail when the pool is missing
  ansible.builtin.assert:
    that: rbd_pool.pools | length == 1
    fail_msg: Pool rbd-ssd does not exist
"""

RETURN = r"""
pools:
  description:
    - The pools (C(CephPoolResponse) in the croit API). Empty when O(name) matches no pool.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: The pool's name.
      returned: always
      type: str
      sample: rbd-ssd
    poolId:
      description: Ceph's numeric pool id.
      returned: always
      type: int
      sample: 3
    application:
      description: The application using the pool.
      returned: always
      type: str
      sample: rbd
    size:
      description: Number of replicas, or k+m for an erasure coded pool.
      returned: always
      type: int
      sample: 3
    minSize:
      description: Minimum number of replicas to serve I/O.
      returned: always
      type: int
      sample: 2
    pgNum:
      description: Number of placement groups.
      returned: always
      type: int
      sample: 128
    crushRule:
      description: Numeric id of the CRUSH rule.
      returned: always
      type: int
      sample: 1
    erasureCoding:
      description: Whether the pool is erasure coded.
      returned: always
      type: bool
      sample: false
    quotaMaxBytes:
      description: Byte quota, V(0) for unlimited.
      returned: always
      type: int
      sample: 0
    stats:
      description: Usage statistics of the pool, as croit reports them.
      returned: always
      type: dict
      sample: {}
    details:
      description: The pool's details as croit reports them (C(/pools/{name}/details)).
      returned: when O(details=true)
      type: dict
      sample: {}
    compression:
      description: The pool's compression settings (C(PoolCompressionSettings) in the croit API).
      returned: when O(details=true)
      type: dict
      sample:
        algorithm: Zstd
        mode: Aggressive
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
