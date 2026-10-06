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
  - Returns the cluster's Ceph keys (cephx users) with their capabilities and the comment croit keeps
    for each one.
  - By default ceph's and croit's own service keys are left out; see O(include_system_keys).
  - Secrets are never returned unless O(show_secrets=true). This module never changes anything.
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
      - When the key does not exist, RV(ceph_keys) is an empty list rather than an error.
    type: str
  include_system_keys:
    description:
      - Also return ceph's and croit's own service keys, such as C(client.admin).
      - Implied when O(name) is set, so that system keys can be looked up by name.
    type: bool
    default: false
  show_secrets:
    description:
      - Include each key's secret in RV(ceph_keys[].key). Needs an API token with the C(admin) role.
      - The result then contains secrets; keep it out of logs, for example with C(no_log) on the task.
    type: bool
    default: false
notes:
  - With O(show_secrets=true) the result contains every listed key's secret.
seealso:
  - module: croit.ceph.ceph_key
    description: Create, change and delete Ceph keys.
  - name: croit API reference
    description: The croit REST API, including C(GET /keys).
    link: https://www.croit.io/api-docs
  - name: Ceph user management
    description: Upstream documentation of cephx users and capabilities.
    link: https://docs.ceph.com/en/latest/rados/operations/user-management/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: All client keys
  croit.ceph.ceph_key_info:
  register: result

- name: Show the names of all client keys
  ansible.builtin.debug:
    msg: "{{ result.ceph_keys | map(attribute='user') | list }}"

- name: One key, including system keys such as client.admin
  croit.ceph.ceph_key_info:
    name: client.admin

- name: Every key with its secret, for a backup
  croit.ceph.ceph_key_info:
    include_system_keys: true
    show_secrets: true
  register: all_keys
  no_log: true
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
      description: The ceph entity name.
      returned: always
      type: str
      sample: client.vms
    comment:
      description: What croit was told the key is for.
      returned: always
      type: str
      sample: Hypervisors
    rawPermissions:
      description: The capability strings ceph stores, per daemon type. A daemon type without capabilities is null.
      returned: always
      type: dict
      sample:
        mon: profile rbd
        osd: profile rbd pool=vms
        mgr: null
        mds: null
    permissions:
      description: The capabilities in the structured shape croit recognised them as; C(type) says which.
      returned: always
      type: dict
      sample:
        type: RbdCephPermissions
    key:
      description: The secret.
      returned: when O(show_secrets=true)
      type: str
      sample: "********"
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
