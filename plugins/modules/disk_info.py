#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /disks
# croit-api: GET /servers
# croit-api: GET /servers/{serverId}/disks

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: disk_info
short_description: Read the disks of a croit cluster
version_added: 0.1.0
description:
  - Returns the disks croit's nodes have reported, with their role, SMART health and Ceph usage.
  - The filters O(server), O(roles), O(device_classes) and O(include_missing) combine; with none set,
    every disk of the cluster is returned.
  - Read-only; it never changes anything and always reports no change.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: N/A
seealso:
  - module: croit.ceph.osd
    description: Create OSDs on unassigned disks.
  - module: croit.ceph.server_info
    description: Read the servers the disks belong to.
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
options:
  server:
    description:
      - Only return the disks of this server, by hostname or numeric id. An unknown server fails the task.
    type: str
  roles:
    description:
      - Only return disks with one of these roles, for example V(unassigned) to find disks free for new OSDs.
    type: list
    elements: str
    choices: [unassigned, mon, osd, journal, other, raid, deleting, updating, mon_unused, old_osd, old_mon, boot]
  device_classes:
    description:
      - Only return disks of these device classes, as croit detected them.
    type: list
    elements: str
    choices: [hdd, ssd, nvme, pmem]
  include_missing:
    description:
      - Also return disks the node no longer sees (C(missing) is V(true) for those).
    type: bool
    default: true
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Free SSDs on one node
  croit.ceph.disk_info:
    server: storage-07
    roles: [unassigned]
    device_classes: [ssd, nvme]
  register: free

- name: Show the device paths of the free disks
  ansible.builtin.debug:
    msg: "{{ free.disks | map(attribute='path') | list }}"

- name: Every disk of the cluster
  croit.ceph.disk_info:
  register: all_disks

- name: Show the serials of disks that disappeared
  ansible.builtin.debug:
    msg: "{{ all_disks.disks | selectattr('missing') | map(attribute='serial') | list }}"
"""

RETURN = r"""
disks:
  description: The disks that match the filters (C(DiskResponse) in the croit API).
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description: croit's numeric disk id.
      returned: always
      type: int
      sample: 31
    server:
      description: croit id of the server the disk is in.
      returned: always
      type: int
      sample: 7
    hostname:
      description: Hostname of the server the disk is in.
      returned: always
      type: str
      sample: storage-07
    path:
      description: Device path on the node, or null.
      returned: always
      type: str
      sample: /dev/sdc
    serial:
      description: Serial number.
      returned: always
      type: str
      sample: S4EVNX0R123456
    wwn:
      description: World wide name, or null.
      returned: always
      type: str
      sample: "0x5002538e40a1b2c3"
    size:
      description: Size in bytes.
      returned: always
      type: int
      sample: 1920383410176
    role:
      description: What the disk is used for, for example V(unassigned), V(osd) or V(mon).
      returned: always
      type: str
      sample: unassigned
    deviceClass:
      description: V(hdd), V(ssd), V(nvme) or V(pmem).
      returned: always
      type: str
      sample: ssd
    osdId:
      description: Id of the OSD on the disk, or null.
      returned: always
      type: int
      sample: null
    missing:
      description: Whether the node no longer sees the disk.
      returned: always
      type: bool
      sample: false
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

ROLES = ["unassigned", "mon", "osd", "journal", "other", "raid", "deleting", "updating", "mon_unused", "old_osd", "old_mon", "boot"]


def main():
    m = CroitModule(
        dict(
            server=dict(type="str"),
            roles=dict(type="list", elements="str", choices=ROLES),
            device_classes=dict(type="list", elements="str", choices=["hdd", "ssd", "nvme", "pmem"]),
            include_missing=dict(type="bool", default=True),
        ),
        wait=False,
        warnings=False,
    )
    p = m.params
    if p["server"] is not None:
        server = require_server(m, p["server"])
        disks = m.get_list(path_join("servers", server["id"], "disks"))
    else:
        disks = m.get_list("/disks")
    if p["roles"]:
        disks = [d for d in disks if d.get("role") in p["roles"]]
    if p["device_classes"]:
        disks = [d for d in disks if d.get("deviceClass") in p["device_classes"]]
    if not p["include_missing"]:
        disks = [d for d in disks if not d.get("missing")]
    m.exit(changed=False, disks=disks)


if __name__ == "__main__":
    main()
