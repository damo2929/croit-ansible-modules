#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /keys
# croit-api: POST /keys
# croit-api: PATCH /keys/{user}
# croit-api: DELETE /keys/{user}
# croit-api: GET /keys/{user}/download

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: ceph_key
short_description: Manage Ceph keys (cephx users) on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete Ceph keys (cephx users such as C(client.backup)) through the croit API.
    A key is identified by its fully qualified entity name O(name).
  - Capabilities are given per daemon type as the strings ceph stores, for example
    C(profile rbd pool=vms). They are compared ignoring whitespace differences, so reformatting a
    capability string does not report a change.
  - Only options that are set are managed; options left unset keep their current value. When O(caps)
    is set it is the key's B(complete) set of capabilities, as with C(ceph auth caps); daemon types left
    out of it get no capabilities.
  - The key secret is never part of the diff or of RV(key). It is only returned, in RV(keyring), when
    O(return_keyring=true).
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
      - Fully qualified ceph entity name of the key, for example V(client.backup).
      - The name must contain a dot (C(<type>.<id>)); a bare name such as V(backup) fails.
    type: str
    required: true
  state:
    description:
      - Whether the key should exist.
      - V(absent) deletes the key. Every client still authenticating with it loses access to the cluster
        immediately, and the secret cannot be recovered.
    type: str
    choices: [present, absent]
    default: present
  caps:
    description:
      - Capabilities of the key per daemon type. This is the complete set; daemon types not listed, or
        set to an empty value, get no capabilities.
      - When not set, the capabilities of an existing key are left alone, and a new key is created
        without any capabilities.
    type: dict
    suboptions:
      mon:
        description: Capabilities on the monitors, for example V(profile rbd).
        type: str
      osd:
        description: Capabilities on the OSDs, for example V(profile rbd pool=vms).
        type: str
      mds:
        description: Capabilities on the metadata servers, for example V(allow rw path=/data).
        type: str
      mgr:
        description: Capabilities on the managers, for example V(profile rbd pool=vms).
        type: str
  comment:
    description:
      - Free text croit keeps about what the key is for. Ceph itself does not store it.
      - When not set, the comment is left alone, and a new key is created with an empty comment.
        V("") clears the comment.
    type: str
  key_type:
    description:
      - Encryption the key is created with. When not set, the cluster's preference is used, which is
        what nearly every key wants. Choose V(aes) only for clients too old for V(aes256k).
      - Only used when the key is created; croit does not report it back, so it is not compared.
    type: str
    choices: [aes256k, aes]
  return_keyring:
    description:
      - Return the key's keyring file in RV(keyring). It contains the secret, so keep the result out
        of logs, for example with C(no_log) on the task.
      - Never done in check mode for a key that does not exist yet.
    type: bool
    default: false
notes:
  - Deleting a key cuts off every client that uses it, immediately. There is no confirmation option,
    because no data is lost, but the secret cannot be recovered.
  - croit warns before changing or deleting system keys (for example C(client.admin)); see
    O(ignore_warnings).
  - It is assumed that a capability change which leaves out a daemon type removes that daemon type's
    capabilities, like C(ceph auth caps). This has not been verified against a live croit cluster.
seealso:
  - module: croit.ceph.ceph_key_info
    description: List Ceph keys and their capabilities.
  - module: croit.ceph.pool
    description: Manage the pools the capabilities refer to.
  - name: croit API reference
    description: The croit REST API, including the C(/keys) endpoints.
    link: https://www.croit.io/api-docs
  - name: Ceph user management
    description: Upstream documentation of cephx users and capabilities.
    link: https://docs.ceph.com/en/latest/rados/operations/user-management/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Key for an RBD client
  croit.ceph.ceph_key:
    name: client.vms
    comment: Hypervisors
    caps:
      mon: profile rbd
      osd: profile rbd pool=vms
      mgr: profile rbd pool=vms

- name: Restrict a CephFS client to one directory
  croit.ceph.ceph_key:
    name: client.data
    caps:
      mon: allow r
      mds: allow rw path=/data
      osd: allow rw tag cephfs data=cephfs

- name: Change only the comment, keeping the capabilities
  croit.ceph.ceph_key:
    name: client.vms
    comment: KVM hypervisors (rack 3)

- name: Fetch the keyring for distribution
  croit.ceph.ceph_key:
    name: client.vms
    return_keyring: true
  register: vms_key
  no_log: true

- name: Write the keyring to the hypervisors
  ansible.builtin.copy:
    content: "{{ vms_key.keyring.contents }}"
    dest: /etc/ceph/ceph.client.vms.keyring
    mode: "0600"
  delegate_to: "{{ item }}"
  loop: "{{ groups['hypervisors'] }}"
  no_log: true

- name: Remove a key that is no longer used
  croit.ceph.ceph_key:
    name: client.old
    state: absent
"""

RETURN = r"""
key:
  description:
    - The key as croit reports it after the change (C(CephUserResponse) in the croit API), without the
      secret.
    - Before the change in check mode; empty when the key does not exist.
  returned: always
  type: dict
  contains:
    user:
      description: The ceph entity name.
      returned: when the key exists
      type: str
      sample: client.vms
    comment:
      description: What croit was told the key is for.
      returned: when the key exists
      type: str
      sample: Hypervisors
    rawPermissions:
      description: The capability strings ceph stores, per daemon type. A daemon type without capabilities is null.
      returned: when the key exists
      type: dict
      sample:
        mon: profile rbd
        osd: profile rbd pool=vms
        mgr: profile rbd pool=vms
        mds: null
    permissions:
      description: The capabilities in whichever structured shape croit could read them as; C(type) says which.
      returned: when the key exists
      type: dict
      sample:
        type: RbdCephPermissions
keyring:
  description:
    - The key's keyring file. It contains the secret; keep it out of logs with C(no_log).
  returned: when O(return_keyring=true) and the key exists
  type: dict
  contains:
    file_name:
      description: Name to save the file as.
      returned: always
      type: str
      sample: ceph.client.vms.keyring
    contents:
      description: The keyring, including the secret. Only present when croit answers small files inline; null otherwise.
      returned: always
      type: str
      sample: "[client.vms]\n\tkey = ********\n"
    url:
      description: Expiring croit download link to the keyring.
      returned: always
      type: str
      sample: https://croit-mgmt/api/download/3f2a9c
"""

import re

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

DAEMONS = ("mon", "osd", "mds", "mgr")
SECRET_FIELDS = ("key",)


def normalise_cap(value):
    """Canonical form of a capability string, for comparison only.

    Collapses whitespace and drops it around ``,`` and ``=``; an empty or
    missing cap is None.
    """
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*=\s*", "=", text)
    return text or None


def current_caps(key):
    raw = (key or {}).get("rawPermissions") or {}
    return dict((d, raw.get(d) or None) for d in DAEMONS)


def strip_secret(key):
    if not key:
        return {}
    return dict((k, v) for k, v in key.items() if k not in SECRET_FIELDS)


def view(key):
    if not key:
        return {}
    return dict(name=key.get("user"), comment=key.get("comment") or "", caps=current_caps(key))


class CephKeyModule(CroitModule):
    def __init__(self):
        super(CephKeyModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                caps=dict(
                    type="dict",
                    options=dict((d, dict(type="str")) for d in DAEMONS),
                ),
                comment=dict(type="str"),
                key_type=dict(type="str", choices=["aes256k", "aes"]),
                return_keyring=dict(type="bool", default=False),
            ),
            wait=False,
        )

    def find_key(self, name):
        # System keys are hidden by default; include them so client.admin & co. can be managed.
        for key in self.get_list("/keys", query=dict(includeSystemKeys=True)):
            if key.get("user") == name:
                return key
        return None

    def desired_caps(self):
        caps = self.params["caps"]
        if caps is None:
            return None
        return dict((d, caps.get(d) or None) for d in DAEMONS)

    def keyring(self, name):
        data = self.get(path_join("keys", name, "download")) or {}
        return dict(file_name=data.get("fileName"), contents=data.get("fileContents"), url=data.get("url"))

    def finish(self, changed, before, after, key):
        result = dict(changed=changed, before=before, after=after, key=strip_secret(key))
        if self.params["return_keyring"] and key:
            result["keyring"] = self.keyring(key["user"])
        self.exit(**result)

    def run(self):
        p = self.params
        name = p["name"]
        if "." not in name:
            self.module.fail_json(msg="name must be a fully qualified ceph entity such as client.%s" % name)
        current = self.find_key(name)

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, key={})
            if not self.check_mode:
                self.write("DELETE", path_join("keys", name))
            self.exit(changed=True, before=view(current), after={}, key={})

        caps = self.desired_caps()
        raw = dict((d, v) for d, v in (caps or {}).items() if v is not None)
        permissions = dict(raw, type="RawCephPermissions")

        if current is None:
            after = dict(name=name, comment=p["comment"] or "", caps=caps or dict((d, None) for d in DAEMONS))
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, key={})
            body = dict(user=name, comment=p["comment"] or "", permissions=permissions)
            if p["key_type"]:
                body["keyType"] = p["key_type"]
            self.write("POST", "/keys", body=body)
            self.finish(True, {}, after, self.find_key(name))

        before = view(current)
        after = dict(before, caps=dict(before["caps"]))
        changes = {}
        if p["comment"] is not None and p["comment"] != before["comment"]:
            changes["comment"] = p["comment"]
            after["comment"] = p["comment"]
        if caps is not None:
            have = dict((d, normalise_cap(v)) for d, v in before["caps"].items())
            want = dict((d, normalise_cap(v)) for d, v in caps.items())
            if have != want:
                changes["permissions"] = permissions
                after["caps"] = caps

        if not changes:
            self.finish(False, before, after, current)
        if self.check_mode:
            self.finish(True, before, after, current)
        self.write("PATCH", path_join("keys", name), body=changes)
        self.finish(True, before, after, self.find_key(name))


def main():
    CephKeyModule().run()


if __name__ == "__main__":
    main()
