# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""In-memory fake of croit's S3 (RGW) endpoints, for the s3_* module tests."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import json

from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit

U = r"(?P<uid>[^/]+)"
B = r"(?P<name>[^/]+)"


def unlimited_quota():
    return dict(enabled=False, maxSize=-1, maxObjects=-1)


class S3Cluster(FakeCroit):
    def __init__(self):
        super(S3Cluster, self).__init__()
        self.users = {}
        self.keys = []
        self.buckets = {}
        self.details = {}
        self.policies = {}
        self.serve_tasks()

        # users
        self.route("GET", "/s3/users", self.list_users)
        self.route("POST", "/s3/users", self.create_user)
        self.route("PATCH", "/s3/users/" + U, self.patch_user)
        self.route("DELETE", "/s3/users/" + U, self.delete_user)
        self.route("PUT", "/s3/users/" + U + "/quota", lambda c, uid: self.set_quota(c, uid, "userQuota"))
        self.route("PUT", "/s3/users/" + U + "/bucket-quota", lambda c, uid: self.set_quota(c, uid, "bucketQuota"))
        self.route("GET", "/s3/users/" + U + "/buckets", self.user_buckets)
        # subusers
        self.route("GET", "/s3/users/" + U + "/subusers", self.list_subusers)
        self.route("POST", "/s3/users/" + U, self.create_subuser)
        self.route("PATCH", "/s3/users/" + U + "/subusers/(?P<sub>[^/]+)", self.patch_subuser)
        self.route("DELETE", "/s3/users/" + U + "/subusers/(?P<sub>[^/]+)", self.delete_subuser)
        # keys
        self.route("GET", "/s3/users/" + U + "/keys", lambda c, uid: self.list_keys(uid))
        self.route("PUT", "/s3/users/(?P<identity>[^/]+)/keys/(?P<ak>[^/]+)", self.put_key)
        self.route("DELETE", "/s3/users/" + U + "/keys/(?P<ak>[^/]+)", lambda c, uid, ak: self.delete_key(uid, ak))
        self.route("GET", "/s3/users/" + U + "/subusers/(?P<sub>[^/]+)/keys",
                   lambda c, uid, sub: self.list_keys("%s:%s" % (uid, sub)))
        self.route("PUT", "/s3/users/" + U + "/subusers/(?P<sub>[^/]+)/keys/(?P<ak>[^/]+)",
                   lambda c, uid, sub, ak: self.put_key(c, "%s:%s" % (uid, sub), ak))
        self.route("DELETE", "/s3/users/" + U + "/subusers/(?P<sub>[^/]+)/keys/(?P<ak>[^/]+)",
                   lambda c, uid, sub, ak: self.delete_key("%s:%s" % (uid, sub), ak))
        # buckets
        self.route("GET", "/s3/buckets", lambda c: (200, [copy.deepcopy(b) for b in self.buckets.values()]))
        self.route("GET", "/s3/buckets/" + B, self.get_details)
        self.route("PUT", "/s3/buckets/" + B, self.create_bucket)
        self.route("PATCH", "/s3/buckets/" + B, self.patch_bucket)
        self.route("DELETE", "/s3/buckets/" + B, self.delete_bucket)
        self.route("PUT", "/s3/buckets/" + B + "/quota", self.bucket_quota)
        self.route("GET", "/s3/buckets/" + B + "/policy", lambda c, name: (200, dict(policyText=self.policies.get(name))))
        self.route("POST", "/s3/buckets/" + B + "/policy", self.put_policy)
        self.route("DELETE", "/s3/buckets/" + B + "/policy", self.delete_policy)

    # Users -------------------------------------------------------------------

    def add_user(self, uid, name="User", **extra):
        user = dict(
            uid=uid,
            name=name,
            email="",
            suspended=False,
            defaultPlacement=None,
            defaultStorageClass=None,
            subusers=[],
            userQuota=unlimited_quota(),
            bucketQuota=unlimited_quota(),
        )
        user.update(extra)
        self.users[uid] = user
        return user

    def list_users(self, call):
        wanted = call.query.get("uid")
        if wanted is not None and not isinstance(wanted, list):
            wanted = [wanted]
        users = [copy.deepcopy(u) for uid, u in self.users.items() if wanted is None or uid in wanted]
        return 200, users

    def create_user(self, call):
        body = call.body
        uid = "%s$%s" % (body["tenant"], body["uid"]) if body.get("tenant") else body["uid"]
        if uid in self.users:
            return 409, dict(code=409, message="exists")
        self.add_user(uid, body["name"], email=body.get("email") or "",
                      defaultPlacement=body.get("defaultPlacement"),
                      defaultStorageClass=body.get("defaultStorageClass"))
        return 204, None

    def patch_user(self, call, uid):
        user = self.users[uid]
        for key, value in call.body.items():
            if key in ("email", "defaultPlacement") and value == "":
                value = "" if key == "email" else None
            user[key] = value
        return 204, None

    def delete_user(self, call, uid):
        if any(b["owner"] == uid for b in self.buckets.values()):
            return 400, dict(code=400, message="user owns buckets")
        del self.users[uid]
        self.keys = [k for k in self.keys if k["user"].split(":")[0] != uid]
        return 204, None

    def set_quota(self, call, uid, field):
        body = call.body
        assert "enabled" in body
        self.users[uid][field] = dict(enabled=body["enabled"], maxSize=body["maxSize"], maxObjects=body["maxObjects"])
        return 204, None

    def user_buckets(self, call, uid):
        return 200, [copy.deepcopy(b) for b in self.buckets.values() if b["owner"] == uid]

    # Subusers ----------------------------------------------------------------

    def list_subusers(self, call, uid):
        if uid not in self.users:
            return 404, dict(code=404, message="no such user")
        return 200, [dict(id="%s:%s" % (uid, s["subuser"]), permissions=s["permissions"]) for s in self.users[uid]["subusers"]]

    def create_subuser(self, call, uid):
        self.users[uid]["subusers"].append(dict(subuser=call.body["subuser"], permissions=call.body.get("permissions")))
        return 200, self.new_task("Create subuser", uid)

    def patch_subuser(self, call, uid, sub):
        for s in self.users[uid]["subusers"]:
            if s["subuser"] == sub:
                s["permissions"] = call.body.get("permissions")
        return 200, self.new_task("Update subuser", uid)

    def delete_subuser(self, call, uid, sub):
        self.users[uid]["subusers"] = [s for s in self.users[uid]["subusers"] if s["subuser"] != sub]
        self.keys = [k for k in self.keys if k["user"] != "%s:%s" % (uid, sub)]
        return 200, self.new_task("Delete subuser", uid)

    # Keys --------------------------------------------------------------------

    def add_key(self, user, access_key, secret_key):
        self.keys.append(dict(user=user, access_key=access_key, secret_key=secret_key))

    def list_keys(self, identity):
        return 200, [copy.deepcopy(k) for k in self.keys if k["user"] == identity]

    def put_key(self, call, identity, ak):
        for key in self.keys:
            if key["access_key"] == ak:
                if key["user"] != identity:
                    return 400, dict(code=400, message="access key belongs to another user")
                key["secret_key"] = call.query["secretKey"]
                return 204, None
        self.add_key(identity, ak, call.query["secretKey"])
        return 204, None

    def delete_key(self, identity, ak):
        self.keys = [k for k in self.keys if not (k["user"] == identity and k["access_key"] == ak)]
        return 204, None

    # Buckets -----------------------------------------------------------------

    def add_bucket(self, name, owner, objects=0, versioning="OFF", acl=None, policy=None):
        self.buckets[name] = dict(
            bucket=name,
            owner=owner,
            id="id-" + name,
            placement_rule="default-placement",
            tenant=name.split(":")[0] if ":" in name else "",
            usage={},
            usageSum=dict(numObjects=objects, sizeKiB=0, sizeKiBActual=0, sizeFormatted="0 B"),
            bucket_quota=unlimited_quota(),
        )
        self.details[name] = dict(
            acl=acl if acl is not None else [
                dict(grantee="SINGLE_USER", permission="FullControl", userId=owner, displayName="Owner")
            ],
            cors=[],
            versioning=versioning,
        )
        self.policies[name] = json.dumps(policy) if policy else None

    def get_details(self, call, name):
        if name not in self.details:
            return 404, dict(code=404, message="no such bucket")
        return 200, copy.deepcopy(self.details[name])

    def create_bucket(self, call, name):
        body = call.body
        owner = body["owner"]
        full = "%s:%s" % (owner.split("$")[0], name) if "$" in owner else name
        self.add_bucket(full, owner, versioning="ENABLED" if body.get("versioning") == "ENABLED" or body.get("objectLock") else "OFF",
                        acl=body.get("acl"))
        self.last_create = body
        return 200, self.new_task("Create bucket", full)

    def patch_bucket(self, call, name):
        body = call.body
        if "owner" in body:
            self.buckets[name]["owner"] = body["owner"]
        if "acl" in body:
            if not body["acl"]:
                return 400, dict(code=400, message="empty acl")
            self.details[name]["acl"] = body["acl"]
        if "versioning" in body:
            wanted = body["versioning"]
            if wanted == "OFF" and self.details[name]["versioning"] != "OFF":
                wanted = "SUSPENDED"
            self.details[name]["versioning"] = wanted
        return 204, None

    def delete_bucket(self, call, name):
        bucket = self.buckets[name]
        if bucket["usageSum"]["numObjects"] and not call.body.get("deleteData"):
            return 400, dict(code=400, message="bucket not empty")
        del self.buckets[name]
        del self.details[name]
        self.policies.pop(name, None)
        return 200, self.new_task("Delete bucket", name)

    def bucket_quota(self, call, name):
        body = call.body
        self.buckets[name]["bucket_quota"] = dict(enabled=body["enabled"], maxSize=body["maxSize"], maxObjects=body["maxObjects"])
        return 204, None

    def put_policy(self, call, name):
        # Store it re-serialised with different key order, as S3 would.
        self.policies[name] = json.dumps(call.body, sort_keys=True, indent=2)
        return 204, None

    def delete_policy(self, call, name):
        self.policies[name] = None
        return 204, None
