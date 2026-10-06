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
  - A placement rule decides which pools a bucket's objects, indexes and metadata are stored in. Each of its storage
    classes may store objects in a pool of its own.
  - Manages one storage class of one placement rule, identified by O(name) and O(storage_class). The V(STANDARD)
    class is the rule itself; creating it creates the rule, and deleting it deletes the rule with all of its storage
    classes.
  - Pools cannot be changed after creation, because objects already stored would no longer be addressable. A
    different pool fails the task instead of recreating the rule.
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
      - Any other class needs the rule to exist already; create it first with O(storage_class=STANDARD).
    type: str
    default: STANDARD
  state:
    description:
      - Whether the storage class should exist.
      - V(absent) needs O(confirm_delete=true). croit refuses to remove a class or rule any bucket still stores in.
        Removing the default placement, or a rule that has other storage classes, also needs O(ignore_warnings=true).
    type: str
    choices: [present, absent]
    default: present
  data_pool:
    description:
      - Pool the objects of this storage class are stored in, as managed with M(croit.ceph.pool).
      - Required to create the class; create-only afterwards, so a different value fails the task.
    type: str
  index_pool:
    description:
      - Pool the rule's bucket indexes are stored in. Only valid for V(STANDARD).
      - croit uses the zone's own index pool when not set. It cannot be erasure coded, and it is create-only.
    type: str
  data_extra_pool:
    description:
      - Pool for the rule's extra metadata, such as incomplete multipart uploads. Only valid for V(STANDARD).
      - croit uses the zone's own non-EC pool when not set. It cannot be erasure coded, and it is create-only.
    type: str
  default:
    description:
      - Make this rule and storage class the zonegroup's default placement, where new buckets land unless they or
        their owner name another.
      - V(false) on the current default fails, because croit cannot unset the default; make another placement the
        default instead. When unset, the default placement is left alone.
    type: bool
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to remove an existing storage class or rule. Without it the module fails,
        in check mode as well.
    type: bool
    default: false
seealso:
  - module: croit.ceph.s3_bucket
    description: Create buckets on a placement rule.
  - module: croit.ceph.s3_user
    description: Set a user's default placement and storage class.
  - module: croit.ceph.pool
    description: Create the pools a placement rule stores in.
  - name: croit API reference
    description: The croit REST API, including the C(/s3/placements) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph RGW pool placement and storage classes
    description: Upstream documentation of placement targets and storage classes.
    link: https://docs.ceph.com/en/latest/radosgw/placement/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Create a placement rule on an erasure coded data pool
  croit.ceph.s3_placement:
    name: ec-placement
    data_pool: default.rgw.buckets.data-ec

- name: Add a cold storage class on an HDD pool
  croit.ceph.s3_placement:
    name: ec-placement
    storage_class: COLD
    data_pool: rgw-cold

- name: Make new buckets land on the EC placement
  croit.ceph.s3_placement:
    name: ec-placement
    default: true
  register: placement

- name: Show the pools the default placement uses
  ansible.builtin.debug:
    msg: "Data in {{ placement.placement.dataPool }}, indexes in {{ placement.placement.indexPool }}"

- name: Remove the cold storage class
  croit.ceph.s3_placement:
    name: ec-placement
    storage_class: COLD
    state: absent
    confirm_delete: true
"""

RETURN = r"""
placement:
  description:
    - The storage class row (C(RgwPlacementPolicyResponse) in the croit API) after the run.
    - In check mode, the row as it was before. Empty when the class does not exist or was removed.
  returned: always
  type: dict
  contains:
    name:
      description: The placement rule's name.
      returned: when the storage class exists
      type: str
      sample: ec-placement
    storageClass:
      description: The storage class this row is about.
      returned: when the storage class exists
      type: str
      sample: STANDARD
    dataPool:
      description: The pool the objects of this class are stored in.
      returned: when the storage class exists
      type: str
      sample: default.rgw.buckets.data-ec
    indexPool:
      description: The pool the rule's bucket indexes are stored in.
      returned: when the storage class exists
      type: str
      sample: default.rgw.buckets.index
    dataExtraPool:
      description: The pool for the rule's extra metadata.
      returned: when the storage class exists
      type: str
      sample: default.rgw.buckets.non-ec
    isDefault:
      description: Whether new buckets land here unless they say otherwise.
      returned: when the storage class exists
      type: bool
      sample: false
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
