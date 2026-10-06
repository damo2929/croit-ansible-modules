#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /maintenance/config-backups
# croit-api: PATCH /maintenance/config-backups
# croit-api: POST /maintenance/config-backups/create
# croit-api: GET /maintenance/config-backups/s3
# croit-api: PUT /maintenance/config-backups/s3
# croit-api: POST /maintenance/config-backups/s3/create

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: config_backup
short_description: Manage croit configuration backups
version_added: 0.1.0
description:
  - Turns croit's daily cloud configuration backups on or off, configures backups to an S3 bucket of
    your own, and optionally takes a backup now.
  - Only options that are set are managed; anything left out keeps its current value.
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
    details:
      - O(run_now) is reported as a change and skipped in check mode.
  diff_mode:
    support: full
options:
  cloud_enabled:
    description:
      - Whether croit uploads an encrypted copy of its configuration to croit's API daily and before
        every update. Needs a registered cluster with a route to croit's API.
    type: bool
  s3:
    description:
      - Backups to an S3 bucket of your own, for a cluster that cannot reach croit's API.
      - Only the sub-options that are set are managed.
    type: dict
    suboptions:
      enabled:
        description:
          - Whether S3 backups are enabled. Enabling makes croit write and remove a test object first,
            and fails when it cannot.
        type: bool
      endpoint:
        description: S3 endpoint URL. An empty string clears it.
        type: str
      bucket:
        description: Bucket to upload to. An empty string clears it.
        type: str
      prefix:
        description: Object key prefix. An empty string clears it.
        type: str
      region:
        description: S3 region. An empty string clears it.
        type: str
      access_key:
        description: S3 access key. An empty string clears it.
        type: str
      secret_key:
        description:
          - S3 secret key. croit never returns it, so it cannot be compared; see O(s3.update_secret).
        type: str
      update_secret:
        description:
          - V(on_create) only sends O(s3.secret_key) when croit has no secret key stored.
          - V(always) sends it on every run, which always reports a change.
        type: str
        choices: [on_create, always]
        default: on_create
      encrypt:
        description:
          - Encrypt the uploaded backups with the cloud backup encryption key. A restore then needs that key.
        type: bool
  run_now:
    description:
      - Take a backup now, after applying the settings, to croit's API (V(cloud)) and/or the S3 bucket (V(s3)).
      - This is an action, not a state. It always reports a change and is skipped in check mode.
    type: list
    elements: str
    choices: [cloud, s3]
  return_encryption_key:
    description:
      - Include the cloud backup encryption key in RV(cloud). It is needed to restore an encrypted backup,
        so keep it somewhere other than this cluster, and treat it as a secret.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Enable cloud backups
  croit.ceph.config_backup:
    cloud_enabled: true

- name: Back up to an internal S3 bucket and take a backup now
  croit.ceph.config_backup:
    s3:
      enabled: true
      endpoint: https://s3.example.internal
      bucket: croit-backups
      prefix: cluster-a/
      access_key: AKIAEXAMPLE
      secret_key: "{{ vault_backup_secret }}"
      encrypt: false
    run_now: [s3]
"""

RETURN = r"""
cloud:
  description:
    - Cloud backup status (C(CloudConfigBackupStatus) in the croit API) after the change.
    - C(backupEncryptionKey) is only included with O(return_encryption_key=true).
  returned: always
  type: dict
  sample:
    enabled: true
    clusterId: 8a9e0c5e-3f4b-4f0e-9e43-5c8f1a2b3c4d
    lastBackupTimestamp: "2026-10-06T02:00:00Z"
s3:
  description: S3 backup status (C(S3ConfigBackupStatus) in the croit API) after the change. Never contains the secret key.
  returned: always
  type: dict
  sample:
    enabled: true
    endpoint: https://s3.example.internal
    bucket: croit-backups
    secretKeySet: true
    encrypt: false
tasks:
  description: The croit tasks the backups taken with O(run_now) ran as, in the order of O(run_now).
  returned: when O(run_now) is set and not in check mode
  type: list
  elements: dict
task:
  description: The croit task of the last backup taken with O(run_now), the same as the last item of RV(tasks).
  returned: when O(run_now) is set and not in check mode
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

CLOUD_PATH = "/maintenance/config-backups"
S3_PATH = "/maintenance/config-backups/s3"
SECRET_MASK = "********"

# Ansible sub-option -> croit field, for the plain S3 settings.
S3_FIELDS = dict(
    enabled="enabled",
    endpoint="endpoint",
    bucket="bucket",
    prefix="prefix",
    region="region",
    access_key="accessKey",
    encrypt="encrypt",
)
S3_TEXT = ("endpoint", "bucket", "prefix", "region", "access_key")


def cloud_view(status):
    return dict(cloud_enabled=bool((status or {}).get("enabled")))


def s3_view(status):
    """S3 settings as Ansible sub-options; empty text means unset."""
    status = status or {}
    view = dict((opt, status.get(api)) for opt, api in S3_FIELDS.items())
    for opt in S3_TEXT:
        view[opt] = view[opt] or None
    view["enabled"] = bool(view["enabled"])
    view["encrypt"] = bool(view["encrypt"])
    view["secret_key"] = SECRET_MASK if status.get("secretKeySet") else None
    return view


def s3_request(view, secret):
    body = dict((api, view[opt]) for opt, api in S3_FIELDS.items())
    body["secretKey"] = secret
    return body


class ConfigBackupModule(CroitModule):
    def __init__(self):
        super(ConfigBackupModule, self).__init__(
            dict(
                cloud_enabled=dict(type="bool"),
                s3=dict(
                    type="dict",
                    options=dict(
                        enabled=dict(type="bool"),
                        endpoint=dict(type="str"),
                        bucket=dict(type="str"),
                        prefix=dict(type="str"),
                        region=dict(type="str"),
                        access_key=dict(type="str", no_log=False),
                        secret_key=dict(type="str", no_log=True),
                        update_secret=dict(type="str", default="on_create", choices=["on_create", "always"]),
                        encrypt=dict(type="bool"),
                    ),
                ),
                run_now=dict(type="list", elements="str", choices=["cloud", "s3"]),
                return_encryption_key=dict(type="bool", default=False, no_log=False),
            ),
        )

    def cloud_status(self):
        status = dict(self.get(CLOUD_PATH) or {})
        if not self.params["return_encryption_key"]:
            status.pop("backupEncryptionKey", None)
        return status

    def run(self):
        p = self.params
        before, after = {}, {}
        cloud = self.cloud_status()
        s3 = self.get(S3_PATH) or {}

        # Cloud ----------------------------------------------------------------
        cloud_change = None
        if p["cloud_enabled"] is not None:
            before.update(cloud_view(cloud))
            after["cloud_enabled"] = p["cloud_enabled"]
            if bool(cloud.get("enabled")) != p["cloud_enabled"]:
                cloud_change = dict(enabled=p["cloud_enabled"])

        # S3 -------------------------------------------------------------------
        s3_body = None
        if p["s3"] is not None:
            wanted = p["s3"]
            current = s3_view(s3)
            merged = dict(current)
            for opt in S3_FIELDS:
                if wanted.get(opt) is not None:
                    merged[opt] = (wanted[opt] or None) if opt in S3_TEXT else wanted[opt]
            secret = None
            if wanted.get("secret_key") is not None:
                if wanted["update_secret"] == "always" or not s3.get("secretKeySet"):
                    secret = wanted["secret_key"]
                    merged["secret_key"] = SECRET_MASK + " (changed)" if s3.get("secretKeySet") else SECRET_MASK
            before["s3"] = current
            after["s3"] = merged
            if merged != current:
                if merged["enabled"] and merged["secret_key"] is None:
                    self.module.fail_json(msg="s3.secret_key is required to enable S3 backups; croit has none stored")
                s3_body = s3_request(merged, secret)

        runs = p["run_now"] or []
        changed = bool(cloud_change or s3_body or runs)
        result = dict(cloud=cloud, s3=s3)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, **result)

        if cloud_change:
            self.write("PATCH", CLOUD_PATH, body=cloud_change)
        if s3_body:
            self.write("PUT", S3_PATH, body=s3_body)
        tasks = []
        for target in runs:
            path = CLOUD_PATH + "/create" if target == "cloud" else S3_PATH + "/create"
            task = self.handle_task(self.write("POST", path))
            if task is not None:
                tasks.append(task)
        if tasks:
            result["tasks"] = tasks
            result["task"] = tasks[-1]
        result["cloud"] = self.cloud_status()
        result["s3"] = self.get(S3_PATH) or {}
        self.exit(changed=True, before=before, after=after, **result)


def main():
    ConfigBackupModule().run()


if __name__ == "__main__":
    main()
