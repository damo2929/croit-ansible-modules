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
  - Returns S3 buckets with their owner, placement, usage and quota, and optionally their access control
    list, versioning and bucket policy.
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
      - Buckets to return, tenant-qualified as C(tenant:bucket) where needed. Unknown names are left out.
      - When not set, every bucket is returned.
    type: list
    elements: str
  owner:
    description:
      - Only return the buckets of this S3 user. They are read live from the cluster instead of croit's
        bucket list, whose usage figures may still be placeholders for buckets croit has not read yet.
    type: str
  include_details:
    description:
      - Also return each bucket's C(acl), C(versioning) and C(cors). Costs one request per bucket.
    type: bool
    default: false
  include_policy:
    description:
      - Also return each bucket's C(policy) as parsed JSON (null when it has none). Costs one request per bucket.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: All buckets
  croit.ceph.s3_bucket_info:
  register: buckets

- name: One bucket with its ACL and policy
  croit.ceph.s3_bucket_info:
    names: [backups]
    include_details: true
    include_policy: true
"""

RETURN = r"""
buckets:
  description:
    - The buckets (C(RgwBucketResponse) in the croit API), plus C(acl), C(versioning) and C(cors) with
      O(include_details=true) and C(policy) with O(include_policy=true).
  returned: always
  type: list
  elements: dict
  sample:
    - bucket: backups
      owner: backup
      placement_rule: default-placement
      tenant: ""
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
