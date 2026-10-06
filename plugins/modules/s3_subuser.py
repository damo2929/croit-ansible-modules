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
  - Create, update and delete one subuser of an S3 user, and set what it may do. The subuser is identified by
    O(uid) and the bare O(subuser) name.
  - When O(permissions) is not set, an existing subuser's permissions are left alone.
  - Keys of a subuser are managed with M(croit.ceph.s3_user_key) and its
    O(croit.ceph.s3_user_key#module:subuser) option.
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
      - The owning S3 user, tenant-qualified as C(tenant$uid) where the user has a tenant.
      - The user must exist for O(state=present). With O(state=absent), a missing user means there is nothing to remove.
    type: str
    required: true
  subuser:
    description:
      - The subuser's bare name, without the C(uid:) prefix. A name containing C(:) is refused.
    type: str
    required: true
  state:
    description:
      - Whether the subuser should exist.
      - V(absent) deletes the subuser together with all of its keys; clients using those keys lose access.
    type: str
    choices: [present, absent]
    default: present
  permissions:
    description:
      - What the subuser may do.
      - When a subuser is created without this option, it gets V(none). When unset for an existing subuser, its
        permissions are left alone.
    type: str
    choices: [none, read, write, read-write, full-control]
seealso:
  - module: croit.ceph.s3_user
    description: Create the S3 user a subuser belongs to.
  - module: croit.ceph.s3_user_key
    description: Manage the access keys of a subuser.
  - module: croit.ceph.s3_user_info
    description: Read S3 users together with their subusers.
  - name: croit API reference
    description: The croit REST API, including the C(/s3/users/{uid}/subusers) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph RGW administration guide
    description: Upstream documentation of RGW users and subusers.
    link: https://docs.ceph.com/en/latest/radosgw/admin/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Create a read-only subuser for monitoring
  croit.ceph.s3_subuser:
    uid: backup
    subuser: monitor
    permissions: read
  register: monitor

- name: Show the subuser's full id
  ansible.builtin.debug:
    msg: "Subuser {{ monitor.subuser.id }} has {{ monitor.subuser.permissions }} access"

- name: Let the subuser write as well
  croit.ceph.s3_subuser:
    uid: backup
    subuser: monitor
    permissions: read-write

- name: Remove the subuser and its keys
  croit.ceph.s3_subuser:
    uid: backup
    subuser: monitor
    state: absent
"""

RETURN = r"""
subuser:
  description:
    - The subuser as croit reports it after the change (C(RgwSubUser) in the croit API).
    - In check mode, the subuser as it was before. Empty when the subuser does not exist or was deleted.
  returned: always
  type: dict
  contains:
    id:
      description: The subuser's full id, C(uid:subuser).
      returned: when the subuser exists
      type: str
      sample: backup:monitor
    permissions:
      description: What the subuser may do, as croit reports it (V(NONE) or null for no permissions).
      returned: when the subuser exists
      type: str
      sample: read
task:
  description:
    - The croit background task the change ran as (C(ManagedTask) in the croit API).
    - With O(wait=true) this is the finished task; with O(wait=false) it may still be running.
  returned: when the change ran as a croit background task
  type: dict
  contains:
    id:
      description: The task's id, usable with M(croit.ceph.task) and M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as croit's task list shows it.
      returned: always
      type: str
      sample: Create S3 subuser
    state:
      description: The task's state, one of V(WAITING), V(RUNNING), V(FINISHED), V(FAILED) or V(CANCELED).
      returned: always
      type: str
      sample: FINISHED
    done:
      description: Whether the task has ended.
      returned: always
      type: bool
      sample: true
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: Creating user backup ... done
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
