#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /services/cephfsguard
# croit-api: GET /services/cephfsguard/{configId}/services
# croit-api: GET /services/cephfsguard/{configId}/webhooks
# croit-api: GET /services/cephfsguard/incidents

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: cephfs_guard_info
short_description: Read cephfs-guard configurations, instances and incidents from a croit cluster
version_added: 0.1.0
description:
  - Returns the cephfs-guard configuration of every guarded CephFS volume, with its health and instances.
  - Optionally returns the alerting webhooks (URLs masked) and the incidents cephfs-guard raised.
  - Read-only; incident triage is left to operators in the croit UI.
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
  volume:
    description:
      - Only return the configuration (and incidents) of this CephFS volume.
    type: str
  webhooks:
    description:
      - Also return each volume's alerting webhooks. Their URLs are masked, because they often carry tokens.
    type: bool
    default: false
  incidents:
    description:
      - Also return the incidents cephfs-guard raised, most recent activity first.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Health of every guarded volume
  croit.ceph.cephfs_guard_info:
  register: guard

- name: Alert when a volume has active detections
  ansible.builtin.debug:
    msg: "{{ item.volume }} has active cephfs-guard detections"
  loop: "{{ guard.configs }}"
  when: item.health.hasActiveDetections | default(false)

- name: Incidents of one volume
  croit.ceph.cephfs_guard_info:
    volume: cephfs
    incidents: true
"""

RETURN = r"""
configs:
  description:
    - The cephfs-guard configurations (C(CephfsGuardConfigResponse)), each with C(services)
      (C(CephfsGuardServiceResponse)) added, and C(webhooks) with O(webhooks=true).
  returned: always
  type: list
  elements: dict
incidents:
  description: The incidents (C(CephfsGuardIncidentResponse)), filtered by O(volume) when set.
  returned: when O(incidents=true)
  type: list
  elements: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def main():
    m = CroitModule(
        dict(
            volume=dict(type="str"),
            webhooks=dict(type="bool", default=False),
            incidents=dict(type="bool", default=False),
        ),
        wait=False,
        warnings=False,
    )
    p = m.params
    configs = []
    for config in m.get_list("/services/cephfsguard"):
        if p["volume"] is not None and config.get("volume") != p["volume"]:
            continue
        item = dict(config)
        item["services"] = (m.get(path_join("services", "cephfsguard", config["id"], "services")) or {}).get("services") or []
        if p["webhooks"]:
            hooks = (m.get(path_join("services", "cephfsguard", config["id"], "webhooks")) or {}).get("webhooks") or []
            item["webhooks"] = [dict(h, url="********") for h in hooks]
        configs.append(item)
    result = dict(changed=False, configs=configs)
    if p["incidents"]:
        incidents = m.get_list("/services/cephfsguard/incidents")
        if p["volume"] is not None:
            incidents = [i for i in incidents if i.get("volume") == p["volume"]]
        result["incidents"] = incidents
    m.exit(**result)


if __name__ == "__main__":
    main()
