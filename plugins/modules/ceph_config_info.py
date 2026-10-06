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
  - Returns the Ceph options an operator changed away from their default, one row per section and mask.
  - With O(available=true) it instead returns every option the cluster's Ceph release documents, each with
    what the cluster configured for it.
  - O(name) and O(section) filter the rows. The module never changes anything.
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
      - Only return rows for this option, for example V(osd_max_backfills).
      - Underscores and spaces are treated alike. When not set, rows for every option are returned.
    type: str
  section:
    description:
      - Only return rows for this section, for example V(global), V(osd) or V(osd.12).
      - When not set, rows for every section are returned.
    type: str
  available:
    description:
      - With V(true), return every option the cluster's Ceph release documents (around two thousand rows),
        each with what the cluster configured for it.
      - With V(false), return only the options changed away from their default. Options croit holds at its own
        default are only listed with V(true).
    type: bool
    default: false
seealso:
  - module: croit.ceph.ceph_config
    description: Set, pin or unset a Ceph option.
  - module: croit.ceph.setting_info
    description: Read croit's own settings.
  - name: croit API reference
    description: The C(/config) and C(/config/available) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph configuration
    description: How Ceph's monitor configuration database, sections and masks work.
    link: https://docs.ceph.com/en/latest/rados/configuration/ceph-conf/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Options changed from their defaults
  croit.ceph.ceph_config_info:
  register: changed_options

- name: List the changed options
  ansible.builtin.debug:
    msg: "{{ item.name }} [{{ item.section }}] = {{ item.currentValue }}"
  loop: "{{ changed_options.config }}"

- name: Everything about one option, including its defaults
  croit.ceph.ceph_config_info:
    name: osd_memory_target
    available: true
  register: memory_target

- name: Only the OSD section
  croit.ceph.ceph_config_info:
    section: osd
"""

RETURN = r"""
config:
  description: The option rows (C(CephConfigResponse) in the croit API), one per configured section and mask.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: The option name, spelled with spaces as croit stores it.
      returned: always
      type: str
      sample: osd max backfills
    section:
      description: The Ceph section the value applies to.
      returned: always
      type: str
      sample: osd
    mask:
      description: The mask narrowing the section, empty for the whole section.
      returned: always
      type: str
      sample: ""
    currentValue:
      description: What the option is set to, or Ceph's default where nothing sets it.
      returned: always
      type: raw
      sample: 2
    defaultValue:
      description: What Ceph uses when nothing sets the option.
      returned: always
      type: raw
      sample: 1
    customized:
      description: Whether an operator set the value, as opposed to croit's or Ceph's default.
      returned: always
      type: bool
      sample: true
    useCroitDefault:
      description: Whether the option is pinned to croit's default.
      returned: always
      type: bool
      sample: false
    useCephDefault:
      description: Whether the option is pinned to Ceph's default.
      returned: always
      type: bool
      sample: false
    canUpdateAtRuntime:
      description: Whether Ceph applies a change without restarting the daemon; null when unknown.
      returned: always
      type: bool
      sample: true
    description:
      description: What Ceph documents the option as.
      returned: always
      type: str
      sample: Maximum number of concurrent backfills to or from a single OSD
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
