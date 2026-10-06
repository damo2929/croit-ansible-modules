#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/smb
# croit-api: GET /services/smb/{serviceId}/groups
# croit-api: POST /services/smb/{serviceId}/groups
# croit-api: DELETE /services/smb/{serviceId}/groups/{groupId}
# croit-api: GET /services/smb/{serviceId}/users

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: smb_group
short_description: Manage local groups of an SMB gateway cluster on a croit cluster
version_added: 0.1.0
description:
  - Create and delete the managed local groups of a croit SMB cluster. The gateway nodes register a group
    with Samba within seconds, so it can be used as an NT principal in Windows ACLs.
  - Group membership is managed on the user, with the O(croit.ceph.smb_user#module:groups) option of
    M(croit.ceph.smb_user).
  - Managed local groups exist only on generation-2 clusters without Active Directory; the module fails on
    any other cluster.
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
options:
  cluster:
    description:
      - The SMB cluster, by name (croit's description) or numeric service id.
    type: str
    required: true
  name:
    description:
      - Group name. A lowercase POSIX name (a-z, 0-9, C(_), C(-), not starting with a digit or C(-)), at most
        32 characters.
    type: str
    required: true
  state:
    description:
      - Whether the group should exist.
      - V(absent) deletes the group. No data is deleted, but NT ACL entries naming the group become dangling.
    type: str
    choices: [present, absent]
    default: present
  gid:
    description:
      - Unix gid of the group, to align it with an external system. croit derives one when not set.
      - Fixed once the group exists.
    type: int
"""

EXAMPLES = r"""
- name: SMB group
  croit.ceph.smb_group:
    cluster: smb-office
    name: staff

- name: Remove a group
  croit.ceph.smb_group:
    cluster: smb-office
    name: staff
    state: absent
"""

RETURN = r"""
group:
  description:
    - The group as croit reports it after the change (C(SmbGroupResponse) in the croit API), with an added
      C(members) list of user names.
    - Before the change in check mode; empty when the group does not exist.
  returned: always
  type: dict
  sample:
    id: 2
    groupname: staff
    gid: 1002
    memberIds: [4]
    members: [alice]
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.smb import require_cluster, require_managed_accounts


class SmbGroupModule(CroitModule):
    def __init__(self):
        super(SmbGroupModule, self).__init__(
            dict(
                cluster=dict(type="str", required=True),
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                gid=dict(type="int"),
            ),
            wait=False,
            warnings=False,
        )

    def find_group(self):
        for group in self.get_list(self.base + "/groups"):
            if group.get("groupname") == self.params["name"]:
                return group
        return None

    def with_members(self, group):
        if not group:
            return {}
        if group.get("memberIds"):
            names = dict((u["id"], u.get("username")) for u in self.get_list(self.base + "/users"))
        else:
            names = {}
        result = dict(group)
        result["members"] = sorted(names.get(i, str(i)) for i in group.get("memberIds") or [])
        return result

    def run(self):
        p = self.params
        config = require_cluster(self, p["cluster"])
        require_managed_accounts(self, config, "groups")
        self.base = path_join("services", "smb", config["serviceId"])
        group = self.find_group()

        if p["state"] == "absent":
            if group is None:
                self.exit(changed=False, group={})
            if not self.check_mode:
                self.write("DELETE", path_join("services", "smb", config["serviceId"], "groups", group["id"]))
            self.exit(changed=True, before=dict(gid=group.get("gid")), after={}, group={})

        if group is None:
            body = dict(groupname=p["name"])
            if p["gid"] is not None:
                body["gid"] = p["gid"]
            after = dict(gid=p["gid"])
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, group={})
            self.write("POST", self.base + "/groups", body=body)
            self.exit(changed=True, before={}, after=after, group=self.with_members(self.find_group()))

        if p["gid"] is not None and p["gid"] != group.get("gid"):
            self.module.fail_json(
                msg="gid of SMB group %r is %s and cannot be changed to %s" % (p["name"], group.get("gid"), p["gid"])
            )
        view = dict(gid=group.get("gid"))
        self.exit(changed=False, before=view, after=view, group=self.with_members(group))


def main():
    SmbGroupModule().run()


if __name__ == "__main__":
    main()
