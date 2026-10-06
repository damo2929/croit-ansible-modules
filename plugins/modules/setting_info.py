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
  - Returns the croit settings this cluster stores a value for, or every setting croit offers with
    O(available=true).
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
      - Only return the setting with this name.
    type: str
  available:
    description:
      - Return every setting croit offers, with its type, level, default and current value.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Settings changed on this cluster
  croit.ceph.setting_info:
  register: settings

- name: Everything croit offers
  croit.ceph.setting_info:
    available: true
  register: all_settings
"""

RETURN = r"""
settings:
  description: The settings (C(CroitSettingResponse) in the croit API).
  returned: always
  type: list
  elements: dict
  sample:
    - name: example setting
      type: BOOL
      level: SIMPLE
      value: "true"
      default: "false"
      customized: true
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
