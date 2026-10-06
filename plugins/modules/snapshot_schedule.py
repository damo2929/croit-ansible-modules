#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /snapshot-schedule/cephfs
# croit-api: POST /snapshot-schedule/cephfs
# croit-api: PATCH /snapshot-schedule/cephfs/{scheduleId}
# croit-api: DELETE /snapshot-schedule/cephfs/{scheduleId}
# croit-api: GET /snapshot-schedule/rbd
# croit-api: POST /snapshot-schedule/rbd
# croit-api: PATCH /snapshot-schedule/rbd/{scheduleId}
# croit-api: DELETE /snapshot-schedule/rbd/{scheduleId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: snapshot_schedule
short_description: Manage scheduled CephFS and RBD snapshots on a croit cluster
version_added: 0.1.0
description:
  - Creates, updates and deletes croit snapshot schedules for CephFS directories or RBD pools and images.
  - A schedule is identified by O(type) and O(snapshot_prefix), plus O(volume) for CephFS when it is
    set, so playbooks never need croit's numeric schedule ids. Prefixes should therefore be unique per
    type (and volume); the module fails if more than one schedule matches.
  - Only options that are set are managed. O(paths) and O(rbd_paths) are compared as sets, so their
    order does not matter.
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
  type:
    description:
      - Whether the schedule snapshots CephFS directories or RBD images.
    type: str
    choices: [cephfs, rbd]
    required: true
  snapshot_prefix:
    description:
      - Name prefix of the snapshots the schedule takes. Identifies the schedule.
    type: str
    required: true
  state:
    description:
      - Whether the schedule should exist.
      - V(absent) removes the schedule only; snapshots it already took are kept.
    type: str
    choices: [present, absent]
    default: present
  volume:
    description:
      - CephFS volume the schedule works on. Only for O(type=cephfs).
      - When set it is part of the schedule's identity. When creating without it, croit uses the
        cluster's configured CephFS.
    type: str
  cron:
    description:
      - When snapshots are taken, as a cron expression, for example V(0 * * * *).
      - Required to create a schedule. Interpreted in the cluster's scheduling timezone.
    type: str
  max_snapshots:
    description:
      - How many snapshots to keep (1-100). Older ones are removed.
      - Required to create a schedule.
    type: int
  enabled:
    description:
      - Whether the schedule fires. New schedules are enabled unless this is V(false).
    type: bool
  paths:
    description:
      - CephFS directories to snapshot, for example V(/projects). Only for O(type=cephfs).
      - Required to create a CephFS schedule.
    type: list
    elements: str
  rbd_paths:
    description:
      - RBD pools, namespaces or images to snapshot. Only for O(type=rbd).
      - A pool alone snapshots every image in it; with O(rbd_paths[].namespace) every image in that
        namespace; with O(rbd_paths[].image) only that image.
      - croit warns when a pool, namespace or image does not exist yet; see O(ignore_warnings).
      - Required to create an RBD schedule.
    type: list
    elements: dict
    suboptions:
      pool:
        description: RBD pool to snapshot; alone, it covers every image in the pool.
        type: str
        required: true
      namespace:
        description: RBD namespace within O(rbd_paths[].pool); covers every image in the namespace.
        type: str
      image:
        description: A single RBD image to snapshot, within O(rbd_paths[].pool) and O(rbd_paths[].namespace).
        type: str
notes:
  - Deleting a schedule keeps the snapshots it already took. Remove CephFS snapshots on the filesystem, and
    RBD snapshots with M(croit.ceph.rbd_snapshot).
seealso:
  - module: croit.ceph.rbd_snapshot
    description: Take or delete a single RBD snapshot.
  - module: croit.ceph.cluster_tuning
    description: Set the timezone schedules are read in.
  - name: croit API reference
    description: The C(/snapshot-schedule) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: CephFS snapshots
    description: Upstream documentation of CephFS snapshots.
    link: https://docs.ceph.com/en/latest/cephfs/snapshots/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Hourly snapshots of two CephFS directories, keep a day
  croit.ceph.snapshot_schedule:
    type: cephfs
    snapshot_prefix: hourly
    volume: cephfs
    cron: "0 * * * *"
    max_snapshots: 24
    paths:
      - /projects
      - /home

- name: Nightly snapshots of every image in a pool, and one more image
  croit.ceph.snapshot_schedule:
    type: rbd
    snapshot_prefix: nightly
    cron: "30 2 * * *"
    max_snapshots: 7
    rbd_paths:
      - pool: vms
      - pool: db
        image: postgres-data

- name: Pause a schedule
  croit.ceph.snapshot_schedule:
    type: rbd
    snapshot_prefix: nightly
    enabled: false
  register: nightly

- name: Show the schedule's paths
  ansible.builtin.debug:
    msg: "{{ nightly.schedule.pathsFormatted }}"

- name: Remove a schedule
  croit.ceph.snapshot_schedule:
    type: cephfs
    snapshot_prefix: hourly
    state: absent
"""

RETURN = r"""
schedule:
  description:
    - The schedule as croit reports it after the change (C(CephFSSnapshotSchedule) or C(RbdSnapshotSchedule)
      in the croit API).
    - In check mode, the schedule before the change. Empty when the schedule does not exist or was deleted.
  returned: always
  type: dict
  contains:
    id:
      description: croit's numeric schedule id.
      returned: always
      type: int
      sample: 4
    cron:
      description: When snapshots are taken.
      returned: always
      type: str
      sample: "0 * * * *"
    enabled:
      description: Whether the schedule fires.
      returned: always
      type: bool
      sample: true
    snapshotPrefix:
      description: Name prefix of the snapshots.
      returned: always
      type: str
      sample: hourly
    maxSnapshots:
      description: How many snapshots are kept.
      returned: always
      type: int
      sample: 24
    paths:
      description:
        - For CephFS, the directories as strings. For RBD, entries with C(pool), C(namespace) and C(rbd).
      returned: always
      type: list
      sample: [/home, /projects]
    pathsFormatted:
      description: The paths as one line of text.
      returned: always
      type: str
      sample: /home, /projects
    volume:
      description: The CephFS volume.
      returned: for O(type=cephfs)
      type: str
      sample: cephfs
    failedSnapshots:
      description: Snapshots croit could not create.
      returned: always
      type: list
      sample: []
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def normalise_cephfs_path(path):
    return "/" + str(path).strip().strip("/")


def rbd_path_key(entry):
    return (entry.get("pool"), entry.get("namespace") or None, entry.get("rbd") or None)


def to_api_rbd_path(entry):
    body = dict(pool=entry["pool"])
    if entry.get("namespace"):
        body["namespace"] = entry["namespace"]
    if entry.get("image"):
        body["rbd"] = entry["image"]
    return body


def view_sort_key(entry):
    return (entry.get("pool") or "", entry.get("namespace") or "", entry.get("image") or "")


def from_api_rbd_path(entry):
    return dict(pool=entry.get("pool"), namespace=entry.get("namespace") or None, image=entry.get("rbd") or None)


class SnapshotScheduleModule(CroitModule):
    def __init__(self):
        super(SnapshotScheduleModule, self).__init__(
            dict(
                type=dict(type="str", required=True, choices=["cephfs", "rbd"]),
                snapshot_prefix=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                volume=dict(type="str"),
                cron=dict(type="str"),
                max_snapshots=dict(type="int"),
                enabled=dict(type="bool"),
                paths=dict(type="list", elements="str"),
                rbd_paths=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        pool=dict(type="str", required=True),
                        namespace=dict(type="str"),
                        image=dict(type="str"),
                    ),
                ),
            ),
            wait=False,
        )
        self.kind = self.params["type"]
        self.base = "/snapshot-schedule/%s" % self.kind

    # Lookups --------------------------------------------------------------

    def find(self):
        p = self.params
        matches = []
        for schedule in self.get_list(self.base):
            if schedule.get("snapshotPrefix") != p["snapshot_prefix"]:
                continue
            if self.kind == "cephfs" and p["volume"] is not None and schedule.get("volume") != p["volume"]:
                continue
            matches.append(schedule)
        if len(matches) > 1:
            self.module.fail_json(
                msg="%d %s snapshot schedules use the prefix %r (ids %s); make the prefixes unique%s"
                % (
                    len(matches),
                    self.kind,
                    p["snapshot_prefix"],
                    ", ".join(str(s.get("id")) for s in matches),
                    " or set volume" if self.kind == "cephfs" else "",
                )
            )
        return matches[0] if matches else None

    # Normalised views -------------------------------------------------------

    def paths_view(self, schedule):
        if self.kind == "cephfs":
            return sorted(normalise_cephfs_path(x) for x in schedule.get("paths") or [])
        return sorted((from_api_rbd_path(x) for x in schedule.get("paths") or []), key=view_sort_key)

    def view(self, schedule):
        if not schedule:
            return {}
        result = dict(
            snapshot_prefix=schedule.get("snapshotPrefix"),
            cron=schedule.get("cron"),
            max_snapshots=schedule.get("maxSnapshots"),
            enabled=schedule.get("enabled"),
        )
        result["paths" if self.kind == "cephfs" else "rbd_paths"] = self.paths_view(schedule)
        if self.kind == "cephfs":
            result["volume"] = schedule.get("volume")
        return result

    def desired_paths(self):
        """(view value, API value) of the requested paths, or (None, None)."""
        p = self.params
        if self.kind == "cephfs":
            if p["paths"] is None:
                return None, None
            norm = sorted(set(normalise_cephfs_path(x) for x in p["paths"]))
            return norm, norm
        if p["rbd_paths"] is None:
            return None, None
        unique = {}
        for entry in p["rbd_paths"]:
            api = to_api_rbd_path(entry)
            unique[rbd_path_key(api)] = api
        api_paths = [unique[k] for k in sorted(unique, key=lambda k: tuple(x or "" for x in k))]
        view = sorted((from_api_rbd_path(x) for x in api_paths), key=view_sort_key)
        return view, api_paths

    # Main -----------------------------------------------------------------

    def validate(self):
        p = self.params
        if self.kind == "cephfs" and p["rbd_paths"] is not None:
            self.module.fail_json(msg="rbd_paths only applies to type=rbd; use paths for CephFS directories")
        if self.kind == "rbd":
            bad = [o for o in ("paths", "volume") if p[o] is not None]
            if bad:
                self.module.fail_json(msg="%s only apply to type=cephfs; use rbd_paths for RBD" % ", ".join(bad))
        if p["max_snapshots"] is not None and not 1 <= p["max_snapshots"] <= 100:
            self.module.fail_json(msg="max_snapshots must be between 1 and 100")
        for opt in ("paths", "rbd_paths"):
            if p[opt] is not None and not p[opt]:
                self.module.fail_json(msg="%s must not be empty; use state=absent to remove the schedule" % opt)

    def run(self):
        p = self.params
        self.validate()
        current = self.find()

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, schedule={})
            if not self.check_mode:
                self.write("DELETE", path_join("snapshot-schedule", self.kind, current["id"]))
            self.exit(changed=True, before=self.view(current), after={}, schedule={})

        paths_view, paths_api = self.desired_paths()
        if current is None:
            return self.create(paths_view, paths_api)
        return self.update(current, paths_view, paths_api)

    def create(self, paths_view, paths_api):
        p = self.params
        missing = [o for o in ("cron", "max_snapshots") if p[o] is None]
        if paths_api is None:
            missing.append("paths" if self.kind == "cephfs" else "rbd_paths")
        if missing:
            self.module.fail_json(
                msg="%s snapshot schedule %r does not exist; creating it needs %s"
                % (self.kind, p["snapshot_prefix"], ", ".join(missing))
            )
        body = dict(cron=p["cron"], snapshotPrefix=p["snapshot_prefix"], maxSnapshots=p["max_snapshots"], paths=paths_api)
        if self.kind == "cephfs" and p["volume"] is not None:
            body["volume"] = p["volume"]

        after = dict(
            snapshot_prefix=p["snapshot_prefix"],
            cron=p["cron"],
            max_snapshots=p["max_snapshots"],
            enabled=p["enabled"] is not False,
        )
        after["paths" if self.kind == "cephfs" else "rbd_paths"] = paths_view
        if self.kind == "cephfs":
            after["volume"] = p["volume"]
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, schedule={})

        self.write("POST", self.base, body=body)
        created = self.find()
        if created is None:
            self.module.fail_json(msg="croit accepted the schedule but it could not be found afterwards", after=after)
        if p["enabled"] is False and created.get("enabled"):
            # The create request has no enabled flag; switch it off right away.
            self.write("PATCH", path_join("snapshot-schedule", self.kind, created["id"]), body=dict(enabled=False))
            created = self.find() or created
        self.exit(changed=True, before={}, after=after, schedule=created)

    def update(self, current, paths_view, paths_api):
        p = self.params
        before = self.view(current)
        after = dict(before)
        changes = {}
        for opt, api in (("cron", "cron"), ("max_snapshots", "maxSnapshots"), ("enabled", "enabled")):
            if p[opt] is not None and p[opt] != before[opt]:
                changes[api] = p[opt]
                after[opt] = p[opt]
        path_opt = "paths" if self.kind == "cephfs" else "rbd_paths"
        if paths_view is not None and paths_view != before[path_opt]:
            changes["paths"] = paths_api
            after[path_opt] = paths_view

        if not changes:
            self.exit(changed=False, before=before, after=after, schedule=current)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, schedule=current)
        self.write("PATCH", path_join("snapshot-schedule", self.kind, current["id"]), body=changes)
        self.exit(changed=True, before=before, after=after, schedule=self.find() or current)


def main():
    SnapshotScheduleModule().run()


if __name__ == "__main__":
    main()
