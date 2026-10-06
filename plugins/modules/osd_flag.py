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
  - Sets or clears OSD map flags such as C(noout), C(noscrub) or C(norebalance), typically around
    maintenance. Only the flags listed in O(flags) are managed; every other flag is left as it is.
  - Only the flags croit offers can be managed; unknown flags fail the task, before anything is changed,
    and list the flags croit offers.
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
      - Duplicates are ignored; an empty list fails the task.
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
notes:
  - Flags such as C(noout), C(norecover) or C(pause) change how the whole cluster behaves. Clear them
    again when maintenance is done, for example in an C(always) section.
seealso:
  - module: croit.ceph.cluster_tuning
    description: Tune recovery speed and full ratios.
  - module: croit.ceph.server
    description: Reboot servers during maintenance.
  - module: croit.ceph.cluster_info
    description: Check cluster health before and after maintenance.
  - name: croit API reference
    description: The croit REST API, including the C(/maintenance/flags) endpoints.
    link: https://www.croit.io/api-docs
  - name: Ceph OSD flags
    description: Upstream documentation of the OSD map flags.
    link: https://docs.ceph.com/en/latest/rados/operations/health-checks/#osdmap-flags
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Maintenance on a node without rebalancing
  block:
    - name: Stop ceph from marking OSDs out
      croit.ceph.osd_flag:
        flags: [noout, norebalance]
      register: maintenance_flags

    - name: Show which flags are now set cluster-wide
      ansible.builtin.debug:
        msg: "{{ maintenance_flags.flags | selectattr('currentState') | map(attribute='name') | list }}"

    - name: Reboot the node
      croit.ceph.server:
        server: node3
        action: reboot
        confirm_action: true
  always:
    - name: Clear the flags again
      croit.ceph.osd_flag:
        flags: [noout, norebalance]
        state: absent

- name: Pause scrubbing during a backup window
  croit.ceph.osd_flag:
    flag: noscrub
"""

RETURN = r"""
flags:
  description:
    - Every flag croit offers (C(CephFlagReponse) in the croit API), with its state after the change;
      before the change in check mode.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: The flag's name.
      returned: always
      type: str
      sample: noout
    currentState:
      description: Whether the flag is set.
      returned: always
      type: bool
      sample: true
    recommendedState:
      description: Whether croit recommends the flag to be set in normal operation.
      returned: always
      type: bool
      sample: false
    description:
      description: What the flag does, as croit describes it.
      returned: always
      type: str
      sample: OSDs will not automatically be marked out after the configured interval
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
