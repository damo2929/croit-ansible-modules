#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /crush/rules
# croit-api: GET /crush/rules/classes
# croit-api: GET /crush/ec-profiles
# croit-api: GET /crush

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: crush_info
short_description: Read CRUSH rules, device classes, erasure code profiles and the CRUSH tree
version_added: 0.1.0
description:
  - Reads the CRUSH configuration of a croit cluster - its CRUSH rules, the device classes of its OSDs,
    its erasure code profiles and, on request, the CRUSH hierarchy.
  - Each rule is returned with an added C(layout) that expresses it in M(croit.ceph.crush_rule) options,
    which makes it easy to pick a rule by device class or failure domain.
  - This module never changes anything.
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
  gather:
    description:
      - What to read. Only the listed parts are requested from croit and returned.
      - V(rules) is every CRUSH rule with its steps, plus the layout M(croit.ceph.crush_rule) compares.
      - V(classes) is the device classes the cluster's OSDs carry.
      - V(ec_profiles) is the erasure code profiles, by name.
      - V(tree) is the CRUSH hierarchy with sizes, utilisation and placement groups. It can be large,
        so it is not gathered by default.
    type: list
    elements: str
    choices: [rules, classes, ec_profiles, tree]
    default: [rules, classes, ec_profiles]
seealso:
  - module: croit.ceph.crush_rule
    description: Create and delete CRUSH rules.
  - module: croit.ceph.pool
    description: Place pools with a CRUSH rule.
  - module: croit.ceph.osd
    description: Manage the OSDs in the CRUSH hierarchy.
  - name: croit API reference
    description: The croit REST API, including the C(/crush) endpoints.
    link: https://www.croit.io/api-docs
  - name: CRUSH maps
    description: Upstream documentation of CRUSH maps and rules.
    link: https://docs.ceph.com/en/latest/rados/operations/crush-map/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Read rules, classes and EC profiles
  croit.ceph.crush_info:
  register: crush

- name: Ids of all rules on SSDs
  ansible.builtin.debug:
    msg: "{{ crush.rules | selectattr('layout.device_class', 'defined') | selectattr('layout.device_class', 'equalto', 'ssd') | map(attribute='id') | list }}"

- name: Make sure the cluster has NVMe OSDs before creating a rule for them
  ansible.builtin.assert:
    that: "'nvme' in crush.classes"

- name: Read the CRUSH tree
  croit.ceph.crush_info:
    gather: [tree]
  register: tree

- name: List the hosts in the tree
  ansible.builtin.debug:
    msg: "{{ tree.tree.nodes | selectattr('type', 'equalto', 'HOST') | map(attribute='name') | list }}"
"""

RETURN = r"""
rules:
  description:
    - CRUSH rules (C(CrushRuleResponse) in the croit API), each with an added C(layout) key.
  returned: when V(rules) is gathered
  type: list
  elements: dict
  contains:
    id:
      description: The rule's id, which pools refer to.
      returned: always
      type: int
      sample: 1
    name:
      description: The rule's name.
      returned: always
      type: str
      sample: replicated_ssd
    type:
      description: C(REPLICATED) or C(ERASURE).
      returned: always
      type: str
      sample: REPLICATED
    steps:
      description: The rule's steps in order, each with C(op) and, depending on it, C(bucket), C(deviceClass), C(bucketType) and C(num).
      returned: always
      type: list
      elements: dict
      sample: [{op: TAKE, bucket: default, deviceClass: ssd}, {op: CHOOSELEAF, bucketType: host, num: 0}, {op: EMIT}]
    layout:
      description:
        - The rule as M(croit.ceph.crush_rule) options. C(type) is V(simple), V(ssd_primary), or V(custom) for
          layouts that module cannot create (then no other keys are present).
      returned: always
      type: dict
      sample: {type: simple, start_bucket: default, failure_domain: host, device_class: ssd, erasure_coding: false}
classes:
  description: Device classes of the cluster's OSDs.
  returned: when V(classes) is gathered
  type: list
  elements: str
  sample: [hdd, ssd]
ec_profiles:
  description: Erasure code profiles keyed by name (C(ErasureCodeProfileDump) in the croit API).
  returned: when V(ec_profiles) is gathered
  type: dict
  sample:
    default:
      k: 2
      m: 2
      plugin: jerasure
      technique: reed_sol_van
tree:
  description: The CRUSH hierarchy (C(CrushTree) in the croit API).
  returned: when V(tree) is gathered
  type: dict
  contains:
    nodes:
      description:
        - Every node of the hierarchy. Buckets have negative ids and list their C(children); OSDs carry
          C(deviceClass), C(reweight), C(status), C(size), C(used) and C(pgs).
      returned: always
      type: list
      elements: dict
      sample:
        - {id: -1, name: default, type: ROOT, children: [-2]}
        - {id: -2, name: node1, type: HOST, children: [0]}
        - {id: 0, name: osd.0, type: OSD, deviceClass: ssd, reweight: 1.0, status: UP, size: 960197124096, used: 52428800, pgs: 64}
    stray:
      description: OSDs that exist outside the hierarchy.
      returned: always
      type: list
      elements: dict
      sample: []
"""

from ansible_collections.croit.ceph.plugins.module_utils.crush import layout
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

# Same parsing as croit.ceph.crush_rule (modules cannot import each other); candidate for module_utils.
CHOICES = ["rules", "classes", "ec_profiles", "tree"]


def main():
    m = CroitModule(
        dict(gather=dict(type="list", elements="str", choices=CHOICES, default=["rules", "classes", "ec_profiles"])),
        wait=False,
        warnings=False,
    )
    gather = m.params["gather"]
    result = {}
    if "rules" in gather:
        rules = m.get_list("/crush/rules")
        for rule in rules:
            rule["layout"] = layout(rule)
        result["rules"] = rules
    if "classes" in gather:
        result["classes"] = m.get("/crush/rules/classes") or []
    if "ec_profiles" in gather:
        result["ec_profiles"] = m.get("/crush/ec-profiles") or {}
    if "tree" in gather:
        result["tree"] = m.get("/crush") or {}
    m.exit(changed=False, **result)


if __name__ == "__main__":
    main()
