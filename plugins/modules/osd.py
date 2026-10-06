#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /servers
# croit-api: GET /servers/{serverId}/disks
# croit-api: GET /crush
# croit-api: POST /disks/create-osds
# croit-api: POST /disks/replace-osds
# croit-api: POST /crush/osd/{osdId}/in
# croit-api: POST /crush/osd/{osdId}/out
# croit-api: POST /services/{type}/{daemonOrServiceId}/start
# croit-api: POST /services/{type}/{daemonOrServiceId}/stop

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: osd
short_description: Manage Ceph OSDs on a croit cluster
version_added: 0.1.0
description:
  - Creates an OSD on a disk of a croit-managed server, replaces an existing OSD onto a new disk, and
    manages whether an OSD is C(in) the CRUSH map and whether its daemon is running.
  - B(Creating or replacing an OSD erases the target disk.) Both need O(confirm_wipe=true).
  - A disk that already carries an OSD is left alone. croit refuses to use a disk that is not
    unassigned (for example an old OSD or a disk with data on it), so such a disk must be wiped in croit first.
    This module does not wipe disks or destroy OSDs on its own.
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
  server:
    description:
      - Server the disk is in, by hostname or numeric id.
      - Required with O(disk).
    type: str
  disk:
    description:
      - The disk to put the OSD on, as a device path (V(/dev/sdb), V(/dev/disk/by-id/...)), serial number,
        WWN, or croit's numeric disk id.
      - Device paths can change between boots; serial numbers and WWNs are stable.
    type: str
  osd_id:
    description:
      - Numeric id of an existing OSD.
      - Alone, selects the OSD to manage with O(in) and O(running).
      - With O(disk), checks that the disk carries this OSD.
      - Mutually exclusive with O(replace_osd).
    type: int
  replace_osd:
    description:
      - Id of an existing OSD to move onto O(disk), keeping its id. croit destroys the old OSD and creates it
        again on the new disk.
      - Nothing happens when O(disk) already carries this OSD.
      - croit refuses a replacement that would lose data outright, and asks for confirmation when it cannot
        tell. That confirmation needs O(ignore_warnings=true).
    type: int
  encrypted:
    description:
      - Create the OSD with dm-crypt encryption. Only used when an OSD is created or replaced.
      - Defaults to V(false) when creating, and to the old OSD's setting when replacing.
      - An existing OSD with a different setting fails the task, because encryption cannot be changed afterwards.
    type: bool
  device_class:
    description:
      - CRUSH device class of a new OSD, for example V(hdd), V(ssd) or V(nvme). ceph detects it when not set.
      - An existing OSD with a different class fails the task.
    type: str
  db_disk:
    description:
      - Disk on the same server to put the new OSD's DB (and WAL, unless O(wal_disk) is set) on. Identified like O(disk).
      - Only used when an OSD is created or replaced. An existing OSD with a different DB disk fails the task.
    type: str
  wal_disk:
    description:
      - Disk on the same server to put the new OSD's WAL on. Identified like O(disk).
      - Only used when an OSD is created or replaced. An existing OSD with a different WAL disk fails the task.
    type: str
  in:
    description:
      - Whether CRUSH places data on the OSD. V(false) marks it out, which moves its data to the other OSDs.
      - Not set means leave alone.
    type: bool
  running:
    description:
      - Whether the OSD daemon should be running. Not set means leave alone.
      - Stopping an OSD makes its placement groups degraded until it is started again; set the C(noout) flag
        first for planned maintenance.
      - croit applies start and stop asynchronously. With O(wait=true) the module waits until ceph reports the
        OSD up or down.
    type: bool
  confirm_wipe:
    description:
      - Must be V(true) to create or replace an OSD, because the target disk is erased.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Create an OSD on a disk identified by serial number
  croit.ceph.osd:
    server: storage-01
    disk: ZL2ABC12
    device_class: hdd
    db_disk: /dev/nvme0n1
    confirm_wipe: true

- name: Take an OSD out before maintenance
  croit.ceph.osd:
    osd_id: 12
    in: false

- name: Stop and start an OSD
  croit.ceph.osd:
    osd_id: 12
    running: false

- name: Move osd.12 to a new disk, keeping its id
  croit.ceph.osd:
    server: storage-01
    disk: /dev/sdk
    replace_osd: 12
    confirm_wipe: true
"""

RETURN = r"""
osd:
  description:
    - The OSD after the change, from the CRUSH map and croit's disk record. Empty when there is none yet
      (including in check mode before a create).
  returned: always
  type: dict
  contains:
    id:
      description: OSD id.
      type: int
    server:
      description: Id of the server it runs on.
      type: int
    disk:
      description: Id of croit's disk record it runs on.
      type: int
    in:
      description: Whether CRUSH places data on it (reweight above 0).
      type: bool
    running:
      description: Whether ceph reports it up.
      type: bool
    status:
      description: What ceph says about it, V(UP), V(DOWN), V(DESTROYED) or V(UNKNOWN).
      type: str
    reweight:
      description: The OSD's reweight.
      type: float
    device_class:
      description: CRUSH device class.
      type: str
disk:
  description: The disk the OSD is on (C(DiskResponse) in the croit API), when a disk was named.
  returned: when O(disk) is set
  type: dict
task:
  description: The last croit background task the change ran as.
  returned: when a task ran
  type: dict
tasks:
  description: Every croit background task the change ran as (creating OSDs runs one task per server).
  returned: when tasks ran
  type: list
  elements: dict
"""

import time

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import require_disk, require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

POLL_INTERVAL = 2.0


def osd_nodes(tree):
    nodes = list((tree or {}).get("nodes") or []) + list((tree or {}).get("stray") or [])
    return dict((n["id"], n) for n in nodes if n.get("type") == "OSD" and n.get("id") is not None and n["id"] >= 0)


def osd_view(node):
    if not node:
        return {}
    reweight = node.get("reweight")
    return {
        "id": node["id"],
        "server": node.get("serverId"),
        "disk": node.get("diskId"),
        "in": reweight is not None and reweight > 0,
        "running": node.get("status") == "UP",
        "status": node.get("status"),
        "reweight": reweight,
        "device_class": node.get("deviceClass"),
    }


class OsdModule(CroitModule):
    def __init__(self):
        super(OsdModule, self).__init__(
            dict(
                server=dict(type="str"),
                disk=dict(type="str"),
                osd_id=dict(type="int"),
                replace_osd=dict(type="int"),
                encrypted=dict(type="bool"),
                device_class=dict(type="str"),
                db_disk=dict(type="str"),
                wal_disk=dict(type="str"),
                running=dict(type="bool"),
                confirm_wipe=dict(type="bool", default=False),
                **{"in": dict(type="bool")}
            ),
            required_one_of=[("disk", "osd_id")],
            required_together=[("server", "disk")],
            required_by=dict(replace_osd=["disk"], db_disk=["disk"], wal_disk=["disk"]),
            mutually_exclusive=[("osd_id", "replace_osd")],
        )
        self.tasks = []

    # Reads ----------------------------------------------------------------

    def crush_osds(self):
        return osd_nodes(self.get("/crush"))

    def server_disks(self, server_id):
        return self.get_list(path_join("servers", server_id, "disks"))

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        osds = self.crush_osds()
        disk = None
        server = None
        disks = []
        if p["disk"] is not None:
            server = require_server(self, p["server"])
            disks = self.server_disks(server["id"])
            disk = require_disk(self, disks, p["disk"])

        target_id = p["osd_id"]
        create = replace = False
        if disk is not None:
            disk_osd = disk.get("osdId")
            if p["replace_osd"] is not None:
                if disk_osd == p["replace_osd"]:
                    target_id = disk_osd
                else:
                    self.check_unassigned(disk, "replace osd.%s onto it" % p["replace_osd"])
                    if p["replace_osd"] not in osds:
                        self.module.fail_json(msg="osd.%s does not exist and cannot be replaced" % p["replace_osd"])
                    replace = True
                    target_id = p["replace_osd"]
            elif disk_osd is not None:
                if target_id is not None and target_id != disk_osd:
                    self.module.fail_json(msg="Disk %r carries osd.%s, not osd.%s" % (p["disk"], disk_osd, target_id))
                target_id = disk_osd
            else:
                self.check_unassigned(disk, "create an OSD on it")
                if target_id is not None:
                    self.module.fail_json(msg="Disk %r carries no OSD, so it cannot be osd.%s" % (p["disk"], target_id))
                create = True
        elif target_id not in osds:
            self.module.fail_json(msg="osd.%s does not exist" % target_id)

        db_id = self.disk_id(disks, p["db_disk"], "db_disk")
        wal_id = self.disk_id(disks, p["wal_disk"], "wal_disk")

        if (create or replace) and not p["confirm_wipe"]:
            self.module.fail_json(
                msg="Refusing to %s disk %r without confirm_wipe=true; the disk will be erased"
                % ("create an OSD on" if create else "replace osd.%s onto" % p["replace_osd"], p["disk"])
            )

        before_node = osds.get(target_id) if not create else None
        before = osd_view(before_node)
        if not create and not replace and disk is not None:
            self.check_create_only(disk, before_node, db_id, wal_id)

        after = dict(before)
        changed = create or replace
        if create:
            # A new OSD comes up in and running.
            after = {"id": None, "server": server["id"], "disk": disk["id"], "device_class": p["device_class"], "in": True, "running": True}
        if replace:
            after["disk"] = disk["id"]

        # Declarative state on top of the (possibly new) OSD.
        wants = {}
        if p["in"] is not None and after.get("in") != p["in"]:
            wants["in"] = p["in"]
        if p["running"] is not None and after.get("running") != p["running"]:
            wants["running"] = p["running"]
        after.update(wants)
        changed = changed or bool(wants)

        result = dict(osd=osd_view(before_node) if before_node else {})
        if disk is not None:
            result["disk"] = disk

        if not changed:
            self.exit(changed=False, before=before, after=after, **result)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, **result)

        if create:
            target_id = self.create(server, disk, db_id, wal_id)
        if replace:
            self.replace(disk, db_id, wal_id)

        if target_id is not None:
            if "in" in wants:
                self.write("POST", path_join("crush", "osd", target_id, "in" if wants["in"] else "out"))
            if "running" in wants:
                data = self.write("POST", path_join("services", "osds", target_id, "start" if wants["running"] else "stop"))
                self.track(self.handle_task(data))
                if self.params["wait"]:
                    self.wait_running(target_id, wants["running"])

        final = self.crush_osds().get(target_id) if target_id is not None else None
        result["osd"] = osd_view(final)
        if disk is not None:
            result["disk"] = self.find_disk_by_id(server["id"], disk["id"]) or disk
        if self.tasks:
            result["tasks"] = self.tasks
            result["task"] = self.tasks[-1]
        self.exit(changed=True, before=before, after=after, **result)

    # Helpers --------------------------------------------------------------

    def track(self, task):
        if task is not None:
            self.tasks.append(task)

    def check_unassigned(self, disk, action):
        if disk.get("role") != "unassigned" or disk.get("missing"):
            self.module.fail_json(
                msg="Cannot %s: disk %s is %s%s. croit only uses unassigned disks; wipe it in croit first if its data "
                "is no longer needed."
                % (
                    action,
                    disk.get("pathFormatted") or disk.get("id"),
                    disk.get("roleLabel") or disk.get("role"),
                    " and missing" if disk.get("missing") else "",
                )
            )

    def disk_id(self, disks, value, what):
        if value is None:
            return None
        return require_disk(self, disks, value, what)["id"]

    def check_create_only(self, disk, node, db_id, wal_id):
        p = self.params
        problems = []
        if p["encrypted"] is not None and bool(disk.get("encrypted")) != p["encrypted"]:
            problems.append("encrypted is %s" % bool(disk.get("encrypted")))
        if p["device_class"] is not None and node is not None and node.get("deviceClass") != p["device_class"]:
            problems.append("device_class is %r" % node.get("deviceClass"))
        if db_id is not None and disk.get("dbDisk") != db_id:
            problems.append("its DB is on disk %s" % disk.get("dbDisk"))
        if wal_id is not None and disk.get("walDisk") != wal_id:
            problems.append("its WAL is on disk %s" % disk.get("walDisk"))
        if problems:
            self.module.fail_json(
                msg="osd.%s already exists and cannot be changed in place: %s. Replace it onto a new disk instead."
                % (disk.get("osdId"), "; ".join(problems))
            )

    def create(self, server, disk, db_id, wal_id):
        p = self.params
        entry = dict(server=server["id"], disk=disk["id"], encrypted=bool(p["encrypted"]))
        if p["device_class"] is not None:
            entry["crushDeviceClass"] = p["device_class"]
        if db_id is not None:
            entry["dbDisk"] = db_id
        if wal_id is not None:
            entry["walDisk"] = wal_id
        tasks = self.write("POST", "/disks/create-osds", body=dict(osds=[entry])) or []
        for task in tasks if isinstance(tasks, list) else [tasks]:
            self.track(self.handle_task(task))
        if not p["wait"]:
            return None
        refreshed = self.find_disk_by_id(server["id"], disk["id"]) or {}
        return refreshed.get("osdId")

    def replace(self, disk, db_id, wal_id):
        p = self.params
        entry = dict(osd=p["replace_osd"], disk=disk["id"])
        if p["encrypted"] is not None:
            entry["encrypted"] = p["encrypted"]
        if db_id is not None or wal_id is not None:
            entry["keepDbWal"] = False
            entry["dbDisk"] = db_id
            entry["walDisk"] = wal_id
        self.track(self.handle_task(self.write("POST", "/disks/replace-osds", body=dict(osds=[entry]))))

    def find_disk_by_id(self, server_id, disk_id):
        for d in self.server_disks(server_id):
            if d.get("id") == disk_id:
                return d
        return None

    def wait_running(self, osd_id, running):
        deadline = time.time() + self.params["wait_timeout"]
        while True:
            node = self.crush_osds().get(osd_id)
            if node is not None and (node.get("status") == "UP") == running:
                return
            if time.time() >= deadline:
                self.module.fail_json(
                    msg="Timed out waiting for osd.%s to be %s" % (osd_id, "up" if running else "down"), osd=osd_view(node)
                )
            time.sleep(POLL_INTERVAL)


def main():
    OsdModule().run()


if __name__ == "__main__":
    main()
