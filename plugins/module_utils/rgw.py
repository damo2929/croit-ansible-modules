# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""RGW (S3) quota helpers shared by croit.ceph.s3_user and croit.ceph.s3_bucket.

RGW quotas use -1 for "no bound", unlike CephFS/pool quotas where 0 means
unlimited (see module.parse_quota).
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.module_utils.module import parse_size

# Sub-options of a user_quota / bucket_quota / quota option.
QUOTA_OPTIONS = dict(
    enabled=dict(type="bool"),
    max_size=dict(type="str"),
    max_objects=dict(type="int"),
)


def parse_quota_size(value):
    """Bytes for an RGW quota size; -1 for no bound. None means not managed."""
    if value is None:
        return None
    if str(value).strip().lower() in ("-1", "unlimited"):
        return -1
    return parse_size(value)


def quota_view(quota):
    """A croit quota as Ansible sub-options; any negative or missing bound is -1."""
    quota = quota or {}

    def bound(value):
        if value is None:
            return -1
        return -1 if value < 0 else value

    return dict(
        enabled=bool(quota.get("enabled")),
        max_size=bound(quota.get("maxSize")),
        max_objects=bound(quota.get("maxObjects")),
    )


def quota_changes(current, desired):
    """Merge the set sub-options of ``desired`` into ``current``; return (merged, differs)."""
    merged = dict(current)
    for key, value in desired.items():
        if value is not None:
            merged[key] = value
    return merged, merged != current


def quota_request(view):
    """Ansible quota view -> croit request body."""
    return dict(enabled=view["enabled"], maxSize=view["max_size"], maxObjects=view["max_objects"])
