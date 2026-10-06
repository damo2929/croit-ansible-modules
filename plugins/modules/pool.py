#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /pools
# croit-api: POST /pools
# croit-api: PATCH /pools/{name}
# croit-api: DELETE /pools/{name}
# croit-api: GET /pools/{name}/compression
# croit-api: GET /crush/rules

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: pool
short_description: Manage Ceph pools on a croit cluster
version_added: 0.1.0
description:
  - Creates, updates and deletes Ceph pools through the croit API. A pool is identified by its O(name).
  - Only options that are set are managed; anything left out keeps its current value. Only the settings
    that differ are sent, so a converged pool causes no write.
  - Settings that Ceph cannot change after creation (replicated or erasure coded, and the erasure code
    profile) are compared, and a difference fails the task instead of recreating the pool.
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
      - Name of the pool, which identifies it. Renaming pools is not supported.
    type: str
    required: true
  state:
    description:
      - Whether the pool should exist.
      - V(absent) deletes the pool and B(all data in it), and needs O(confirm_delete=true).
    type: str
    choices: [present, absent]
    default: present
  application:
    description:
      - Application using the pool, for example V(rbd), V(cephfs) or V(rgw).
      - croit warns before changing the application of an existing pool, see O(ignore_warnings).
    type: str
  description:
    description:
      - Free text croit keeps about what the pool is for. Ceph itself does not store it.
      - An empty string and an unset description compare as equal.
    type: str
  size:
    description:
      - Number of replicas of a replicated pool.
      - Not valid for erasure coded pools, where croit derives it from O(data_chunks) and O(parity_chunks).
    type: int
  min_size:
    description:
      - Minimum number of replicas needed to serve I/O on a replicated pool.
      - Not valid for erasure coded pools.
    type: int
  pg_num:
    description:
      - Number of placement groups. croit uses 128 when a pool is created without it.
      - Leave unset when the PG autoscaler manages the pool, or every run will fight the autoscaler.
    type: int
  crush_rule:
    description:
      - CRUSH rule to place the pool with, by name or numeric id. An unknown rule fails and lists the known ones.
      - When creating a replicated pool without it, croit uses the cluster's default rule. For an erasure
        coded pool, Ceph creates a rule from O(device_class).
    type: str
  erasure_coding:
    description:
      - Create an erasure coded pool instead of a replicated one.
      - Cannot be changed after the pool exists; a different value fails the task.
    type: bool
  data_chunks:
    description:
      - Erasure code data chunks (k). croit uses 4 when not set.
      - Cannot be changed after the pool exists; a different value fails the task.
    type: int
  parity_chunks:
    description:
      - Erasure code parity chunks (m). croit uses 2 when not set.
      - Cannot be changed after the pool exists; a different value fails the task.
    type: int
  device_class:
    description:
      - Device class, such as V(hdd) or V(ssd), an erasure coded pool is placed on when O(crush_rule) is not set.
      - Only used when the pool is created, and never compared afterwards.
    type: str
  fast_read:
    description:
      - Read all k+m shards of an erasure coded pool in parallel, trading bandwidth for latency.
      - Only valid for erasure coded pools.
    type: bool
  quota_max_bytes:
    description:
      - Byte quota of the pool, as bytes or with a binary unit such as V(500G) or V(10T). V(0) is unlimited.
    type: str
  quota_max_objects:
    description:
      - Object quota of the pool. V(0) is unlimited.
    type: int
  compression:
    description:
      - BlueStore compression of the pool. Only the sub-options that are set are managed; the others keep
        their current value.
    type: dict
    suboptions:
      algorithm:
        description: Compression algorithm the pool compresses with. V(none) turns compression off.
        type: str
        choices: [lz4, snappy, zlib, zstd, none]
      mode:
        description: When the pool compresses data. V(none) never compresses.
        type: str
        choices: [none, passive, aggressive, force]
      min_blob_size:
        description: Chunks smaller than this many bytes are not compressed.
        type: int
      max_blob_size:
        description: Chunks larger than this many bytes are split before they are compressed.
        type: int
      required_ratio:
        description: How much smaller a compressed chunk must be for the compressed version to be kept, for example V(0.875).
        type: float
  volume:
    description:
      - CephFS volume using the pool, for O(application=cephfs). croit uses the default filesystem when not set.
      - Only used when the pool is created, and never compared afterwards.
    type: str
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing pool and all its data.
      - The pool's delete protection is lifted automatically before deleting.
    type: bool
    default: false
notes:
  - Deleting a pool destroys every object in it and cannot be undone.
  - Changing O(size), O(crush_rule) or O(pg_num) of a pool that holds data starts data movement.
seealso:
  - module: croit.ceph.pool_info
    description: Read pools and their details.
  - module: croit.ceph.pool_qos
    description: Manage the RBD QoS limits of a pool.
  - module: croit.ceph.crush_rule
    description: Create the CRUSH rules pools are placed with.
  - name: croit API reference
    description: The C(/pools) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph pools
    description: Upstream documentation of pool settings.
    link: https://docs.ceph.com/en/latest/rados/operations/pools/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Replicated RBD pool on SSDs
  croit.ceph.pool:
    name: rbd-ssd
    application: rbd
    size: 3
    min_size: 2
    crush_rule: replicated_ssd
    description: VM disks

- name: Erasure coded pool for S3 data, 8+3 on HDDs
  croit.ceph.pool:
    name: default.rgw.buckets.data
    application: rgw
    erasure_coding: true
    data_chunks: 8
    parity_chunks: 3
    device_class: hdd
    compression:
      algorithm: zstd
      mode: aggressive

- name: Set a quota and show what changed
  croit.ceph.pool:
    name: rbd-ssd
    quota_max_bytes: 20T
  register: result
  diff: true

- name: Show the pool id
  ansible.builtin.debug:
    msg: "rbd-ssd has pool id {{ result.pool.poolId }}"

- name: Delete a pool and all its data
  croit.ceph.pool:
    name: scratch
    state: absent
    confirm_delete: true
"""

RETURN = r"""
pool:
  description:
    - The pool as croit reports it after the change (C(CephPoolResponse) in the croit API).
    - In check mode, the pool before the change. Empty when the pool does not exist or was deleted.
  returned: always
  type: dict
  contains:
    name:
      description: The pool's name.
      returned: always
      type: str
      sample: rbd-ssd
    poolId:
      description: Ceph's numeric pool id.
      returned: always
      type: int
      sample: 3
    application:
      description: The application using the pool.
      returned: always
      type: str
      sample: rbd
    size:
      description: Number of replicas, or k+m for an erasure coded pool.
      returned: always
      type: int
      sample: 3
    minSize:
      description: Minimum number of replicas to serve I/O.
      returned: always
      type: int
      sample: 2
    pgNum:
      description: Number of placement groups.
      returned: always
      type: int
      sample: 128
    crushRule:
      description: Numeric id of the CRUSH rule.
      returned: always
      type: int
      sample: 1
    erasureCoding:
      description: Whether the pool is erasure coded.
      returned: always
      type: bool
      sample: false
    dataChunks:
      description: Erasure code data chunks (k), or V(null) for a replicated pool.
      returned: always
      type: int
      sample: null
    parityChunks:
      description: Erasure code parity chunks (m), or V(null) for a replicated pool.
      returned: always
      type: int
      sample: null
    quotaMaxBytes:
      description: Byte quota, V(0) for unlimited.
      returned: always
      type: int
      sample: 21990232555520
    quotaMaxObjects:
      description: Object quota, V(0) for unlimited.
      returned: always
      type: int
      sample: 0
    deleteProtected:
      description: Whether the pool is protected from deletion.
      returned: always
      type: bool
      sample: true
compression:
  description: The pool's compression settings after the change (C(PoolCompressionSettings) in the croit API).
  returned: when O(compression) is set and the pool exists
  type: dict
  contains:
    algorithm:
      description: Compression algorithm, as croit spells it.
      returned: always
      type: str
      sample: Zstd
    mode:
      description: Compression mode, as croit spells it.
      returned: always
      type: str
      sample: Aggressive
    minBlobSize:
      description: Minimum blob size in bytes, or V(null) for Ceph's default.
      returned: always
      type: int
      sample: null
    maxBlobSize:
      description: Maximum blob size in bytes, or V(null) for Ceph's default.
      returned: always
      type: int
      sample: null
    requiredRatio:
      description: Required compression ratio, or V(null) for Ceph's default.
      returned: always
      type: float
      sample: null
task:
  description: The croit background task the change ran as. Creating a pool always runs as a task.
  returned: when the change ran as a croit task
  type: dict
  contains:
    id:
      description: The task's id, usable with M(croit.ceph.task).
      returned: always
      type: int
      sample: 412
    state:
      description: The task's state; V(FINISHED) after a successful wait.
      returned: always
      type: str
      sample: FINISHED
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: Creating pool rbd-ssd ... done
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import (
    CroitModule,
    changed_fields,
    parse_size,
)

DELETE_CONFIRMATION = "I'm really sure that I want to delete this"

# Ansible option -> croit API field, for the plain fields compared 1:1.
FIELDS = dict(
    application="application",
    description="description",
    size="size",
    min_size="minSize",
    pg_num="pgNum",
    crush_rule="crushRule",
    fast_read="fastRead",
    quota_max_bytes="quotaMaxBytes",
    quota_max_objects="quotaMaxObjects",
)
IMMUTABLE = dict(erasure_coding="erasureCoding", data_chunks="dataChunks", parity_chunks="parityChunks")
CREATE_ONLY = dict(device_class="deviceClass", volume="volume")

COMPRESSION_FIELDS = dict(
    algorithm="algorithm",
    mode="mode",
    min_blob_size="minBlobSize",
    max_blob_size="maxBlobSize",
    required_ratio="requiredRatio",
)
# croit's enum spelling for the lower-case choices.
COMPRESSION_ENUMS = dict(
    algorithm=dict(lz4="LZ4", snappy="Snappy", zlib="Zlib", zstd="Zstd", none="None"),
    mode=dict(none="None", passive="Passive", aggressive="Aggressive", force="Force"),
)


def managed_view(pool):
    """The pool's managed fields, keyed by Ansible option name, for diffs."""
    if not pool:
        return {}
    view = dict((opt, pool.get(api)) for opt, api in FIELDS.items())
    view.update((opt, pool.get(api)) for opt, api in IMMUTABLE.items())
    return view


class PoolModule(CroitModule):
    def __init__(self):
        super(PoolModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                application=dict(type="str"),
                description=dict(type="str"),
                size=dict(type="int"),
                min_size=dict(type="int"),
                pg_num=dict(type="int"),
                crush_rule=dict(type="str"),
                erasure_coding=dict(type="bool"),
                data_chunks=dict(type="int"),
                parity_chunks=dict(type="int"),
                device_class=dict(type="str"),
                fast_read=dict(type="bool"),
                quota_max_bytes=dict(type="str"),
                quota_max_objects=dict(type="int"),
                compression=dict(
                    type="dict",
                    options=dict(
                        algorithm=dict(type="str", choices=list(COMPRESSION_ENUMS["algorithm"])),
                        mode=dict(type="str", choices=list(COMPRESSION_ENUMS["mode"])),
                        min_blob_size=dict(type="int"),
                        max_blob_size=dict(type="int"),
                        required_ratio=dict(type="float"),
                    ),
                ),
                volume=dict(type="str"),
                confirm_delete=dict(type="bool", default=False),
            ),
        )

    # Lookups --------------------------------------------------------------

    def find_pool(self, name):
        for pool in self.get_list("/pools"):
            if pool.get("name") == name:
                return pool
        return None

    def resolve_crush_rule(self, value):
        if value is None:
            return None
        rules = self.get_list("/crush/rules")
        for rule in rules:
            if rule.get("name") == value:
                return rule["id"]
        if value.isdigit():
            rule_id = int(value)
            if any(rule.get("id") == rule_id for rule in rules):
                return rule_id
        self.module.fail_json(
            msg="CRUSH rule %r does not exist. Known rules: %s"
            % (value, ", ".join("%s (%s)" % (r.get("name"), r.get("id")) for r in rules))
        )

    # Desired state --------------------------------------------------------

    def desired(self):
        p = self.params
        try:
            quota_bytes = parse_size(p["quota_max_bytes"])
        except ValueError as e:
            self.module.fail_json(msg="quota_max_bytes: %s" % e)
        values = dict(
            application=p["application"],
            description=p["description"],
            size=p["size"],
            min_size=p["min_size"],
            pg_num=p["pg_num"],
            crush_rule=self.resolve_crush_rule(p["crush_rule"]),
            fast_read=p["fast_read"],
            quota_max_bytes=quota_bytes,
            quota_max_objects=p["quota_max_objects"],
        )
        return dict((FIELDS[k], v) for k, v in values.items())

    def desired_compression(self):
        comp = self.params["compression"]
        if not comp:
            return None
        result = {}
        for opt, api in COMPRESSION_FIELDS.items():
            value = comp.get(opt)
            if value is None:
                continue
            result[api] = COMPRESSION_ENUMS[opt][value] if opt in COMPRESSION_ENUMS else value
        return result or None

    def validate_ec(self, erasure_coded):
        p = self.params
        if erasure_coded:
            bad = [o for o in ("size", "min_size") if p[o] is not None]
            if bad:
                self.module.fail_json(
                    msg="%s cannot be set on an erasure coded pool; croit derives them from data_chunks "
                    "and parity_chunks" % " and ".join(bad)
                )
        else:
            bad = [o for o in ("data_chunks", "parity_chunks", "fast_read") if p[o] is not None]
            if bad:
                self.module.fail_json(msg="%s only apply to erasure coded pools" % ", ".join(bad))

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        name = p["name"]
        current = self.find_pool(name)

        if p["state"] == "absent":
            return self.absent(current)

        if current is None:
            return self.create(name)
        return self.update(name, current)

    def absent(self, current):
        if current is None:
            self.exit(changed=False, pool={})
        if not self.params["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to delete pool %r and all its data without confirm_delete=true" % current["name"]
            )
        if not self.check_mode:
            pool_path = path_join("pools", current["name"])
            if current.get("deleteProtected"):
                self.write("PATCH", pool_path, body=dict(unprotect=True))
            self.write(
                "DELETE",
                pool_path,
                body=dict(name=current["name"], poolId=current["poolId"], thisWillDeleteData=DELETE_CONFIRMATION),
            )
        self.exit(changed=True, before=managed_view(current), after={}, pool={})

    def create(self, name):
        p = self.params
        self.validate_ec(bool(p["erasure_coding"]))
        body = dict((k, v) for k, v in self.desired().items() if v is not None)
        body["name"] = name
        for opt, api in list(IMMUTABLE.items()) + list(CREATE_ONLY.items()):
            if p[opt] is not None:
                body[api] = p[opt]
        compression = self.desired_compression()
        if compression:
            body["compression"] = compression

        after = dict((opt, body.get(api)) for opt, api in list(FIELDS.items()) + list(IMMUTABLE.items()))
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, pool={})

        task = self.handle_task(self.write("POST", "/pools", body=body))
        result = dict(changed=True, before={}, after=after, pool=self.find_pool(name) or {})
        if task is not None:
            result["task"] = task
        if compression and result["pool"]:
            result["compression"] = self.get(path_join("pools", name, "compression"))
        self.exit(**result)

    def update(self, name, current):
        p = self.params
        erasure_coded = bool(current.get("erasureCoding"))

        for opt, api in IMMUTABLE.items():
            if p[opt] is not None and p[opt] != current.get(api):
                self.module.fail_json(
                    msg="%s of pool %r is %r and cannot be changed to %r after creation"
                    % (opt, name, current.get(api), p[opt])
                )
        self.validate_ec(erasure_coded)

        desired = self.desired()
        # croit stores no description as an empty string.
        normalised = dict(current)
        if normalised.get("description") is None:
            normalised["description"] = ""
        changes = dict((k, desired[k]) for k in changed_fields(normalised, desired))

        before = managed_view(current)
        after = dict(before)
        for opt, api in FIELDS.items():
            if api in changes:
                after[opt] = changes[api]

        result = dict(pool=current)
        compression = self.desired_compression()
        if compression:
            current_comp = self.get(path_join("pools", name, "compression")) or {}
            comp_changes = changed_fields(current_comp, compression)
            before["compression"] = dict((k, current_comp.get(k)) for k in compression)
            after["compression"] = dict(before["compression"])
            result["compression"] = current_comp
            if comp_changes:
                merged = dict((k, v) for k, v in current_comp.items() if k in COMPRESSION_FIELDS.values())
                merged.update(compression)
                changes["compression"] = merged
                after["compression"].update(compression)

        if not changes:
            self.exit(changed=False, before=before, after=after, **result)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, **result)

        task = self.handle_task(self.write("PATCH", path_join("pools", name), body=changes))
        if task is not None:
            result["task"] = task
        result["pool"] = self.find_pool(name) or {}
        if compression:
            result["compression"] = self.get(path_join("pools", name, "compression"))
        self.exit(changed=True, before=before, after=after, **result)


def main():
    PoolModule().run()


if __name__ == "__main__":
    main()
