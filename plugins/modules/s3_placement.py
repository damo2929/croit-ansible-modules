#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /s3/placements
# croit-api: PUT /s3/placements/{name}
# croit-api: PUT /s3/placements/{placementRule}/storage-classes/{storageClass}
# croit-api: DELETE /s3/placements/{placementRule}/storage-classes/{storageClass}
# croit-api: PUT /s3/default-placement

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: s3_placement
short_description: Manage S3 placement rules and storage classes on a croit cluster
version_added: 0.1.0
description:
  - A placement rule decides which pools a bucket's objects, indexes and metadata are stored in. Each of its
    storage classes may store objects in a pool of its own.
  - Manages one storage class of one placement rule. The V(STANDARD) class is the rule itself. Creating it
    creates the rule, and deleting it deletes the rule with all its storage classes.
  - Pools cannot be changed after creation, because objects already stored would no longer be addressable.
    A different pool fails the task.
  - croit does not support these changes on clusters in a multisite setup, and refuses them there.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  name:
    description:
      - Name of the placement rule, for example V(default-placement).
    type: str
    required: true
  storage_class:
    description:
      - Storage class of the rule. V(STANDARD) is the rule itself.
      - Any other class needs the rule to exist already.
    type: str
    default: STANDARD
  state:
    description:
      - Whether the storage class should exist.
      - V(absent) needs O(confirm_delete=true). croit refuses to remove a class or rule any bucket still stores
        in. Removing the default placement, or a rule that has other storage classes, needs
        O(ignore_warnings=true).
    type: str
    choices: [present, absent]
    default: present
  data_pool:
    description:
      - Pool the objects of this storage class are stored in. Required to create it.
    type: str
  index_pool:
    description:
      - Pool the rule's bucket indexes are stored in. Only for V(STANDARD); croit uses the zone's own index pool
        when not set. Cannot be erasure coded.
    type: str
  data_extra_pool:
    description:
      - Pool for the rule's extra metadata. Only for V(STANDARD); croit uses the zone's own non-EC pool when not
        set. Cannot be erasure coded.
    type: str
  default:
    description:
      - Make this rule and storage class the zonegroup's default placement, where new buckets land unless they
        name another.
      - V(false) on the current default fails, because croit cannot unset the default. Make another placement
        the default instead.
    type: bool
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to remove an existing storage class or rule.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Placement rule on an erasure coded data pool
  croit.ceph.s3_placement:
    name: ec-placement
    data_pool: default.rgw.buckets.data-ec

- name: Cold storage class on HDDs
  croit.ceph.s3_placement:
    name: ec-placement
    storage_class: COLD
    data_pool: rgw-cold

- name: New buckets land on the EC placement
  croit.ceph.s3_placement:
    name: ec-placement
    default: true

- name: Remove the storage class
  croit.ceph.s3_placement:
    name: ec-placement
    storage_class: COLD
    state: absent
    confirm_delete: true
"""

RETURN = r"""
placement:
  description: The storage class row (C(RgwPlacementPolicyResponse)) after the run; empty when it does not exist.
  returned: always
  type: dict
  sample:
    name: ec-placement
    storageClass: STANDARD
    dataPool: default.rgw.buckets.data-ec
    indexPool: default.rgw.buckets.index
    dataExtraPool: default.rgw.buckets.non-ec
    isDefault: false
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

STANDARD = "STANDARD"
# Ansible option -> RgwPlacementPolicyResponse field.
POOLS = dict(data_pool="dataPool", index_pool="indexPool", data_extra_pool="dataExtraPool")


def view(row):
    if not row:
        return {}
    result = dict((opt, row.get(api)) for opt, api in POOLS.items())
    result["default"] = bool(row.get("isDefault"))
    return result


class S3PlacementModule(CroitModule):
    def __init__(self):
        super(S3PlacementModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                storage_class=dict(type="str", default=STANDARD),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                data_pool=dict(type="str"),
                index_pool=dict(type="str"),
                data_extra_pool=dict(type="str"),
                default=dict(type="bool"),
                confirm_delete=dict(type="bool", default=False),
            ),
            wait=False,
        )

    def rows(self):
        data = self.get("/s3/placements") or {}
        if isinstance(data, dict):
            return data.get("placements") or data.get("data") or []
        return data or []

    def find(self, rows, name, storage_class):
        for row in rows:
            if row.get("name") == name and row.get("storageClass") == storage_class:
                return row
        return None

    def run(self):
        p = self.params
        name, storage_class = p["name"], p["storage_class"]
        standard = storage_class == STANDARD
        if not standard and (p["index_pool"] is not None or p["data_extra_pool"] is not None):
            self.module.fail_json(msg="index_pool and data_extra_pool only apply to the STANDARD storage class")

        rows = self.rows()
        current = self.find(rows, name, storage_class)

        if p["state"] == "absent":
            return self.absent(current)

        before = view(current)
        if current is None:
            if p["data_pool"] is None:
                self.module.fail_json(msg="data_pool is required to create %s/%s" % (name, storage_class))
            if not standard and not any(r.get("name") == name for r in rows):
                self.module.fail_json(
                    msg="Placement rule %r does not exist; create it (storage_class=STANDARD) before adding %r"
                    % (name, storage_class)
                )
            after = dict(data_pool=p["data_pool"], index_pool=p["index_pool"], data_extra_pool=p["data_extra_pool"])
            after["default"] = bool(p["default"])
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, placement={})
            if standard:
                body = dict(dataPool=p["data_pool"])
                if p["index_pool"] is not None:
                    body["indexPool"] = p["index_pool"]
                if p["data_extra_pool"] is not None:
                    body["dataExtraPool"] = p["data_extra_pool"]
                self.write("PUT", path_join("s3", "placements", name), body=body)
            else:
                self.write(
                    "PUT",
                    path_join("s3", "placements", name, "storage-classes", storage_class),
                    body=dict(dataPool=p["data_pool"]),
                )
            if p["default"]:
                self.set_default()
            current = self.find(self.rows(), name, storage_class) or {}
            after = view(current) or after
            self.exit(changed=True, before={}, after=after, placement=current)

        for opt, api in POOLS.items():
            if p[opt] is not None and p[opt] != current.get(api):
                self.module.fail_json(
                    msg="%s of %s/%s is %r and cannot be changed to %r; create a new placement rule or storage class "
                    "instead" % (opt, name, storage_class, current.get(api), p[opt])
                )

        after = dict(before)
        changed = False
        if p["default"] is not None and p["default"] != before["default"]:
            if not p["default"]:
                self.module.fail_json(
                    msg="%s/%s is the default placement and croit cannot unset it; make another placement the default"
                    % (name, storage_class)
                )
            after["default"] = True
            changed = True

        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, placement=current)
        self.set_default()
        self.exit(changed=True, before=before, after=after, placement=self.find(self.rows(), name, storage_class) or {})

    def set_default(self):
        p = self.params
        self.write(
            "PUT",
            "/s3/default-placement",
            body=dict(placementRule=p["name"], storageClass=p["storage_class"]),
        )

    def absent(self, current):
        p = self.params
        if current is None:
            self.exit(changed=False, placement={})
        if not p["confirm_delete"]:
            what = "placement rule %r with all its storage classes" % p["name"] if p["storage_class"] == STANDARD else (
                "storage class %r of placement rule %r" % (p["storage_class"], p["name"])
            )
            self.module.fail_json(msg="Refusing to remove %s without confirm_delete=true" % what)
        if not self.check_mode:
            self.write("DELETE", path_join("s3", "placements", p["name"], "storage-classes", p["storage_class"]))
        self.exit(changed=True, before=view(current), after={}, placement={})


def main():
    S3PlacementModule().run()


if __name__ == "__main__":
    main()
