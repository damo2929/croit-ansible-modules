#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /s3/buckets
# croit-api: GET /s3/buckets/{bucketName}
# croit-api: PUT /s3/buckets/{bucketName}
# croit-api: PATCH /s3/buckets/{bucketName}
# croit-api: DELETE /s3/buckets/{bucketName}
# croit-api: PUT /s3/buckets/{bucketName}/quota
# croit-api: GET /s3/buckets/{bucketName}/policy
# croit-api: POST /s3/buckets/{bucketName}/policy
# croit-api: DELETE /s3/buckets/{bucketName}/policy

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: s3_bucket
short_description: Manage S3 buckets on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete S3 buckets of the Ceph object gateway through the croit API, including the
    owner, versioning, access control list, quota and bucket policy.
  - Only options that are set are managed; anything left out keeps its current value.
  - Settings that can only be chosen at creation (placement, object lock, pre-sharding) are used when the
    bucket is created and ignored afterwards.
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
  name:
    description:
      - The bucket's name. A bucket in a tenant is addressed as C(tenant:bucket).
    type: str
    required: true
  state:
    description:
      - Whether the bucket should exist.
      - V(absent) needs O(confirm_delete=true). A bucket that still holds objects is only deleted with
        O(purge_objects=true), which deletes B(all its objects).
    type: str
    choices: [present, absent]
    default: present
  owner:
    description:
      - The S3 user that owns the bucket. Required when the bucket is created.
      - Changing it gives the bucket to another user of the same tenant. Moving a bucket to another tenant
        is not supported, because it changes the bucket's name.
    type: str
  placement:
    description:
      - Placement rule the bucket's data lands on. The zone's default when not set.
      - Only used when the bucket is created.
    type: str
  object_lock:
    description:
      - Enable S3 object lock (retention and legal hold). It also enables versioning.
      - Only used when the bucket is created.
    type: bool
  expected_number_of_objects:
    description:
      - Pre-shard the bucket index for about this many objects. Leave unset if in doubt.
      - Only used when the bucket is created.
    type: int
  versioning:
    description:
      - Whether the bucket keeps old versions of its objects.
      - S3 cannot turn versioning off once it was enabled, only suspend it. V(suspended) is also satisfied
        by a bucket that never had versioning.
    type: str
    choices: [enabled, suspended]
  acl:
    description:
      - The complete access control list of the bucket. Grants that are not listed are removed, so include
        the owner's own C(full_control) grant.
      - An empty list is refused by croit.
    type: list
    elements: dict
    suboptions:
      grantee:
        description: Who the grant is for.
        type: str
        required: true
        choices: [single_user, all_users, authenticated_users, log_delivery]
      permission:
        description: What the grantee may do.
        type: str
        required: true
        choices: [read, write, read_acp, write_acp, full_control]
      user_id:
        description: The S3 user, for O(acl[].grantee=single_user).
        type: str
  quota:
    description:
      - Quota the bucket is held to. Only the sub-options that are set are managed.
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
  policy:
    description:
      - The bucket policy, as a dict or a JSON string. It replaces the whole policy, and is compared as parsed
        JSON, so formatting and key order do not matter.
      - An empty dict or empty string removes the policy.
    type: raw
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing bucket.
    type: bool
    default: false
  purge_objects:
    description:
      - With O(state=absent), also delete every object in the bucket. Without it, croit refuses to delete a
        bucket that still holds objects.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Versioned bucket for backups with a quota
  croit.ceph.s3_bucket:
    api_url: https://croit-mgmt/api
    api_token: "{{ vault_croit_token }}"
    name: backups
    owner: backup
    versioning: enabled
    quota:
      enabled: true
      max_size: 5T

- name: Public read access through a bucket policy
  croit.ceph.s3_bucket:
    name: website
    owner: web
    policy:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Principal: "*"
          Action: ["s3:GetObject"]
          Resource: ["arn:aws:s3:::website/*"]

- name: Delete a bucket and everything in it
  croit.ceph.s3_bucket:
    name: scratch
    state: absent
    confirm_delete: true
    purge_objects: true
"""

RETURN = r"""
bucket:
  description:
    - The bucket as croit lists it after the change (C(RgwBucketResponse) in the croit API).
    - When O(acl) or O(versioning) is set it also has C(acl) and C(versioning) (from C(BucketDetails)), and
      when O(policy) is set, C(policy) as parsed JSON (or null).
    - Before the change in check mode; empty when the bucket does not exist.
  returned: always
  type: dict
  sample:
    bucket: backups
    owner: backup
    placement_rule: default-placement
    bucket_quota:
      enabled: true
      maxSize: 5497558138880
      maxObjects: -1
    versioning: ENABLED
task:
  description: The last croit background task the change ran as, when there was one.
  returned: when a task ran
  type: dict
"""

import json

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.rgw import parse_quota_size, quota_view

DELETE_CONFIRMATION = "I'm really sure that I want to delete this"

VERSIONING = dict(enabled="ENABLED", suspended="SUSPENDED")
GRANTEES = dict(
    single_user="SINGLE_USER",
    all_users="ALL_USERS",
    authenticated_users="AUTHENTICATED_USERS",
    log_delivery="LOG_DELIVERY",
)
PERMISSIONS = dict(read="Read", write="Write", read_acp="ReadAcp", write_acp="WriteAcp", full_control="FullControl")


# ACL helpers -----------------------------------------------------------------


def acl_key(entry):
    user = entry.get("userId") if entry.get("grantee") == "SINGLE_USER" else None
    return (entry.get("grantee"), entry.get("permission"), user or "")


def acl_canonical(entries):
    """An ACL as a sorted list of API entries, ignoring display names and order."""
    result = []
    for grantee, permission, user in sorted(set(acl_key(e) for e in entries or [])):
        entry = dict(grantee=grantee, permission=permission)
        if grantee == "SINGLE_USER":
            entry["userId"] = user
        result.append(entry)
    return result


# Policy helpers ----------------------------------------------------------------


def parse_policy(value, what):
    """Parsed policy dict, or {} for none."""
    if value is None or value == "" or value == {}:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as e:
            raise ValueError("%s is not valid JSON: %s" % (what, e))
    if not isinstance(value, dict):
        raise ValueError("%s must be a JSON object" % what)
    return value


def bucket_tenant(name):
    return name.split(":", 1)[0] if ":" in name else ""


def owner_tenant(owner):
    return owner.split("$", 1)[0] if "$" in owner else ""


class S3BucketModule(CroitModule):
    def __init__(self):
        super(S3BucketModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                owner=dict(type="str"),
                placement=dict(type="str"),
                object_lock=dict(type="bool"),
                expected_number_of_objects=dict(type="int"),
                versioning=dict(type="str", choices=list(VERSIONING)),
                acl=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        grantee=dict(type="str", required=True, choices=list(GRANTEES)),
                        permission=dict(type="str", required=True, choices=list(PERMISSIONS)),
                        user_id=dict(type="str"),
                    ),
                ),
                quota=dict(
                    type="dict",
                    options=dict(
                        enabled=dict(type="bool"),
                        max_size=dict(type="str"),
                        max_objects=dict(type="int"),
                    ),
                ),
                policy=dict(type="raw"),
                confirm_delete=dict(type="bool", default=False),
                purge_objects=dict(type="bool", default=False),
            ),
        )

    # Reads ------------------------------------------------------------------

    def find_bucket(self, name):
        for bucket in self.get_list("/s3/buckets"):
            if bucket.get("bucket") == name:
                return bucket
        return None

    def details(self, name, owner):
        return self.get(path_join("s3", "buckets", name), query=dict(owner=owner)) or {}

    def current_policy(self, name, owner):
        answer = self.get(path_join("s3", "buckets", name, "policy"), query=dict(owner=owner)) or {}
        text = answer.get("policyText")
        try:
            return parse_policy(text, "the bucket's current policy")
        except ValueError as e:
            self.module.fail_json(msg=str(e))

    def read_full(self, name):
        """The bucket from the list, enriched with what the options manage."""
        bucket = self.find_bucket(name)
        if bucket is None:
            return None
        bucket = dict(bucket)
        p = self.params
        if p["acl"] is not None or p["versioning"] is not None:
            details = self.details(name, bucket.get("owner"))
            bucket["acl"] = details.get("acl") or []
            bucket["versioning"] = details.get("versioning")
        if p["policy"] is not None:
            policy = self.current_policy(name, bucket.get("owner"))
            bucket["policy"] = policy or None
        return bucket

    # Desired ----------------------------------------------------------------

    def desired_acl(self):
        acl = self.params["acl"]
        if acl is None:
            return None
        entries = []
        for item in acl:
            entry = dict(grantee=GRANTEES[item["grantee"]], permission=PERMISSIONS[item["permission"]])
            if item["grantee"] == "single_user":
                if not item.get("user_id"):
                    self.module.fail_json(msg="acl entries with grantee=single_user need user_id")
                entry["userId"] = item["user_id"]
            elif item.get("user_id"):
                self.module.fail_json(msg="user_id is only valid for acl entries with grantee=single_user")
            entries.append(entry)
        if not entries:
            self.module.fail_json(msg="acl must not be empty; croit refuses an empty access control list")
        return acl_canonical(entries)

    def desired_quota(self):
        quota = self.params["quota"]
        if not quota:
            return None
        try:
            size = parse_quota_size(quota.get("max_size"))
        except ValueError as e:
            self.module.fail_json(msg="quota.max_size: %s" % e)
        return dict(enabled=quota.get("enabled"), max_size=size, max_objects=quota.get("max_objects"))

    def desired_policy(self):
        if self.params["policy"] is None:
            return None
        try:
            return parse_policy(self.params["policy"], "policy")
        except ValueError as e:
            self.module.fail_json(msg=str(e))

    # Main -------------------------------------------------------------------

    def run(self):
        p = self.params
        name = p["name"]
        if p["state"] == "absent":
            self.absent(name, self.find_bucket(name))
        current = self.read_full(name)
        if current is None:
            self.create(name)
        self.update(name, current)

    def absent(self, name, current):
        if current is None:
            self.exit(changed=False, bucket={})
        if not self.params["confirm_delete"]:
            self.module.fail_json(msg="Refusing to delete bucket %r without confirm_delete=true" % name)
        objects = (current.get("usageSum") or {}).get("numObjects") or 0
        if objects and not self.params["purge_objects"]:
            self.module.fail_json(
                msg="Bucket %r still holds %d object(s); set purge_objects=true to delete them with it" % (name, objects)
            )
        before = dict(owner=current.get("owner"), objects=objects)
        task = None
        if not self.check_mode:
            body = dict(name=name)
            if self.params["purge_objects"]:
                body.update(deleteData=True, thisWillDeleteData=DELETE_CONFIRMATION)
            task = self.handle_task(self.write("DELETE", path_join("s3", "buckets", name), body=body))
        result = dict(changed=True, before=before, after={}, bucket={})
        if task is not None:
            result["task"] = task
        self.exit(**result)

    def check_owner(self, name, owner):
        if owner is not None and owner_tenant(owner) != bucket_tenant(name):
            self.module.fail_json(
                msg="owner %r is in tenant %r but bucket %r is in tenant %r; moving buckets between tenants is "
                "not supported" % (owner, owner_tenant(owner), name, bucket_tenant(name))
            )

    def create(self, name):
        p = self.params
        if not p["owner"]:
            self.module.fail_json(msg="owner is required to create bucket %r" % name)
        self.check_owner(name, p["owner"])
        if p["object_lock"] and p["versioning"] == "suspended":
            self.module.fail_json(msg="object_lock enables versioning, so versioning cannot be suspended")
        acl = self.desired_acl()
        quota = self.desired_quota()
        policy = self.desired_policy()

        after = dict(owner=p["owner"])
        if p["versioning"]:
            # A new bucket without versioning reports OFF, which satisfies "suspended".
            after["versioning"] = "ENABLED" if p["versioning"] == "enabled" or p["object_lock"] else "OFF"
        if acl is not None:
            after["acl"] = acl
        if quota:
            merged = quota_view(None)
            merged.update((k, v) for k, v in quota.items() if v is not None)
            after["quota"] = merged
        if policy:
            after["policy"] = policy
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, bucket={})

        body = dict(owner=p["owner"])
        for opt, api in (("placement", "placement"), ("object_lock", "objectLock"),
                         ("expected_number_of_objects", "expectedNumberOfObjects")):
            if p[opt] is not None:
                body[api] = p[opt]
        if p["versioning"] == "enabled":
            body["versioning"] = "ENABLED"
        if acl is not None:
            body["acl"] = acl
        bare = name.split(":", 1)[1] if ":" in name else name
        tasks = [self.handle_task(self.write("PUT", path_join("s3", "buckets", bare), body=body))]
        # Suspending is not possible in the create request; a new bucket has no versioning anyway.
        if quota and "quota" in after and after["quota"] != quota_view(None):
            tasks.append(self.put_quota(name, after["quota"]))
        if policy:
            tasks.append(self.put_policy(name, p["owner"], policy))
        self.finish(name, {}, after, tasks)

    def update(self, name, current):
        p = self.params
        self.check_owner(name, p["owner"])
        before, after = {}, {}
        patch = {}
        tasks = []

        if p["owner"] is not None:
            before["owner"] = after["owner"] = current.get("owner")
            if p["owner"] != current.get("owner"):
                patch["owner"] = after["owner"] = p["owner"]

        if p["versioning"] is not None:
            state = current.get("versioning")
            before["versioning"] = after["versioning"] = state
            wanted = VERSIONING[p["versioning"]]
            satisfied = state == wanted or (wanted == "SUSPENDED" and state == "OFF")
            if not satisfied:
                patch["versioning"] = after["versioning"] = wanted

        acl = self.desired_acl()
        if acl is not None:
            current_acl = acl_canonical(current.get("acl"))
            before["acl"] = after["acl"] = current_acl
            if acl != current_acl:
                patch["acl"] = after["acl"] = acl

        quota_update = None
        quota = self.desired_quota()
        if quota:
            current_quota = quota_view(current.get("bucket_quota"))
            merged = dict(current_quota)
            merged.update((k, v) for k, v in quota.items() if v is not None)
            before["quota"] = current_quota
            after["quota"] = merged
            if merged != current_quota:
                quota_update = merged

        policy = self.desired_policy()
        policy_change = False
        if policy is not None:
            current_policy = current.get("policy") or {}
            before["policy"] = current_policy or None
            after["policy"] = policy or None
            policy_change = policy != current_policy

        changed = bool(patch) or quota_update is not None or policy_change
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, bucket=current)

        owner = patch.get("owner") or current.get("owner")
        if patch:
            tasks.append(self.handle_task(self.write("PATCH", path_join("s3", "buckets", name), body=patch)))
        if quota_update is not None:
            tasks.append(self.put_quota(name, quota_update))
        if policy_change:
            if policy:
                tasks.append(self.put_policy(name, owner, policy))
            else:
                tasks.append(
                    self.handle_task(
                        self.write("DELETE", path_join("s3", "buckets", name, "policy"), query=dict(owner=owner))
                    )
                )
        self.finish(name, before, after, tasks)

    def put_quota(self, name, view):
        body = dict(enabled=view["enabled"], maxSize=view["max_size"], maxObjects=view["max_objects"])
        return self.handle_task(self.write("PUT", path_join("s3", "buckets", name, "quota"), body=body))

    def put_policy(self, name, owner, policy):
        return self.handle_task(
            self.write("POST", path_join("s3", "buckets", name, "policy"), body=policy, query=dict(owner=owner))
        )

    def finish(self, name, before, after, tasks):
        result = dict(changed=True, before=before, after=after, bucket=self.read_full(name) or {})
        tasks = [t for t in tasks if t is not None]
        if tasks:
            result["task"] = tasks[-1]
        self.exit(**result)


def main():
    S3BucketModule().run()


if __name__ == "__main__":
    main()
