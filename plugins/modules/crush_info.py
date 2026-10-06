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
  - Reads the CRUSH configuration of a croit cluster.
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
      - What to read.
      - V(rules) is every CRUSH rule with its steps, plus the layout croit.ceph.crush_rule compares.
      - V(classes) is the device classes the cluster's OSDs carry.
      - V(ec_profiles) is the erasure code profiles, by name.
      - V(tree) is the CRUSH hierarchy with sizes, utilisation and placement groups. It can be large,
        so it is not gathered by default.
    type: list
    elements: str
    choices: [rules, classes, ec_profiles, tree]
    default: [rules, classes, ec_profiles]
"""

EXAMPLES = r"""
- name: Read rules, classes and EC profiles
  croit.ceph.crush_info:
  register: crush

- name: Ids of all rules on SSDs
  ansible.builtin.debug:
    msg: "{{ crush.rules | selectattr('layout.device_class', 'equalto', 'ssd') | map(attribute='id') | list }}"

- name: Read the CRUSH tree
  croit.ceph.crush_info:
    gather: [tree]
  register: tree
"""

RETURN = r"""
rules:
  description:
    - CRUSH rules (C(CrushRuleResponse) in the croit API), each with an added C(layout) key holding the
      rule as croit.ceph.crush_rule options.
  returned: when V(rules) is gathered
  type: list
  elements: dict
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
