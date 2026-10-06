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
options:
  server:
    description:
      - Only return the disks of this server, by hostname or numeric id.
    type: str
  roles:
    description:
      - Only return disks with one of these roles, for example V(unassigned) to find disks free for new OSDs.
    type: list
    elements: str
    choices: [unassigned, mon, osd, journal, other, raid, deleting, updating, mon_unused, old_osd, old_mon, boot]
  device_classes:
    description:
      - Only return disks of these device classes.
    type: list
    elements: str
    choices: [hdd, ssd, nvme, pmem]
  include_missing:
    description:
      - Also return disks the node no longer sees.
    type: bool
    default: true
"""

EXAMPLES = r"""
- name: Free SSDs on one node
  croit.ceph.disk_info:
    server: storage-07
    roles: [unassigned]
    device_classes: [ssd, nvme]
  register: free

- name: Disks that disappeared
  croit.ceph.disk_info:
  register: all_disks

- name: Show missing disks
  ansible.builtin.debug:
    msg: "{{ all_disks.disks | selectattr('missing') | map(attribute='serial') | list }}"
"""

RETURN = r"""
disks:
  description: The disks (C(DiskResponse) in the croit API).
  returned: always
  type: list
  elements: dict
  sample:
    - id: 31
      hostname: storage-07
      server: 7
      role: unassigned
      deviceClass: ssd
      size: 1920383410176
      serial: S4EVNX0R123456
      path: /dev/sdc
      missing: false
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
