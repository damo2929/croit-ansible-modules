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
  - Returns the S3 users of the Ceph object gateway with their subusers and quotas, either all of them or the
    ones named in O(uids).
  - Access and secret keys are never returned. This module never changes anything.
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
      - User ids to return, tenant-qualified as C(tenant$uid) where the user has a tenant.
      - Ids croit does not know are left out of the result rather than failing.
      - When not set, every user is returned.
    type: list
    elements: str
  include_buckets:
    description:
      - Also return the buckets each user owns, read live from the cluster.
      - This costs one extra request per user, so prefer it together with O(uids) on large clusters.
    type: bool
    default: false
seealso:
  - module: croit.ceph.s3_user
    description: Create, update and delete S3 users.
  - module: croit.ceph.s3_bucket_info
    description: Read S3 buckets with their ACL, versioning and policy.
  - name: croit API reference
    description: The croit REST API, including the C(/s3/users) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph RGW administration guide
    description: Upstream documentation of RGW users and quotas.
    link: https://docs.ceph.com/en/latest/radosgw/admin/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Read every S3 user
  croit.ceph.s3_user_info:
  register: s3_users

- name: List the suspended users
  ansible.builtin.debug:
    msg: "{{ s3_users.users | selectattr('suspended') | map(attribute='uid') | list }}"

- name: Read one user together with the buckets it owns
  croit.ceph.s3_user_info:
    uids:
      - backup
    include_buckets: true
  register: backup_user

- name: Show how many buckets the user owns
  ansible.builtin.debug:
    msg: "backup owns {{ backup_user.users[0].buckets | length }} bucket(s)"
  when: backup_user.users | length > 0
"""

RETURN = r"""
users:
  description:
    - The users (C(RgwUserResponse) in the croit API), without any keys.
  returned: always
  type: list
  elements: dict
  contains:
    uid:
      description: The user id, tenant-qualified as C(tenant$uid) where the user has a tenant.
      returned: always
      type: str
      sample: backup
    name:
      description: The display name.
      returned: always
      type: str
      sample: Backup service
    email:
      description: The email address, empty where none is set.
      returned: always
      type: str
      sample: backup@example.com
    suspended:
      description: Whether RGW refuses the user's requests.
      returned: always
      type: bool
      sample: false
    subusers:
      description: The user's subusers, each with C(subuser) and C(permissions).
      returned: always
      type: list
      elements: dict
      sample:
        - subuser: reader
          permissions: read
    userQuota:
      description: The quota over all of the user's buckets together, with C(enabled), C(maxSize) and C(maxObjects).
      returned: always
      type: dict
      sample:
        enabled: true
        maxSize: 10995116277760
        maxObjects: -1
    bucketQuota:
      description: The quota applied to each of the user's buckets, with C(enabled), C(maxSize) and C(maxObjects).
      returned: always
      type: dict
      sample:
        enabled: false
        maxSize: -1
        maxObjects: -1
    buckets:
      description:
        - The buckets the user owns (C(RgwBucketResponse) in the croit API), with name, placement rule, quota and usage.
      returned: when O(include_buckets=true)
      type: list
      elements: dict
      sample:
        - bucket: backups
          owner: backup
          placement_rule: default-placement
          tenant: ""
          usageSum:
            numObjects: 1520
            sizeKiB: 5242880
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
