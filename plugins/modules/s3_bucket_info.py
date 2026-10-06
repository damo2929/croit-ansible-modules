#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /s3/buckets
# croit-api: GET /s3/users/{uid}/buckets
# croit-api: GET /s3/buckets/{bucketName}
# croit-api: GET /s3/buckets/{bucketName}/policy

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: s3_bucket_info
short_description: Read S3 buckets of a croit cluster
version_added: 0.1.0
description:
  - Returns S3 buckets of the Ceph object gateway with their owner, placement, usage and quota, and optionally
    their access control list, versioning, CORS rules and bucket policy.
  - Buckets can be selected by O(names) or by O(owner). This module never changes anything.
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
  names:
    description:
      - Buckets to return, tenant-qualified as C(tenant:bucket) where the bucket has a tenant.
      - Names croit does not know are left out of the result rather than failing.
      - When not set, every bucket (or every bucket of O(owner)) is returned.
    type: list
    elements: str
  owner:
    description:
      - Only return the buckets of this S3 user, tenant-qualified as C(tenant$uid) where needed.
      - These buckets are read live from the cluster instead of from croit's bucket list, whose usage figures may
        still be placeholders for buckets croit has not read yet.
    type: str
  include_details:
    description:
      - Also return each bucket's RV(buckets[].acl), RV(buckets[].versioning) and RV(buckets[].cors).
      - This costs one extra request per bucket.
    type: bool
    default: false
  include_policy:
    description:
      - Also return each bucket's RV(buckets[].policy) as parsed JSON, or null when it has none.
      - This costs one extra request per bucket.
    type: bool
    default: false
seealso:
  - module: croit.ceph.s3_bucket
    description: Create, update and delete S3 buckets.
  - module: croit.ceph.s3_user_info
    description: Read S3 users, optionally with the buckets they own.
  - name: croit API reference
    description: The croit REST API, including the C(/s3/buckets) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph RGW bucket policies
    description: Upstream documentation of the S3 bucket policy language RGW supports.
    link: https://docs.ceph.com/en/latest/radosgw/bucketpolicy/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Read every bucket
  croit.ceph.s3_bucket_info:
  register: buckets

- name: Show the five largest buckets by object count
  ansible.builtin.debug:
    msg: "{{ (buckets.buckets | sort(attribute='usageSum.numObjects', reverse=true))[:5] | map(attribute='bucket') | list }}"

- name: Read one bucket with its ACL, versioning and policy
  croit.ceph.s3_bucket_info:
    names:
      - backups
    include_details: true
    include_policy: true
  register: backups

- name: Check that versioning is enabled on the backup bucket
  ansible.builtin.assert:
    that:
      - backups.buckets[0].versioning == 'ENABLED'

- name: Read every bucket of one user
  croit.ceph.s3_bucket_info:
    owner: backup
"""

RETURN = r"""
buckets:
  description:
    - The buckets (C(RgwBucketResponse) in the croit API).
  returned: always
  type: list
  elements: dict
  contains:
    bucket:
      description: The bucket's name, tenant-qualified as C(tenant:bucket) where it has a tenant.
      returned: always
      type: str
      sample: backups
    owner:
      description: The S3 user that owns the bucket.
      returned: always
      type: str
      sample: backup
    placement_rule:
      description: The placement rule the bucket's data lands on.
      returned: always
      type: str
      sample: default-placement
    tenant:
      description: The bucket's tenant, empty for one that has none.
      returned: always
      type: str
      sample: ""
    bucket_quota:
      description: The quota RGW holds the bucket to, with C(enabled), C(maxSize) and C(maxObjects).
      returned: always
      type: dict
      sample:
        enabled: false
        maxSize: -1
        maxObjects: -1
    usageSum:
      description: What the bucket holds across every zone, including C(numObjects) and C(sizeKiB).
      returned: always
      type: dict
      sample:
        numObjects: 1520
        sizeKiB: 5242880
    acl:
      description: The bucket's access control list (C(AclEntry) in the croit API), each with C(grantee), C(permission) and C(userId).
      returned: when O(include_details=true)
      type: list
      elements: dict
      sample:
        - grantee: SINGLE_USER
          permission: FullControl
          userId: backup
    versioning:
      description: The bucket's versioning state, V(ENABLED), V(SUSPENDED) or V(OFF).
      returned: when O(include_details=true)
      type: str
      sample: ENABLED
    cors:
      description: The bucket's CORS rules as croit reports them.
      returned: when O(include_details=true)
      type: list
      elements: dict
      sample: []
    policy:
      description:
        - The bucket policy as parsed JSON, or null when the bucket has none.
        - If the stored policy is not valid JSON, it is returned as the raw text.
      returned: when O(include_policy=true)
      type: raw
      sample:
        Version: "2012-10-17"
        Statement: []
"""

import json

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            names=dict(type="list", elements="str"),
            owner=dict(type="str"),
            include_details=dict(type="bool", default=False),
            include_policy=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    p = m.params
    if p["owner"]:
        buckets = m.get_list(path_join("s3", "users", p["owner"], "buckets"))
    else:
        buckets = m.get_list("/s3/buckets")
    if p["names"]:
        buckets = [b for b in buckets if b.get("bucket") in p["names"]]

    for bucket in buckets:
        name, owner = bucket.get("bucket"), bucket.get("owner")
        if p["include_details"]:
            details = m.get(path_join("s3", "buckets", name), query=dict(owner=owner)) or {}
            for key in ("acl", "versioning", "cors"):
                bucket[key] = details.get(key)
        if p["include_policy"]:
            text = (m.get(path_join("s3", "buckets", name, "policy"), query=dict(owner=owner)) or {}).get("policyText")
            try:
                bucket["policy"] = json.loads(text) if text else None
            except ValueError:
                bucket["policy"] = text
    m.exit(changed=False, buckets=buckets)


if __name__ == "__main__":
    main()
