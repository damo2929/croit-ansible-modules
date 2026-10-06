#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /maintenance/flags
# croit-api: PUT /maintenance/flags/{flag}/set
# croit-api: PUT /maintenance/flags/{flag}/unset

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: osd_flag
short_description: Set and unset cluster-wide OSD map flags on a croit cluster
version_added: 0.1.0
description:
  - Sets or clears OSD map flags such as C(noout), C(noscrub) or C(norebalance), typically around maintenance.
  - Only the flags croit offers can be managed; unknown flags fail the task and list the ones croit offers.
  - C(pause) counts as set when either half of it (C(pauserd), C(pausewr)) is set, as croit reports it.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  flags:
    description:
      - The flags to manage, for example V(noout). A single flag can be given as a string.
    type: list
    elements: str
    required: true
    aliases: [flag]
  state:
    description:
      - Whether the flags should be set (V(present)) or cleared (V(absent)).
    type: str
    choices: [present, absent]
    default: present
"""

EXAMPLES = r"""
- name: Stop ceph from marking OSDs out during maintenance
  croit.ceph.osd_flag:
    flags: [noout, norebalance]

- name: Clear them again
  croit.ceph.osd_flag:
    flags: [noout, norebalance]
    state: absent
"""

RETURN = r"""
flags:
  description:
    - Every flag croit offers after the change (C(CephFlagReponse) in the croit API), with its current state.
  returned: always
  type: list
  elements: dict
  sample:
    - name: noout
      currentState: true
      recommendedState: false
      description: OSDs will not automatically be marked out after the configured interval
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            flags=dict(type="list", elements="str", required=True, aliases=["flag"]),
            state=dict(type="str", default="present", choices=["present", "absent"]),
        ),
        wait=False,
        warnings=False,
    )
    wanted = []
    for flag in m.params["flags"]:
        if flag not in wanted:
            wanted.append(flag)
    if not wanted:
        m.module.fail_json(msg="flags must name at least one flag")
    present = m.params["state"] == "present"

    offered = m.get_list("/maintenance/flags")
    current = dict((f.get("name"), bool(f.get("currentState"))) for f in offered)
    unknown = [f for f in wanted if f not in current]
    if unknown:
        m.module.fail_json(
            msg="croit does not offer flag(s) %s. Flags it offers: %s" % (", ".join(unknown), ", ".join(sorted(current)))
        )

    before = dict((f, current[f]) for f in wanted)
    after = dict((f, present) for f in wanted)
    todo = [f for f in wanted if current[f] != present]
    if not todo or m.check_mode:
        m.exit(changed=bool(todo), before=before, after=after, flags=offered)

    action = "set" if present else "unset"
    for flag in todo:
        m.write("PUT", path_join("maintenance", "flags", flag, action))
    m.exit(changed=True, before=before, after=after, flags=m.get_list("/maintenance/flags"))


if __name__ == "__main__":
    main()
