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
  - Create, update and delete S3 users of the Ceph object gateway (RGW) through the croit API, including the
    user quota and the per-bucket quota.
  - The user is identified by O(uid), optionally qualified by O(tenant). Only options that are set are managed;
    anything left out keeps its current value.
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
      - If O(uid) already names a tenant and O(tenant) is also set, both must name the same tenant.
    type: str
    required: true
  tenant:
    description:
      - Tenant of the user. It is combined with O(uid) as C(tenant$uid).
      - Leave unset for a user without a tenant.
    type: str
  state:
    description:
      - Whether the user should exist.
      - V(absent) deletes the user. croit refuses to delete a user that still owns buckets, so the module fails
        before any change and lists the buckets; delete them with M(croit.ceph.s3_bucket) or move them to
        another owner first.
    type: str
    choices: [present, absent]
    default: present
  display_name:
    description:
      - The user's display name.
      - Required when the user is created; when unset on an existing user, the name is left alone.
    type: str
  email:
    description:
      - The user's email address.
      - An empty string removes the address.
    type: str
  default_placement:
    description:
      - Placement rule that new buckets of this user land on, as managed with M(croit.ceph.s3_placement).
      - An empty string resets it to the zone's default placement.
    type: str
  default_storage_class:
    description:
      - Storage class that new objects of this user land on.
      - An empty string resets it to the placement rule's own default storage class.
    type: str
  suspended:
    description:
      - Whether the gateway refuses this user's requests.
      - When a new user is created suspended, croit creates it first and suspends it in a second request.
    type: bool
  user_quota:
    description:
      - Quota over everything the user stores, across all of their buckets together.
      - Only the sub-options that are set are managed; the others keep their current values.
    type: dict
    suboptions:
      enabled:
        description: Whether the quota is enforced. A quota with bounds but V(false) here is not enforced.
        type: bool
      max_size:
        description:
          - Maximum total size, as bytes or with a binary unit such as V(500G) or V(10T).
          - V(-1) or V(unlimited) means no size bound.
        type: str
      max_objects:
        description: Maximum number of objects. V(-1) means no object bound.
        type: int
  bucket_quota:
    description:
      - Quota applied to each of the user's buckets separately, as the default for their buckets.
      - Only the sub-options that are set are managed; the others keep their current values.
      - A single bucket's own quota is managed with O(croit.ceph.s3_bucket#module:quota).
    type: dict
    suboptions:
      enabled:
        description: Whether the quota is enforced. A quota with bounds but V(false) here is not enforced.
        type: bool
      max_size:
        description:
          - Maximum size of each bucket, as bytes or with a binary unit such as V(500G) or V(10T).
          - V(-1) or V(unlimited) means no size bound.
        type: str
      max_objects:
        description: Maximum number of objects per bucket. V(-1) means no object bound.
        type: int
notes:
  - Deleting a user removes its access keys and subusers. Clients using those keys immediately lose access.
  - The quotas are compared as RGW reports them, where any negative bound means unlimited and is shown as V(-1).
seealso:
  - module: croit.ceph.s3_user_info
    description: Read S3 users, optionally with the buckets each one owns.
  - module: croit.ceph.s3_user_key
    description: Manage the S3 access keys of a user or subuser.
  - module: croit.ceph.s3_subuser
    description: Manage the subusers of an S3 user.
  - module: croit.ceph.s3_bucket
    description: Manage the buckets an S3 user owns.
  - name: croit API reference
    description: The croit REST API, including the C(/s3/users) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph RGW administration guide
    description: Upstream documentation of RGW users and quotas.
    link: https://docs.ceph.com/en/latest/radosgw/admin/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Create an S3 user for the backup service with a 10 TiB quota
  croit.ceph.s3_user:
    uid: backup
    display_name: Backup service
    email: backup@example.com
    user_quota:
      enabled: true
      max_size: 10T

- name: Limit every bucket of the user to one million objects
  croit.ceph.s3_user:
    uid: backup
    bucket_quota:
      enabled: true
      max_objects: 1000000

- name: Create a user in a tenant, suspended until it is needed
  croit.ceph.s3_user:
    uid: alice
    tenant: tenant1
    display_name: Alice
    suspended: true
  register: alice

- name: Show the tenant-qualified uid croit assigned
  ansible.builtin.debug:
    msg: "Created {{ alice.user.uid }}"

- name: Delete a user that no longer owns any buckets
  croit.ceph.s3_user:
    uid: backup
    state: absent
"""

RETURN = r"""
user:
  description:
    - The user as croit reports it after the change (C(RgwUserResponse) in the croit API).
    - In check mode, the user as it was before; empty when the user does not exist or was deleted.
    - The user's access keys are never part of this result.
  returned: always
  type: dict
  contains:
    uid:
      description: The user id, tenant-qualified as C(tenant$uid) where the user has a tenant.
      returned: when the user exists
      type: str
      sample: backup
    name:
      description: The display name.
      returned: when the user exists
      type: str
      sample: Backup service
    email:
      description: The email address, empty where none is set.
      returned: when the user exists
      type: str
      sample: backup@example.com
    suspended:
      description: Whether RGW refuses the user's requests.
      returned: when the user exists
      type: bool
      sample: false
    defaultPlacement:
      description: Placement rule new buckets land on, or null for the zone's default.
      returned: when the user exists
      type: str
      sample: default-placement
    defaultStorageClass:
      description: Storage class new objects land on, or null for the placement rule's own.
      returned: when the user exists
      type: str
      sample: STANDARD
    subusers:
      description: The user's subusers, each with C(subuser) and C(permissions).
      returned: when the user exists
      type: list
      elements: dict
      sample:
        - subuser: reader
          permissions: read
    userQuota:
      description: The quota over all of the user's buckets together, with C(enabled), C(maxSize) and C(maxObjects).
      returned: when the user exists
      type: dict
      sample:
        enabled: true
        maxSize: 10995116277760
        maxObjects: -1
    bucketQuota:
      description: The quota applied to each of the user's buckets, with C(enabled), C(maxSize) and C(maxObjects).
      returned: when the user exists
      type: dict
      sample:
        enabled: false
        maxSize: -1
        maxObjects: -1
task:
  description:
    - The croit background task the change ran as (C(ManagedTask) in the croit API).
    - With O(wait=true) this is the finished task; with O(wait=false) it may still be running.
  returned: when the change ran as a croit background task
  type: dict
  contains:
    id:
      description: The task's id, usable with M(croit.ceph.task) and M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as croit's task list shows it.
      returned: always
      type: str
      sample: Create S3 user
    state:
      description: The task's state, one of V(WAITING), V(RUNNING), V(FINISHED), V(FAILED) or V(CANCELED).
      returned: always
      type: str
      sample: FINISHED
    done:
      description: Whether the task has ended.
      returned: always
      type: bool
      sample: true
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: Creating user backup ... done
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
