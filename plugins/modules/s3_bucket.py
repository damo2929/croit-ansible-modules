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
  - Create, update and delete S3 buckets of the Ceph object gateway (RGW) through the croit API, including the
    owner, versioning, access control list, quota and bucket policy.
  - The bucket is identified by O(name). Only options that are set are managed; anything left out keeps its
    current value.
  - Settings that can only be chosen at creation (O(placement), O(object_lock), O(expected_number_of_objects)) are
    used when the bucket is created and ignored afterwards.
  - Deleting a bucket needs O(confirm_delete=true), and a bucket that still holds objects also needs
    O(purge_objects=true), which deletes all of its objects.
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
      - The S3 user that owns the bucket, tenant-qualified as C(tenant$uid) where the user has a tenant.
      - Required when the bucket is created. Changing it gives the bucket to another user of the same tenant.
      - The owner must be in the bucket's tenant; moving a bucket to another tenant is refused, because it
        would change the bucket's name.
    type: str
  placement:
    description:
      - Placement rule the bucket's data lands on, as managed with M(croit.ceph.s3_placement).
      - When not set, the owner's default placement or the zone's default is used.
      - Only used when the bucket is created.
    type: str
  object_lock:
    description:
      - Enable S3 object lock (retention and legal hold) on the bucket. Object lock also enables versioning, so it
        cannot be combined with O(versioning=suspended).
      - Only used when the bucket is created.
    type: bool
  expected_number_of_objects:
    description:
      - Pre-shard the bucket index for about this many objects. Leave unset if in doubt; RGW reshards
        dynamically.
      - Only used when the bucket is created.
    type: int
  versioning:
    description:
      - Whether the bucket keeps old versions of its objects.
      - S3 cannot turn versioning off once it was enabled, only suspend it. V(suspended) is therefore also
        satisfied by a bucket that never had versioning.
    type: str
    choices: [enabled, suspended]
  acl:
    description:
      - The complete access control list of the bucket. Grants that are not listed are removed, so include the
        owner's own V(full_control) grant.
      - Compared as a set; the order of the entries and display names do not matter.
      - An empty list is refused, because croit cannot store an empty access control list.
    type: list
    elements: dict
    suboptions:
      grantee:
        description:
          - Who the grant is for. V(single_user) needs O(acl[].user_id); V(all_users) means anonymous access,
            V(authenticated_users) any S3 user of the cluster, and V(log_delivery) the log delivery group.
        type: str
        required: true
        choices: [single_user, all_users, authenticated_users, log_delivery]
      permission:
        description:
          - What the grantee may do. V(read) and V(write) apply to the bucket's objects, V(read_acp) and V(write_acp)
            to its access control list, and V(full_control) to all of these.
        type: str
        required: true
        choices: [read, write, read_acp, write_acp, full_control]
      user_id:
        description:
          - The S3 user the grant is for. Required for, and only valid with, O(acl[].grantee=single_user).
        type: str
  quota:
    description:
      - Quota the bucket is held to. Only the sub-options that are set are managed; the others keep their current
        values.
      - The default for all of a user's buckets is O(croit.ceph.s3_user#module:bucket_quota).
    type: dict
    suboptions:
      enabled:
        description: Whether the quota is enforced. A quota with bounds but V(false) here is not enforced.
        type: bool
      max_size:
        description:
          - Maximum size, as bytes or with a binary unit such as V(500G) or V(5T).
          - V(-1) or V(unlimited) means no size bound.
        type: str
      max_objects:
        description: Maximum number of objects. V(-1) means no object bound.
        type: int
  policy:
    description:
      - The bucket policy, as a dict or a JSON string. It replaces the whole policy, and is compared as parsed JSON,
        so formatting and key order do not matter.
      - An empty dict or an empty string removes the policy.
    type: raw
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing bucket. Without it the module fails, in check mode
        as well.
    type: bool
    default: false
  purge_objects:
    description:
      - With O(state=absent), also delete every object in the bucket. Without it, the module refuses to delete a
        bucket that still holds objects.
    type: bool
    default: false
notes:
  - Deleting a bucket with O(purge_objects=true) irreversibly deletes all of its objects and their versions.
  - The object count used for the O(purge_objects) check comes from croit's bucket list, which can lag behind
    writes for a short time.
seealso:
  - module: croit.ceph.s3_bucket_info
    description: Read buckets with their ACL, versioning, CORS rules and policy.
  - module: croit.ceph.s3_user
    description: Manage the S3 users that own buckets, and their default bucket quota.
  - module: croit.ceph.s3_placement
    description: Manage the placement rules a bucket can be created on.
  - name: croit API reference
    description: The croit REST API, including the C(/s3/buckets) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph RGW bucket policies
    description: Upstream documentation of the S3 bucket policy language RGW supports.
    link: https://docs.ceph.com/en/latest/radosgw/bucketpolicy/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Create a versioned bucket for backups with a 5 TiB quota
  croit.ceph.s3_bucket:
    name: backups
    owner: backup
    versioning: enabled
    quota:
      enabled: true
      max_size: 5T

- name: Give a second user read access, keeping the owner's full control
  croit.ceph.s3_bucket:
    name: backups
    acl:
      - grantee: single_user
        user_id: backup
        permission: full_control
      - grantee: single_user
        user_id: auditor
        permission: read

- name: Allow anonymous reads through a bucket policy
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
  register: website

- name: Show the policy now stored on the bucket
  ansible.builtin.debug:
    var: website.bucket.policy

- name: Delete a bucket and every object in it
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
    - In check mode, the bucket as it was before. Empty when the bucket does not exist or was deleted.
  returned: always
  type: dict
  contains:
    bucket:
      description: The bucket's name, tenant-qualified as C(tenant:bucket) where it has a tenant.
      returned: when the bucket exists
      type: str
      sample: backups
    owner:
      description: The S3 user that owns the bucket.
      returned: when the bucket exists
      type: str
      sample: backup
    placement_rule:
      description: The placement rule the bucket's data lands on.
      returned: when the bucket exists
      type: str
      sample: default-placement
    tenant:
      description: The bucket's tenant, empty for one that has none.
      returned: when the bucket exists
      type: str
      sample: ""
    bucket_quota:
      description: The quota RGW holds the bucket to, with C(enabled), C(maxSize) and C(maxObjects).
      returned: when the bucket exists
      type: dict
      sample:
        enabled: true
        maxSize: 5497558138880
        maxObjects: -1
    usageSum:
      description: What the bucket holds across every zone, including C(numObjects) and C(sizeKiB).
      returned: when the bucket exists
      type: dict
      sample:
        numObjects: 1520
        sizeKiB: 5242880
    versioning:
      description: The bucket's versioning state, V(ENABLED), V(SUSPENDED) or V(OFF).
      returned: when the bucket exists and O(acl) or O(versioning) is set
      type: str
      sample: ENABLED
    acl:
      description: The bucket's access control list (C(AclEntry) in the croit API), each with C(grantee), C(permission) and C(userId).
      returned: when the bucket exists and O(acl) or O(versioning) is set
      type: list
      elements: dict
      sample:
        - grantee: SINGLE_USER
          permission: FullControl
          userId: backup
    policy:
      description: The bucket policy as parsed JSON, or null when the bucket has none.
      returned: when the bucket exists and O(policy) is set
      type: dict
      sample:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal: "*"
            Action: ["s3:GetObject"]
            Resource: ["arn:aws:s3:::website/*"]
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
      sample: Create S3 bucket
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
