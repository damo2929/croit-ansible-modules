#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /s3/users
# croit-api: GET /s3/users/{uid}/subusers
# croit-api: POST /s3/users/{uid}
# croit-api: PATCH /s3/users/{uid}/subusers/{subuser}
# croit-api: DELETE /s3/users/{uid}/subusers/{subuser}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: s3_subuser
short_description: Manage subusers of an S3 (RGW) user on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete one subuser of an S3 user, and set what it may do.
  - Keys of a subuser are managed with M(croit.ceph.s3_user_key) and O(croit.ceph.s3_user_key#module:subuser).
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
options:
  uid:
    description:
      - The owning S3 user, tenant-qualified as C(tenant$uid) where needed. The user must exist.
    type: str
    required: true
  subuser:
    description:
      - The subuser's name, without the C(uid:) prefix.
    type: str
    required: true
  state:
    description:
      - Whether the subuser should exist. Deleting a subuser also deletes its keys.
    type: str
    choices: [present, absent]
    default: present
  permissions:
    description:
      - What the subuser may do. When a subuser is created without it, it gets V(none).
    type: str
    choices: [none, read, write, read-write, full-control]
"""

EXAMPLES = r"""
- name: Read-only subuser for monitoring
  croit.ceph.s3_subuser:
    api_url: https://croit-mgmt/api
    api_token: "{{ vault_croit_token }}"
    uid: backup
    subuser: monitor
    permissions: read

- name: Remove a subuser and its keys
  croit.ceph.s3_subuser:
    uid: backup
    subuser: monitor
    state: absent
"""

RETURN = r"""
subuser:
  description:
    - The subuser as croit reports it after the change (C(RgwSubUser) in the croit API), with C(id) as C(uid:subuser).
    - Before the change in check mode; empty when the subuser does not exist.
  returned: always
  type: dict
  sample:
    id: backup:monitor
    permissions: read
task:
  description: The croit background task the change ran as, when there was one.
  returned: when a task ran
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

# Ansible choice -> croit enum.
PERMISSIONS = {
    "none": "NONE",
    "read": "read",
    "write": "write",
    "read-write": "read-write",
    "full-control": "full-control",
}


def permission_of(subuser):
    """croit reports no permission as null or NONE; compare both as NONE."""
    return (subuser or {}).get("permissions") or "NONE"


def view(subuser):
    if not subuser:
        return {}
    return dict(permissions=permission_of(subuser))


class S3SubuserModule(CroitModule):
    def __init__(self):
        super(S3SubuserModule, self).__init__(
            dict(
                uid=dict(type="str", required=True),
                subuser=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                permissions=dict(type="str", choices=list(PERMISSIONS)),
            ),
        )

    def run(self):
        p = self.params
        uid, name = p["uid"], p["subuser"]
        if ":" in name:
            self.module.fail_json(msg="subuser must be the bare name, without the %r prefix" % (uid + ":"))
        full_id = "%s:%s" % (uid, name)

        if not any(u.get("uid") == uid for u in self.get_list("/s3/users", query=dict(uid=[uid]))):
            if p["state"] == "absent":
                self.exit(changed=False, subuser={})
            self.module.fail_json(msg="S3 user %r does not exist" % uid)

        current = None
        for subuser in self.get_list(path_join("s3", "users", uid, "subusers")):
            if subuser.get("id") == full_id:
                current = subuser
                break
        sub_path = path_join("s3", "users", uid, "subusers", name)

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, subuser={})
            task = None
            if not self.check_mode:
                task = self.handle_task(self.write("DELETE", sub_path))
            self.exit(changed=True, before=view(current), after={}, subuser={}, **self.task_result(task))

        wanted = PERMISSIONS[p["permissions"]] if p["permissions"] else None
        if current is None:
            after = dict(permissions=wanted or "NONE")
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, subuser={})
            body = dict(subuser=name, permissions=wanted)
            task = self.handle_task(self.write("POST", path_join("s3", "users", uid), body=body))
            self.exit(changed=True, before={}, after=after, subuser=self.read(uid, full_id), **self.task_result(task))

        before = view(current)
        if wanted is None or wanted == permission_of(current):
            self.exit(changed=False, before=before, after=before, subuser=current)
        after = dict(permissions=wanted)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, subuser=current)
        task = self.handle_task(self.write("PATCH", sub_path, body=dict(permissions=wanted)))
        self.exit(changed=True, before=before, after=after, subuser=self.read(uid, full_id), **self.task_result(task))

    def read(self, uid, full_id):
        for subuser in self.get_list(path_join("s3", "users", uid, "subusers")):
            if subuser.get("id") == full_id:
                return subuser
        return {}

    @staticmethod
    def task_result(task):
        return dict(task=task) if task is not None else {}


def main():
    S3SubuserModule().run()


if __name__ == "__main__":
    main()
