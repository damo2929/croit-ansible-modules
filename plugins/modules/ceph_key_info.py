#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /keys

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: ceph_key_info
short_description: List Ceph keys (cephx users) on a croit cluster
version_added: 0.1.0
description:
  - Returns the cluster's Ceph keys with their capabilities and the comment croit keeps for each.
  - Secrets are only returned with O(show_secrets=true).
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
      - Only return the key with this fully qualified name, for example V(client.vms).
    type: str
  include_system_keys:
    description:
      - Also return ceph's and croit's own service keys.
      - Implied when O(name) is set, so that system keys can be looked up by name.
    type: bool
    default: false
  show_secrets:
    description:
      - Include each key's secret in RV(ceph_keys[].key). Needs an API token with the C(admin) role.
      - The result then contains secrets; keep it out of logs (for example with C(no_log) on the task).
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: All client keys
  croit.ceph.ceph_key_info:
  register: result

- name: One key
  croit.ceph.ceph_key_info:
    name: client.vms
  register: vms
"""

RETURN = r"""
ceph_keys:
  description:
    - The keys (C(CephUserResponse) in the croit API).
    - Named C(ceph_keys) rather than C(keys) because C(result.keys) is a method in Jinja.
  returned: always
  type: list
  elements: dict
  contains:
    user:
      description: The ceph entity.
      type: str
      sample: client.vms
    comment:
      description: What croit was told the key is for.
      type: str
    rawPermissions:
      description: The capability strings ceph stores, per daemon type.
      type: dict
    permissions:
      description: The capabilities in the shape croit recognised them as.
      type: dict
    key:
      description: The secret.
      type: str
      returned: when O(show_secrets=true)
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            name=dict(type="str"),
            include_system_keys=dict(type="bool", default=False),
            show_secrets=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    p = m.params
    query = dict(includeSystemKeys=bool(p["include_system_keys"] or p["name"]))
    if p["show_secrets"]:
        query["showKeys"] = True
    keys = m.get_list("/keys", query=query)
    if p["name"]:
        keys = [k for k in keys if k.get("user") == p["name"]]
    if not p["show_secrets"]:
        keys = [dict((k, v) for k, v in key.items() if k != "key") for key in keys]
    m.exit(changed=False, ceph_keys=keys)


if __name__ == "__main__":
    main()
