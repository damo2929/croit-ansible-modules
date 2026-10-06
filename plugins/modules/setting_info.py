#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /settings
# croit-api: GET /settings/available

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: setting_info
short_description: Read croit settings
version_added: 0.1.0
description:
  - Returns the croit settings this cluster stores a value for.
  - With O(available=true) it returns every setting croit offers, with its type, level, default and current
    value, which is how to find the names M(croit.ceph.setting) accepts.
  - The module never changes anything.
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
      - Only return the setting with this exact name. When not set, every matching setting is returned.
    type: str
  available:
    description:
      - With V(true), return every setting croit offers, stored or not.
      - With V(false), return only the settings this cluster stores a value for; a cluster nobody configured
        returns an empty list.
    type: bool
    default: false
seealso:
  - module: croit.ceph.setting
    description: Store or reset a croit setting.
  - module: croit.ceph.ceph_config_info
    description: Read Ceph options rather than croit settings.
  - name: croit API reference
    description: The C(/settings) and C(/settings/available) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Settings changed on this cluster
  croit.ceph.setting_info:
  register: settings

- name: Show them
  ansible.builtin.debug:
    msg: "{{ item.name }} = {{ item.value }}"
  loop: "{{ settings.settings }}"

- name: Everything croit offers
  croit.ceph.setting_info:
    available: true
  register: all_settings

- name: Names of the settings shown on the simple settings page
  ansible.builtin.debug:
    msg: "{{ all_settings.settings | selectattr('level', 'equalto', 'SIMPLE') | map(attribute='name') | list }}"
"""

RETURN = r"""
settings:
  description: The settings (C(CroitSettingResponse) in the croit API).
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: What the setting is called, as croit's settings list shows it.
      returned: always
      type: str
      sample: example setting
    type:
      description: What the value holds, one of C(STRING), C(INT) or C(BOOL).
      returned: always
      type: str
      sample: BOOL
    level:
      description: How prominently croit offers the setting, one of C(SIMPLE), C(ADVANCED) or C(DEBUG).
      returned: always
      type: str
      sample: SIMPLE
    value:
      description: What the setting is worth on this cluster, as a string; its default where nothing is stored.
      returned: always
      type: str
      sample: "true"
    default:
      description: What the setting is worth when nothing is stored, as a string.
      returned: always
      type: str
      sample: "false"
    customized:
      description: Whether this cluster stores a value for the setting.
      returned: always
      type: bool
      sample: true
    description:
      description: What the setting does, and what changing it costs.
      returned: always
      type: str
      sample: Enables the example behaviour.
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(name=dict(type="str"), available=dict(type="bool", default=False)),
        wait=False,
        warnings=False,
    )
    settings = m.get_list("/settings/available" if m.params["available"] else "/settings")
    if m.params["name"] is not None:
        settings = [s for s in settings if s.get("name") == m.params["name"]]
    m.exit(changed=False, settings=settings)


if __name__ == "__main__":
    main()
