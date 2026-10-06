#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /config
# croit-api: GET /config/available

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: ceph_config_info
short_description: Read Ceph configuration options from a croit cluster
version_added: 0.1.0
description:
  - Returns the Ceph options an operator changed away from their default, or every option Ceph documents
    with O(available=true).
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
      - Only return rows for this option. Underscores and spaces are treated alike.
    type: str
  section:
    description:
      - Only return rows for this section, for example V(global) or V(osd).
    type: str
  available:
    description:
      - Return every option the cluster's Ceph release documents (around two thousand rows), each with what
        the cluster configured for it, instead of only the changed ones.
      - Options croit holds at its own default are only listed with V(true).
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Options changed from their defaults
  croit.ceph.ceph_config_info:
  register: changed_options

- name: Everything about one option
  croit.ceph.ceph_config_info:
    name: osd_memory_target
    available: true
  register: memory_target
"""

RETURN = r"""
config:
  description: The option rows (C(CephConfigResponse) in the croit API), one per configured section and mask.
  returned: always
  type: list
  elements: dict
  sample:
    - name: osd max backfills
      section: osd
      mask: ""
      currentValue: 2
      defaultValue: 1
      customized: true
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def normalise_name(name):
    return " ".join(name.replace("_", " ").split()).lower()


def main():
    m = CroitModule(
        dict(
            name=dict(type="str"),
            section=dict(type="str"),
            available=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    p = m.params
    rows = m.get_list("/config/available" if p["available"] else "/config")
    if p["name"] is not None:
        wanted = normalise_name(p["name"])
        rows = [r for r in rows if normalise_name(r.get("name", "")) == wanted]
    if p["section"] is not None:
        rows = [r for r in rows if (r.get("section") or "global") == p["section"]]
    m.exit(changed=False, config=rows)


if __name__ == "__main__":
    main()
