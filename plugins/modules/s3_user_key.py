#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /s3/users/{uid}/keys
# croit-api: PUT /s3/users/{uid}/keys/{accessKey}
# croit-api: DELETE /s3/users/{uid}/keys/{accessKey}
# croit-api: GET /s3/users/{uid}/subusers/{subuser}/keys
# croit-api: PUT /s3/users/{uid}/subusers/{subuser}/keys/{accessKey}
# croit-api: DELETE /s3/users/{uid}/subusers/{subuser}/keys/{accessKey}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: s3_user_key
short_description: Manage S3 access keys of an S3 (RGW) user or subuser on a croit cluster
version_added: 0.1.0
description:
  - Ensures one S3 credential pair (access key and secret key) exists, or not, for an S3 user or one of
    its subusers.
  - croit reports the stored secret, so the secret is compared and only rewritten when it differs. Secrets
    are never returned or shown in a diff.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
    details:
      - Secrets are shown as masked placeholders, never as their value.
options:
  uid:
    description:
      - The S3 user the key belongs to, tenant-qualified as C(tenant$uid) where needed.
    type: str
    required: true
  subuser:
    description:
      - The subuser the key belongs to, as its bare name without the C(uid:) prefix.
      - When not set, the key belongs to the user itself.
    type: str
  access_key:
    description:
      - The access key. It must be unique across every S3 user of the cluster.
    type: str
    required: true
  secret_key:
    description:
      - The secret key. Required when the key does not exist yet.
      - When not set for an existing key, its secret is left alone.
    type: str
  state:
    description:
      - Whether the key should exist.
    type: str
    choices: [present, absent]
    default: present
  exclusive:
    description:
      - Remove every other key of the same user or subuser, so O(access_key) is its only key.
      - Useful for key rotation. Only valid with O(state=present).
    type: bool
    default: false
notes:
  - croit's API takes the secret as a query parameter, so it may appear in the access logs of proxies
    between Ansible and croit.
"""

EXAMPLES = r"""
- name: Key for the backup user
  croit.ceph.s3_user_key:
    api_url: https://croit-mgmt/api
    api_token: "{{ vault_croit_token }}"
    uid: backup
    access_key: BACKUPACCESSKEY0001
    secret_key: "{{ vault_backup_s3_secret }}"

- name: Rotate to a new key and remove all older ones
  croit.ceph.s3_user_key:
    uid: backup
    access_key: BACKUPACCESSKEY0002
    secret_key: "{{ vault_backup_s3_secret_new }}"
    exclusive: true

- name: Key for a subuser
  croit.ceph.s3_user_key:
    uid: backup
    subuser: monitor
    access_key: MONITORACCESSKEY01
    secret_key: "{{ vault_monitor_s3_secret }}"
"""

RETURN = r"""
key:
  description:
    - The key after the change, without its secret. Empty when it does not exist.
  returned: always
  type: dict
  sample:
    user: backup
    access_key: BACKUPACCESSKEY0001
task:
  description: The last croit background task the change ran as, when there was one.
  returned: when a task ran
  type: dict
removed_keys:
  description: Access keys removed because of O(exclusive=true) (or that would be, in check mode).
  returned: when O(exclusive=true)
  type: list
  elements: str
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

MASKED = "********"
MASKED_CHANGED = "******** (changed)"


def public(key):
    """A key without its secret."""
    if not key:
        return {}
    return dict(user=key.get("user"), access_key=key.get("access_key"))


class S3UserKeyModule(CroitModule):
    def __init__(self):
        super(S3UserKeyModule, self).__init__(
            dict(
                uid=dict(type="str", required=True),
                subuser=dict(type="str"),
                access_key=dict(type="str", required=True, no_log=False),
                secret_key=dict(type="str", no_log=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                exclusive=dict(type="bool", default=False),
            ),
        )

    def base(self):
        p = self.params
        if p["subuser"]:
            return ["s3", "users", p["uid"], "subusers", p["subuser"]]
        return ["s3", "users", p["uid"]]

    def keys(self, identity):
        segments = self.base() + ["keys"]
        return [k for k in self.get_list(path_join(*segments)) if k.get("user") == identity and k.get("access_key")]

    def run(self):
        p = self.params
        if p["subuser"] and ":" in p["subuser"]:
            self.module.fail_json(msg="subuser must be the bare name, without the uid: prefix")
        if p["exclusive"] and p["state"] == "absent":
            self.module.fail_json(msg="exclusive=true is only valid with state=present")
        identity = "%s:%s" % (p["uid"], p["subuser"]) if p["subuser"] else p["uid"]
        keys = self.keys(identity)
        current = None
        for key in keys:
            if key["access_key"] == p["access_key"]:
                current = key
        key_path = path_join(*(self.base() + ["keys", p["access_key"]]))

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, key={})
            result = dict(key={})
            if not self.check_mode:
                self.add_task(result, self.handle_task(self.write("DELETE", key_path)))
            self.exit(changed=True, before=self.diff_view(current), after={}, **result)

        result = dict(key=public(current))
        before = self.diff_view(current) if current else {}
        after = dict(before)
        set_secret = False
        if current is None:
            if not p["secret_key"]:
                self.module.fail_json(msg="secret_key is required to create access key %r" % p["access_key"])
            set_secret = True
            after = dict(user=identity, access_key=p["access_key"], secret_key=MASKED)
        elif p["secret_key"] is not None and p["secret_key"] != current.get("secret_key"):
            set_secret = True
            after["secret_key"] = MASKED_CHANGED

        others = [k["access_key"] for k in keys if k["access_key"] != p["access_key"]] if p["exclusive"] else []
        if p["exclusive"]:
            result["removed_keys"] = others
            before["other_access_keys"] = sorted(others)
            after["other_access_keys"] = []

        changed = set_secret or bool(others)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, **result)

        if set_secret:
            self.add_task(result, self.handle_task(self.write("PUT", key_path, query=dict(secretKey=p["secret_key"]))))
        for access_key in others:
            self.add_task(result, self.handle_task(self.write("DELETE", path_join(*(self.base() + ["keys", access_key])))))
        for key in self.keys(identity):
            if key["access_key"] == p["access_key"]:
                result["key"] = public(key)
        self.exit(changed=True, before=before, after=after, **result)

    @staticmethod
    def add_task(result, task):
        if task is not None:
            result["task"] = task

    @staticmethod
    def diff_view(key):
        view = public(key)
        view["secret_key"] = MASKED
        return view


def main():
    S3UserKeyModule().run()


if __name__ == "__main__":
    main()
