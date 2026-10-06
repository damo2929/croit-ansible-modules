#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /server-access/keys
# croit-api: PUT /server-access/keys

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: server_ssh_keys
short_description: Manage the SSH keys allowed on croit-managed servers
version_added: 0.1.0
description:
  - Manages the list of public SSH keys croit installs for C(root) on every server it manages.
  - croit stores the list as a whole. The module reads it, adds or removes the given keys and writes the result
    back only when it differs, so keys added in the croit UI are kept unless O(exclusive=true).
  - Keys are matched by their type and key data (for example C(ssh-ed25519 AAAA...)). Options in front of the
    key and the trailing comment are ignored when matching, so a key whose comment differs is not changed. To
    change a comment, remove the key and add it again.
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
    details:
      - The diff shows the complete key list before and after.
options:
  keys:
    description:
      - Public keys in C(authorized_keys) format, one key per entry.
      - Duplicate keys (same type and key data) are added once. Empty entries fail the task.
    type: list
    elements: str
    required: true
  state:
    description:
      - V(present) makes sure the keys are allowed, adding the missing ones at the end of the list.
      - V(absent) makes sure they are not, removing every entry with the same type and key data.
    type: str
    choices: [present, absent]
    default: present
  exclusive:
    description:
      - With O(state=present), remove every key that is not in O(keys), so the list is exactly O(keys).
      - An empty O(keys) with O(exclusive=true) removes every key.
      - Not valid with O(state=absent).
    type: bool
    default: false
notes:
  - Removing the last key you can log in with leaves only croit's own access to the servers.
seealso:
  - module: croit.ceph.server
    description: Manage the servers these keys are installed on.
  - module: croit.ceph.hook_script
    description: Run scripts on the servers, for example to install further keys for other users.
  - name: croit API reference
    description: The C(/server-access/keys) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Allow the ops team's keys
  croit.ceph.server_ssh_keys:
    keys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyAlice alice@ops
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyBob bob@ops
  register: allowed

- name: Show how many keys are allowed
  ansible.builtin.debug:
    msg: "{{ allowed.ssh_keys | length }} keys are allowed on the servers"

- name: Exactly these keys, nothing else
  croit.ceph.server_ssh_keys:
    keys: "{{ ops_ssh_keys }}"
    exclusive: true

- name: Revoke a key (the comment does not matter)
  croit.ceph.server_ssh_keys:
    keys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyBob
    state: absent
"""

RETURN = r"""
ssh_keys:
  description:
    - The keys croit has after the change. In check mode, the keys before the change.
    - Named C(ssh_keys) rather than C(keys), which would clash with the C(keys()) method in Jinja.
  returned: always
  type: list
  elements: str
  sample:
    - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyAlice alice@ops
"""

import re

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

_KEY_TYPE = re.compile(r"^(ssh-[a-z0-9-]+|ecdsa-sha2-[a-z0-9-]+|sk-[a-z0-9@.-]+)$")


def identity(key):
    """(type, data) of an authorized_keys line, ignoring options and comment.

    Lines that cannot be parsed are identified by their whitespace-normalised text.
    """
    tokens = key.split()
    for i, token in enumerate(tokens[:-1]):
        if _KEY_TYPE.match(token):
            return (token, tokens[i + 1])
    return (" ".join(tokens),)


def run(m):
    p = m.params
    if p["exclusive"] and p["state"] == "absent":
        m.module.fail_json(msg="exclusive can only be used with state=present")

    current = m.get("/server-access/keys") or []
    current_ids = [identity(k) for k in current]

    wanted = []
    wanted_ids = []
    for key in p["keys"]:
        if not key.strip():
            m.module.fail_json(msg="keys must not contain empty entries")
        key_id = identity(key)
        if key_id not in wanted_ids:
            wanted.append(key.strip())
            wanted_ids.append(key_id)

    if p["state"] == "absent":
        new = [k for k, k_id in zip(current, current_ids) if k_id not in wanted_ids]
    else:
        if p["exclusive"]:
            new = [k for k, k_id in zip(current, current_ids) if k_id in wanted_ids]
        else:
            new = list(current)
        new_ids = [identity(k) for k in new]
        new.extend(k for k, k_id in zip(wanted, wanted_ids) if k_id not in new_ids)

    changed = new != current
    if not changed or m.check_mode:
        m.exit(changed=changed, before=dict(keys=current), after=dict(keys=new), ssh_keys=current)
    m.write("PUT", "/server-access/keys", body=dict(keys=new))
    m.exit(changed=True, before=dict(keys=current), after=dict(keys=new), ssh_keys=m.get("/server-access/keys") or [])


def main():
    m = CroitModule(
        dict(
            keys=dict(type="list", elements="str", required=True, no_log=False),
            state=dict(type="str", default="present", choices=["present", "absent"]),
            exclusive=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    run(m)


if __name__ == "__main__":
    main()
