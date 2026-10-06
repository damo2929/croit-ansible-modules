#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/smb
# croit-api: GET /services/smb/{serviceId}/users
# croit-api: POST /services/smb/{serviceId}/users
# croit-api: DELETE /services/smb/{serviceId}/users/{userId}
# croit-api: PUT /services/smb/{serviceId}/users/{userId}/groups
# croit-api: POST /services/smb/{serviceId}/users/{userId}/password
# croit-api: GET /services/smb/{serviceId}/groups

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: smb_user
short_description: Manage local users of an SMB gateway cluster on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete the managed local users of a croit SMB cluster.
  - Managed local users exist only on generation-2 clusters without Active Directory; the module fails on
    any other cluster.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  cluster:
    description:
      - The SMB cluster, by name (croit's description) or numeric service id.
    type: str
    required: true
  name:
    description:
      - User name. A lowercase POSIX name (a-z, 0-9, C(_), C(-), not starting with a digit or C(-)), at most
        32 characters.
    type: str
    required: true
  state:
    description:
      - Whether the user should exist.
      - V(absent) deletes the user and its SMB password. No data is deleted, but NT ACL entries naming the
        user keep its old SID and become dangling, as on Windows.
    type: str
    choices: [present, absent]
    default: present
  uid:
    description:
      - Unix uid of the user, to align it with an external system. croit derives one when not set.
      - Fixed once the user exists.
    type: int
  groups:
    description:
      - The complete list of managed local groups the user is a member of, by name. Compared as a set.
    type: list
    elements: str
  password:
    description:
      - SMB password of the user. Never stored by croit, so it cannot be compared; see O(update_password).
      - Never returned or shown in diffs.
    type: str
  update_password:
    description:
      - V(on_create) sets O(password) only when the user is created.
      - V(always) sets it on every run, which always reports a change.
    type: str
    choices: [on_create, always]
    default: on_create
"""

EXAMPLES = r"""
- name: SMB user in two groups
  croit.ceph.smb_user:
    cluster: smb-office
    name: alice
    groups: [staff, projects]
    password: "{{ vault_alice_password }}"

- name: Rotate a password
  croit.ceph.smb_user:
    cluster: smb-office
    name: alice
    password: "{{ vault_alice_new_password }}"
    update_password: always

- name: Remove a user
  croit.ceph.smb_user:
    cluster: smb-office
    name: alice
    state: absent
"""

RETURN = r"""
user:
  description:
    - The user as croit reports it after the change (C(SmbUserResponse) in the croit API), with an added
      C(groups) list of group names.
    - Before the change in check mode; empty when the user does not exist.
  returned: always
  type: dict
  sample:
    id: 4
    username: alice
    uid: 1004
    groupIds: [2]
    groups: [staff]
task:
  description: The last croit background task the change ran as, when there was one.
  returned: when a task ran
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.smb import require_cluster, require_managed_accounts

MASK = "********"


class SmbUserModule(CroitModule):
    def __init__(self):
        super(SmbUserModule, self).__init__(
            dict(
                cluster=dict(type="str", required=True),
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                uid=dict(type="int"),
                groups=dict(type="list", elements="str"),
                password=dict(type="str", no_log=True),
                update_password=dict(type="str", default="on_create", choices=["on_create", "always"], no_log=False),
            ),
            warnings=False,
        )
        self.tasks = []

    def users(self):
        return self.get_list(self.base + "/users")

    def find_user(self):
        for user in self.users():
            if user.get("username") == self.params["name"]:
                return user
        return None

    def with_names(self, user):
        if not user:
            return {}
        names = dict((g["id"], g.get("groupname")) for g in self.groups)
        result = dict(user)
        result["groups"] = sorted(names.get(i, str(i)) for i in user.get("groupIds") or [])
        return result

    def view(self, user):
        if not user:
            return {}
        return dict(uid=user.get("uid"), groups=self.with_names(user)["groups"])

    def group_ids(self):
        wanted = self.params["groups"]
        if wanted is None:
            return None
        ids = dict((g.get("groupname"), g["id"]) for g in self.groups)
        unknown = sorted(set(g for g in wanted if g not in ids))
        if unknown:
            self.module.fail_json(
                msg="Unknown SMB group(s) %s on cluster %r. Known groups: %s"
                % (", ".join(unknown), self.config.get("description"), ", ".join(sorted(ids)) or "none")
            )
        return sorted(set(ids[g] for g in wanted))

    def record(self, data):
        task = self.handle_task(data)
        if task is not None:
            self.tasks.append(task)

    def finish(self, changed, before, after, user):
        result = dict(changed=changed, before=before, after=after, user=user)
        if self.tasks:
            result["task"] = self.tasks[-1]
        self.exit(**result)

    def run(self):
        p = self.params
        self.config = require_cluster(self, p["cluster"])
        require_managed_accounts(self, self.config, "users")
        self.base = path_join("services", "smb", self.config["serviceId"])
        self.groups = self.get_list(self.base + "/groups")
        user = self.find_user()

        if p["state"] == "absent":
            if user is None:
                self.exit(changed=False, user={})
            if not self.check_mode:
                self.record(self.write("DELETE", path_join("services", "smb", self.config["serviceId"], "users", user["id"])))
            self.finish(True, self.view(user), {}, {})

        group_ids = self.group_ids()
        if user is None:
            return self.create(group_ids)
        return self.update(user, group_ids)

    def create(self, group_ids):
        p = self.params
        body = dict(username=p["name"])
        if p["uid"] is not None:
            body["uid"] = p["uid"]
        if group_ids is not None:
            body["groupIds"] = group_ids
        if p["password"] is not None:
            body["password"] = p["password"]
        else:
            self.module.warn("SMB user %r is created without a password and cannot log in until one is set" % p["name"])
        names = dict((g["id"], g.get("groupname")) for g in self.groups)
        after = dict(uid=p["uid"], groups=sorted(names[i] for i in group_ids or []))
        if p["password"] is not None:
            after["password"] = MASK
        if self.check_mode:
            self.finish(True, {}, after, {})
        self.record(self.write("POST", self.base + "/users", body=body))
        self.finish(True, {}, after, self.with_names(self.find_user()))

    def update(self, user, group_ids):
        p = self.params
        if p["uid"] is not None and p["uid"] != user.get("uid"):
            self.module.fail_json(
                msg="uid of SMB user %r is %s and cannot be changed to %s" % (p["name"], user.get("uid"), p["uid"])
            )
        before = self.view(user)
        after = dict(before)
        groups_changed = group_ids is not None and group_ids != sorted(user.get("groupIds") or [])
        if groups_changed:
            names = dict((g["id"], g.get("groupname")) for g in self.groups)
            after["groups"] = sorted(names[i] for i in group_ids)
        password_changed = p["password"] is not None and p["update_password"] == "always"
        if password_changed:
            before["password"] = MASK
            after["password"] = MASK + " (changed)"
        changed = groups_changed or password_changed
        if not changed or self.check_mode:
            self.finish(changed, before, after, self.with_names(user))
        user_path = path_join("services", "smb", self.config["serviceId"], "users", user["id"])
        if groups_changed:
            self.write("PUT", user_path + "/groups", body=dict(groupIds=group_ids))
        if password_changed:
            self.record(self.write("POST", user_path + "/password", body=dict(password=p["password"])))
        self.finish(True, before, after, self.with_names(self.find_user()))


def main():
    SmbUserModule().run()


if __name__ == "__main__":
    main()
