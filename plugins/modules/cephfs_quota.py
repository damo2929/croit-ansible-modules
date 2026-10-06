#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /cephfs/quota
# croit-api: PUT /cephfs/quota
# croit-api: GET /cephfs/layout
# croit-api: PUT /cephfs/layout
# croit-api: GET /cephfs/layout/pools

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: cephfs_quota
short_description: Manage quotas and the data layout of CephFS directories on a croit cluster
version_added: 0.1.0
description:
  - Sets the byte and file quota of a CephFS directory, and the data pool (layout) new files in it are
    stored in, through the croit API.
  - Only options that are set are managed; anything left out keeps its current value.
  - The directory must already exist.
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
  path:
    description:
      - Absolute path of the directory inside the CephFS volume, for example V(/projects/alpha).
      - The root of a filesystem cannot have a quota.
    type: str
    required: true
  volume:
    description:
      - CephFS volume the directory is in. croit's own CephFS volume is used when not set.
    type: str
  state:
    description:
      - V(present) applies the options that are set.
      - V(absent) removes both quota limits. It does not change the layout, and cannot be combined with
        O(max_bytes), O(max_files), O(layout_pool) or O(layout_namespace).
    type: str
    choices: [present, absent]
    default: present
  max_bytes:
    description:
      - Byte quota, as bytes or with a binary unit such as V(500G) or V(10T).
      - V(unlimited) (or V(0)) removes the byte limit.
    type: str
  max_files:
    description:
      - Maximum number of files and directories. V(0) removes the file limit.
    type: int
  layout_pool:
    description:
      - Data pool that new files below the directory are stored in. Must be one of the volume's data pools.
      - Changing it only affects files created afterwards.
      - An empty string makes the directory inherit its parent's layout again.
    type: str
  layout_namespace:
    description:
      - RADOS namespace inside O(layout_pool) that new files are stored in.
      - An empty string removes the namespace.
    type: str
"""

EXAMPLES = r"""
- name: Limit a project directory to 10 TiB and one million files
  croit.ceph.cephfs_quota:
    api_url: https://croit-mgmt/api
    api_token: "{{ vault_croit_token }}"
    volume: cephfs
    path: /projects/alpha
    max_bytes: 10T
    max_files: 1000000

- name: Store new archive files on the EC data pool
  croit.ceph.cephfs_quota:
    volume: cephfs
    path: /archive
    layout_pool: cephfs.cephfs.ec-data

- name: Remove the quota
  croit.ceph.cephfs_quota:
    volume: cephfs
    path: /projects/alpha
    state: absent
"""

RETURN = r"""
quota:
  description: The directory's quota after the change (C(CephFsQuota) in the croit API); before it in check mode.
  returned: always
  type: dict
  sample:
    maxBytes: 10995116277760
    maxFiles: 1000000
layout:
  description: The directory's layout after the change (C(CephFsLayout) in the croit API); before it in check mode.
  returned: when O(layout_pool) or O(layout_namespace) is set
  type: dict
  sample:
    pool: cephfs.cephfs.ec-data
    namespace: null
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule, parse_quota


def limit(value):
    """croit answers null (or a non-positive number) for no limit; normalise to 0."""
    return value if isinstance(value, int) and value > 0 else 0


def nullable(value):
    """Option value -> layout API value; an empty string means inherit / none."""
    return value or None


class CephfsQuotaModule(CroitModule):
    def __init__(self):
        super(CephfsQuotaModule, self).__init__(
            dict(
                path=dict(type="str", required=True),
                volume=dict(type="str"),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                max_bytes=dict(type="str"),
                max_files=dict(type="int"),
                layout_pool=dict(type="str"),
                layout_namespace=dict(type="str"),
            ),
            wait=False,
            warnings=False,
        )

    def run(self):
        p = self.params
        if not p["path"].startswith("/"):
            self.module.fail_json(msg="path must be absolute, got %r" % p["path"])
        if p["state"] == "absent":
            given = [o for o in ("max_bytes", "max_files", "layout_pool", "layout_namespace") if p[o] is not None]
            if given:
                self.module.fail_json(msg="state=absent cannot be combined with %s" % ", ".join(given))
        if p["max_files"] is not None and p["max_files"] < 0:
            self.module.fail_json(msg="max_files must not be negative")
        try:
            max_bytes = parse_quota(p["max_bytes"])
        except ValueError as e:
            self.module.fail_json(msg="max_bytes: %s" % e)

        quota_query = dict(dir=p["path"], volume=p["volume"])
        layout_query = dict(path=p["path"], volume=p["volume"])
        manage_layout = p["layout_pool"] is not None or p["layout_namespace"] is not None

        quota = self.get("/cephfs/quota", query=quota_query) or {}
        current = dict(max_bytes=limit(quota.get("maxBytes")), max_files=limit(quota.get("maxFiles")))
        result = dict(quota=quota)

        if p["state"] == "absent":
            desired = dict(max_bytes=0, max_files=0)
        else:
            desired = dict(max_bytes=max_bytes, max_files=p["max_files"])

        layout = None
        if manage_layout:
            layout = self.get("/cephfs/layout", query=layout_query) or {}
            result["layout"] = layout
            current.update(layout_pool=layout.get("pool"), layout_namespace=layout.get("namespace"))
            desired.update(layout_pool=p["layout_pool"], layout_namespace=p["layout_namespace"])
            if desired["layout_pool"] is not None:
                desired["layout_pool"] = nullable(desired["layout_pool"])
            if desired["layout_namespace"] is not None:
                desired["layout_namespace"] = nullable(desired["layout_namespace"])

        # A layout option set to "" becomes None above, meaning "inherit"; compare those explicitly.
        changed_keys = []
        for key, value in desired.items():
            explicit_none = key.startswith("layout_") and p[key] == ""
            if (value is not None or explicit_none) and current.get(key) != value:
                changed_keys.append(key)

        before = dict(current)
        after = dict(current)
        for key in changed_keys:
            after[key] = desired[key]

        if manage_layout and "layout_pool" in changed_keys and after["layout_pool"]:
            pools = self.get_list("/cephfs/layout/pools", query=dict(volume=p["volume"]))
            if after["layout_pool"] not in pools:
                self.module.fail_json(
                    msg="Pool %r cannot hold CephFS data for this volume. Eligible pools: %s"
                    % (after["layout_pool"], ", ".join(pools) or "none")
                )

        if not changed_keys:
            self.exit(changed=False, before=before, after=after, **result)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, **result)

        if "max_bytes" in changed_keys or "max_files" in changed_keys:
            body = dict(maxBytes=after["max_bytes"] or None, maxFiles=after["max_files"] or None)
            self.write("PUT", "/cephfs/quota", body=body, query=quota_query)
            result["quota"] = self.get("/cephfs/quota", query=quota_query) or {}
        if "layout_pool" in changed_keys or "layout_namespace" in changed_keys:
            body = dict(pool=after["layout_pool"], namespace=after["layout_namespace"])
            self.write("PUT", "/cephfs/layout", body=body, query=layout_query)
            result["layout"] = self.get("/cephfs/layout", query=layout_query) or {}
        self.exit(changed=True, before=before, after=after, **result)


def main():
    CephfsQuotaModule().run()


if __name__ == "__main__":
    main()
