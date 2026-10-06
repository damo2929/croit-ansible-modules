#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /s3/users
# croit-api: GET /s3/users/{uid}/buckets

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: s3_user_info
short_description: Read S3 (RGW) users of a croit cluster
version_added: 0.1.0
description:
  - Returns S3 users with their subusers and quotas. Access and secret keys are never returned.
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
  uids:
    description:
      - User ids to return, tenant-qualified as C(tenant$uid) where needed. Unknown ids are left out.
      - When not set, every user is returned.
    type: list
    elements: str
  include_buckets:
    description:
      - Also return the buckets each user owns, read live from the cluster. Costs one request per user.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: All S3 users
  croit.ceph.s3_user_info:
  register: s3_users

- name: One user with their buckets
  croit.ceph.s3_user_info:
    uids: [backup]
    include_buckets: true
"""

RETURN = r"""
users:
  description:
    - The users (C(RgwUserResponse) in the croit API).
    - With O(include_buckets=true), each user also has a C(buckets) list (C(RgwBucketResponse)).
  returned: always
  type: list
  elements: dict
  sample:
    - uid: backup
      name: Backup service
      email: ""
      suspended: false
      subusers: []
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            uids=dict(type="list", elements="str"),
            include_buckets=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    uids = m.params["uids"]
    users = m.get_list("/s3/users", query=dict(uid=uids) if uids else None)
    if uids:
        users = [u for u in users if u.get("uid") in uids]
    if m.params["include_buckets"]:
        for user in users:
            user["buckets"] = m.get_list(path_join("s3", "users", user["uid"], "buckets"))
    m.exit(changed=False, users=users)


if __name__ == "__main__":
    main()
