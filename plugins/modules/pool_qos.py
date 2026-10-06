#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /pools
# croit-api: GET /pools/{pool}/qos
# croit-api: POST /pools/{pool}/qos

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: pool_qos
short_description: Manage RBD QoS limits of a Ceph pool on a croit cluster
version_added: 0.1.0
description:
  - Sets and removes the RBD QoS limits of a pool. Every image in the pool inherits them, unless the image
    sets its own (see the O(croit.ceph.rbd#module:qos) option of M(croit.ceph.rbd)).
  - Only the limits named in O(limits) are managed, unless O(exclusive=true).
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
      - Name of the pool. It must exist.
    type: str
    required: true
  limits:
    description:
      - QoS limits keyed by the rbd config key croit lists for the pool, for example C(rbd_qos_iops_limit),
        C(rbd_qos_bps_limit), C(rbd_qos_read_iops_limit) or C(rbd_qos_write_bps_limit).
      - Values are integers. Byte limits also accept a binary unit such as V(100M). V(0) means no limit.
      - A null value removes the limit, so images fall back to ceph's default.
      - An unknown key fails the task and lists the keys croit offers.
    type: dict
    default: {}
  exclusive:
    description:
      - Remove every limit set on the pool that is not named in O(limits).
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Limit every image in the pool to 2000 IOPS and 200 MiB/s
  croit.ceph.pool_qos:
    pool: rbd-ssd
    limits:
      rbd_qos_iops_limit: 2000
      rbd_qos_bps_limit: 200M

- name: Remove one limit
  croit.ceph.pool_qos:
    pool: rbd-ssd
    limits:
      rbd_qos_bps_limit: null

- name: Remove every limit from the pool
  croit.ceph.pool_qos:
    pool: rbd-ssd
    exclusive: true
"""

RETURN = r"""
qos:
  description:
    - The pool's QoS settings after the change (C(QosCommandsResponse) in the croit API), one row per
      setting croit can limit. C(value) is null where no limit is set.
    - Before the change in check mode.
  returned: always
  type: list
  elements: dict
  sample:
    - setting:
        command: rbd_qos_iops_limit
        displayName: IOPS limit
        description: The desired limit of IO operations per second.
      value: 2000
      inherited: null
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.qos import (
    qos_apply,
    qos_changes,
    qos_current,
    qos_desired,
    qos_set_limits,
)


def main():
    m = CroitModule(
        dict(
            pool=dict(type="str", required=True),
            limits=dict(type="dict", default={}),
            exclusive=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    pool = m.params["pool"]
    if not any(p.get("name") == pool for p in m.get_list("/pools")):
        m.module.fail_json(msg="Pool %r does not exist" % pool)

    qos_path = path_join("pools", pool, "qos")
    rows = m.get_list(qos_path)
    current = qos_current(rows)
    desired = qos_desired(m, m.params["limits"])
    changes = qos_changes(m, current, desired, exclusive=m.params["exclusive"])

    before = qos_set_limits(current)
    after = dict(current)
    after.update(changes)
    after = qos_set_limits(after)

    if not changes:
        m.exit(changed=False, before=before, after=after, qos=rows)
    if m.check_mode:
        m.exit(changed=True, before=before, after=after, qos=rows)

    qos_apply(m, qos_path, changes)
    m.exit(changed=True, before=before, after=after, qos=m.get_list(qos_path))


if __name__ == "__main__":
    main()
