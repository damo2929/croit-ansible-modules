#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /s3/users
# croit-api: POST /s3/users
# croit-api: PATCH /s3/users/{uid}
# croit-api: DELETE /s3/users/{uid}
# croit-api: PUT /s3/users/{uid}/quota
# croit-api: PUT /s3/users/{uid}/bucket-quota
# croit-api: GET /s3/users/{uid}/buckets

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: s3_user
short_description: Manage S3 (RGW) users on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete S3 users of the Ceph object gateway through the croit API, including the
    user quota and the per-bucket quota.
  - Only options that are set are managed; anything left out keeps its current value.
  - Access keys are managed with M(croit.ceph.s3_user_key) and subusers with M(croit.ceph.s3_subuser).
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  uid:
    description:
      - The user id. A user in a tenant is addressed as C(tenant$uid); either pass it that way or set O(tenant).
    type: str
    required: true
  tenant:
    description:
      - Tenant of the user. Combined with O(uid) as C(tenant$uid).
    type: str
  state:
    description:
      - Whether the user should exist.
      - croit refuses to delete a user that still owns buckets; delete or move the buckets first.
    type: str
    choices: [present, absent]
    default: present
  display_name:
    description:
      - The user's display name. Required when the user is created.
    type: str
  email:
    description:
      - The user's email address. An empty string removes it.
    type: str
  default_placement:
    description:
      - Placement rule new buckets of this user land on. An empty string resets it to the zone's default.
    type: str
  default_storage_class:
    description:
      - Storage class new objects of this user land on.
    type: str
  suspended:
    description:
      - Whether the gateway refuses this user's requests.
    type: bool
  user_quota:
    description:
      - Quota over everything the user stores, across all of their buckets.
      - Only the sub-options that are set are managed.
    type: dict
    suboptions:
      enabled:
        description: Whether the quota is enforced.
        type: bool
      max_size:
        description:
          - Maximum size, as bytes or with a binary unit such as V(500G). V(-1) or V(unlimited) means no size bound.
        type: str
      max_objects:
        description: Maximum number of objects. V(-1) means no object bound.
        type: int
  bucket_quota:
    description:
      - Quota applied to each of the user's buckets separately.
      - Only the sub-options that are set are managed.
    type: dict
    suboptions:
      enabled:
        description: Whether the quota is enforced.
        type: bool
      max_size:
        description:
          - Maximum size, as bytes or with a binary unit such as V(500G). V(-1) or V(unlimited) means no size bound.
        type: str
      max_objects:
        description: Maximum number of objects. V(-1) means no object bound.
        type: int
"""

EXAMPLES = r"""
- name: S3 user for the backup service with a 10 TiB quota
  croit.ceph.s3_user:
    api_url: https://croit-mgmt/api
    api_token: "{{ vault_croit_token }}"
    uid: backup
    display_name: Backup service
    email: backup@example.com
    user_quota:
      enabled: true
      max_size: 10T

- name: Suspend a user
  croit.ceph.s3_user:
    uid: tenant1$alice
    suspended: true

- name: Delete a user (it must not own buckets)
  croit.ceph.s3_user:
    uid: backup
    state: absent
"""

RETURN = r"""
user:
  description:
    - The user as croit reports it after the change (C(RgwUserResponse) in the croit API).
    - Before the change in check mode; empty when the user does not exist.
  returned: always
  type: dict
  sample:
    uid: backup
    name: Backup service
    email: backup@example.com
    suspended: false
    subusers: []
    userQuota:
      enabled: true
      maxSize: 10995116277760
      maxObjects: -1
    bucketQuota:
      enabled: false
      maxSize: -1
      maxObjects: -1
task:
  description: The last croit background task the change ran as, when there was one.
  returned: when a task ran
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.rgw import (
    QUOTA_OPTIONS,
    parse_quota_size,
    quota_changes,
    quota_request,
    quota_view,
)

# Ansible option -> croit API field, compared 1:1.
FIELDS = dict(
    display_name="name",
    email="email",
    default_placement="defaultPlacement",
    default_storage_class="defaultStorageClass",
    suspended="suspended",
)
# Fields where croit reports "not set" as null or "" and accepts "" to clear.
EMPTY_IS_UNSET = ("email", "defaultPlacement", "defaultStorageClass")


def normalise(field, value):
    if field in EMPTY_IS_UNSET and value is None:
        return ""
    return value


def managed_view(user):
    if not user:
        return {}
    view = dict((opt, normalise(api, user.get(api))) for opt, api in FIELDS.items())
    view["user_quota"] = quota_view(user.get("userQuota"))
    view["bucket_quota"] = quota_view(user.get("bucketQuota"))
    return view


class S3UserModule(CroitModule):
    def __init__(self):
        super(S3UserModule, self).__init__(
            dict(
                uid=dict(type="str", required=True),
                tenant=dict(type="str"),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                display_name=dict(type="str"),
                email=dict(type="str"),
                default_placement=dict(type="str"),
                default_storage_class=dict(type="str"),
                suspended=dict(type="bool"),
                user_quota=dict(type="dict", options=QUOTA_OPTIONS),
                bucket_quota=dict(type="dict", options=QUOTA_OPTIONS),
            ),
        )

    def identity(self):
        uid, tenant = self.params["uid"], self.params["tenant"]
        if "$" in uid:
            uid_tenant, bare = uid.split("$", 1)
            if tenant and tenant != uid_tenant:
                self.module.fail_json(msg="uid %r names tenant %r but tenant is %r" % (uid, uid_tenant, tenant))
            return uid, uid_tenant, bare
        if tenant:
            return "%s$%s" % (tenant, uid), tenant, uid
        return uid, None, uid

    def find_user(self, full_uid):
        for user in self.get_list("/s3/users", query=dict(uid=[full_uid])):
            if user.get("uid") == full_uid:
                return user
        return None

    def desired_quota(self, option):
        quota = self.params[option]
        if not quota:
            return None
        try:
            size = parse_quota_size(quota.get("max_size"))
        except ValueError as e:
            self.module.fail_json(msg="%s.max_size: %s" % (option, e))
        return dict(enabled=quota.get("enabled"), max_size=size, max_objects=quota.get("max_objects"))

    def run(self):
        full_uid, tenant, bare_uid = self.identity()
        current = self.find_user(full_uid)
        if self.params["state"] == "absent":
            self.absent(full_uid, current)
        self.present(full_uid, tenant, bare_uid, current)

    def absent(self, full_uid, current):
        if current is None:
            self.exit(changed=False, user={})
        buckets = self.get_list(path_join("s3", "users", full_uid, "buckets"))
        if buckets:
            self.module.fail_json(
                msg="S3 user %r still owns %d bucket(s) (%s); croit will not delete it. Delete or move the buckets first."
                % (full_uid, len(buckets), ", ".join(b.get("bucket", "?") for b in buckets))
            )
        if not self.check_mode:
            self.handle_task(self.write("DELETE", path_join("s3", "users", full_uid)))
        self.exit(changed=True, before=managed_view(current), after={}, user={})

    def present(self, full_uid, tenant, bare_uid, current):
        p = self.params
        if current is None and p["display_name"] is None:
            self.module.fail_json(msg="display_name is required to create S3 user %r" % full_uid)

        if current is None:
            before = {}
            current_view = managed_view(dict(name=None, suspended=False))
        else:
            before = managed_view(current)
            current_view = before

        # Plain fields: option -> desired value, for the ones that differ.
        field_changes = dict(
            (opt, p[opt])
            for opt, api in FIELDS.items()
            if p[opt] is not None and normalise(api, p[opt]) != current_view[opt]
        )
        quota_updates = {}
        for opt in ("user_quota", "bucket_quota"):
            wanted = self.desired_quota(opt)
            if wanted is None:
                continue
            merged, differs = quota_changes(current_view[opt], wanted)
            if differs:
                quota_updates[opt] = merged

        after = dict(current_view)
        after.update((opt, normalise(FIELDS[opt], value)) for opt, value in field_changes.items())
        after.update(quota_updates)

        changed = current is None or bool(field_changes) or bool(quota_updates)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, user=current or {})

        tasks = []
        if current is None:
            body = dict(uid=bare_uid, name=p["display_name"])
            if tenant:
                body["tenant"] = tenant
            for opt in ("email", "default_placement", "default_storage_class"):
                if p[opt] is not None:
                    body[FIELDS[opt]] = p[opt]
            tasks.append(self.handle_task(self.write("POST", "/s3/users", body=body)))
            # The create request carries no suspension; set it afterwards.
            field_changes = dict(suspended=True) if p["suspended"] else {}
        if field_changes:
            body = dict((FIELDS[opt], value) for opt, value in field_changes.items())
            tasks.append(self.handle_task(self.write("PATCH", path_join("s3", "users", full_uid), body=body)))
        for opt, endpoint in (("user_quota", "quota"), ("bucket_quota", "bucket-quota")):
            if opt in quota_updates:
                body = quota_request(quota_updates[opt])
                tasks.append(self.handle_task(self.write("PUT", path_join("s3", "users", full_uid, endpoint), body=body)))

        result = dict(changed=True, before=before, after=after, user=self.find_user(full_uid) or {})
        tasks = [t for t in tasks if t is not None]
        if tasks:
            result["task"] = tasks[-1]
        self.exit(**result)


def main():
    S3UserModule().run()


if __name__ == "__main__":
    main()
