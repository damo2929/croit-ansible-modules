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
  - This module never changes anything. Incident triage is left to operators in the croit UI.
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
      - Only return the configuration, and incidents, of this CephFS volume. When not set, every guarded
        volume is returned.
    type: str
  webhooks:
    description:
      - Also return each volume's alerting webhooks in RV(configs[].webhooks). Their URLs are masked,
        because they often carry tokens.
    type: bool
    default: false
  incidents:
    description:
      - Also return the incidents cephfs-guard raised in RV(incidents), most recent activity first.
    type: bool
    default: false
seealso:
  - module: croit.ceph.cephfs_guard
    description: Enable and configure cephfs-guard for a volume.
  - module: croit.ceph.cephfs_guard_webhook
    description: Manage a guarded volume's alerting webhooks.
  - name: croit API reference
    description: The croit REST API, including the C(/services/cephfsguard) endpoints.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Health of every guarded volume
  croit.ceph.cephfs_guard_info:
  register: guard

- name: Alert when a volume has active detections
  ansible.builtin.debug:
    msg: "{{ item.volume }} has active cephfs-guard detections"
  loop: "{{ guard.configs }}"
  when: item.health.hasActiveDetections | default(false)

- name: Incidents and webhooks of one volume
  croit.ceph.cephfs_guard_info:
    volume: cephfs
    incidents: true
    webhooks: true
  register: cephfs_guard

- name: Fail when an incident has not been triaged yet
  ansible.builtin.assert:
    that: cephfs_guard.incidents | selectattr('state', 'equalto', 'NEW') | list | length == 0
    fail_msg: Untriaged cephfs-guard incidents on cephfs
"""

RETURN = r"""
configs:
  description:
    - The cephfs-guard configurations (C(CephfsGuardConfigResponse) in the croit API), filtered by
      O(volume) when it is set.
  returned: always
  type: list
  elements: dict
  contains:
    id:
      description: Id of the volume's cephfs-guard configuration.
      returned: always
      type: int
      sample: 1
    volume:
      description: The guarded CephFS volume.
      returned: always
      type: str
      sample: cephfs
    detection:
      description: Detection aggregation settings (C(actionThreshold), C(minDetectors)).
      returned: always
      type: dict
      sample: {actionThreshold: 0.6, minDetectors: 1}
    detectors:
      description: Per-detector settings, each with C(enabled) and C(weight).
      returned: always
      type: dict
      sample: {fileEntropy: {enabled: true, weight: 1.0}}
    actions:
      description: Which actions run on a detection, each with C(enabled).
      returned: always
      type: dict
      sample: {snapshot: {enabled: true}, yaraScan: {enabled: false}, block: {enabled: false}}
    health:
      description: Aggregated health (C(enabled), C(healthy), C(status) one of C(ok), C(degraded) or C(no_services), C(hasActiveDetections)).
      returned: always
      type: dict
      sample: {enabled: true, healthy: true, status: ok, hasActiveDetections: false}
    services:
      description: The volume's instances (C(CephfsGuardServiceResponse) in the croit API), as RV(croit.ceph.cephfs_guard#module:services) returns them.
      returned: always
      type: list
      elements: dict
      sample: [{id: 3, serverHostname: node1, nicName: eth1, ip: 10.0.1.11, mdsPort: 7600, httpPort: 7601}]
    webhooks:
      description: The volume's alerting webhooks (C(id), C(url) masked as V(********), C(timeout)).
      returned: when O(webhooks=true)
      type: list
      elements: dict
      sample: [{id: 3, url: "********", timeout: 5s}]
incidents:
  description:
    - The incidents (C(CephfsGuardIncidentResponse) in the croit API), filtered by O(volume) when it is set.
  returned: when O(incidents=true)
  type: list
  elements: dict
  contains:
    id:
      description: Id of the incident.
      returned: always
      type: int
      sample: 17
    volume:
      description: CephFS volume the activity was seen on.
      returned: always
      type: str
      sample: cephfs
    clientId:
      description: CephFS client behind the activity.
      returned: always
      type: int
      sample: 4242
    state:
      description: C(ONGOING) while still collecting detections, otherwise the triage status such as C(NEW), C(ACKNOWLEDGED) or C(FALSE_POSITIVE).
      returned: always
      type: str
      sample: NEW
    firstSeen:
      description: When the activity was first detected.
      returned: always
      type: str
      sample: "2026-10-06T11:58:02Z"
    lastSeen:
      description: When the activity was last detected.
      returned: always
      type: str
      sample: "2026-10-06T12:01:40Z"
    maxConfidence:
      description: Highest confidence any detection reported, from 0.0 to 1.0.
      returned: always
      type: float
      sample: 0.92
    detectors:
      description: Detectors that contributed.
      returned: always
      type: list
      elements: str
      sample: [fileEntropy, extensionChange]
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
