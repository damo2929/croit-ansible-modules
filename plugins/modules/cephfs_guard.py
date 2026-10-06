#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /services/cephfsguard
# croit-api: POST /services/cephfsguard
# croit-api: GET /services/cephfsguard/{configId}
# croit-api: PATCH /services/cephfsguard/{configId}
# croit-api: DELETE /services/cephfsguard/{configId}
# croit-api: GET /services/cephfsguard/{configId}/services
# croit-api: POST /services/cephfsguard/{configId}/services
# croit-api: PATCH /services/cephfsguard/{configId}/services/{serviceId}
# croit-api: GET /servers
# croit-api: GET /servers/{serverId}/nics

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: cephfs_guard
short_description: Manage cephfs-guard ransomware protection of a CephFS volume on a croit cluster
version_added: 0.1.0
description:
  - Enable, configure and disable cephfs-guard for a CephFS volume, identified by O(volume).
  - Manages the detection settings, the detectors, the actions taken on detection, and which servers run a
    cephfs-guard instance (and its ports).
  - Only options that are set are managed; anything left out keeps its current value.
  - Alerting webhooks are managed with M(croit.ceph.cephfs_guard_webhook). Incident triage is an operator task and is
    not managed by this collection; read incidents with M(croit.ceph.cephfs_guard_info).
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
  volume:
    description:
      - The CephFS volume to guard.
    type: str
    required: true
  state:
    description:
      - V(present) enables cephfs-guard for the volume. V(absent) removes every cephfs-guard instance of the volume and
        its settings; the volume and its data are untouched, but it is no longer protected.
    type: str
    choices: [present, absent]
    default: present
  servers:
    description:
      - Servers that must run a cephfs-guard instance for the volume. Required to enable cephfs-guard.
      - Servers already running an instance that are not listed are left alone; croit offers no way to remove a single
        instance through this API.
      - The interface, VLAN and IP version of an existing instance cannot be changed; a difference fails the task.
    type: list
    elements: dict
    suboptions:
      server:
        description: Server hostname or croit id.
        type: str
        required: true
      nic:
        description: Interface to listen on, by croit name, Linux name, MAC address or croit id.
        type: str
        required: true
      vlan:
        description: VLAN tag on the interface; leave unset for the untagged interface.
        type: int
      use_ipv6:
        description: Listen on IPv6 instead of IPv4.
        type: bool
        default: false
      mds_port:
        description: MDS receiver port. croit picks one when unset.
        type: int
      http_port:
        description: HTTP port. croit picks one when unset.
        type: int
  detection:
    description:
      - Detection aggregation settings. Only the sub-options that are set are managed.
    type: dict
    suboptions:
      action_threshold:
        description: Score that triggers the actions. croit uses 0.6 when cephfs-guard is enabled without it.
        type: float
      min_detectors:
        description: Minimum number of detectors that must contribute. croit uses 1 when unset.
        type: int
  detectors:
    description:
      - Detector settings, keyed by detector. Only the detectors and sub-options that are set are managed.
    type: dict
    suboptions:
      extension_change:
        description: Suspicious file extension changes.
        type: dict
        suboptions:
          enabled:
            description: Whether the detector is enabled.
            type: bool
          weight:
            description: Weight of the detector in the score aggregation.
            type: float
      filename_change:
        description: Suspicious filename patterns in renames.
        type: dict
        suboptions:
          enabled:
            description: Whether the detector is enabled.
            type: bool
          weight:
            description: Weight of the detector in the score aggregation.
            type: float
      bulk_operations:
        description: High-frequency file operations typical of ransomware.
        type: dict
        suboptions:
          enabled:
            description: Whether the detector is enabled.
            type: bool
          weight:
            description: Weight of the detector in the score aggregation.
            type: float
      ransom_note:
        description: Creation of ransom note files.
        type: dict
        suboptions:
          enabled:
            description: Whether the detector is enabled.
            type: bool
          weight:
            description: Weight of the detector in the score aggregation.
            type: float
      file_entropy:
        description: Files with high entropy, a sign of encryption.
        type: dict
        suboptions:
          enabled:
            description: Whether the detector is enabled.
            type: bool
          weight:
            description: Weight of the detector in the score aggregation.
            type: float
      timeline_analysis:
        description: Behavioural patterns of ransomware encryption phases.
        type: dict
        suboptions:
          enabled:
            description: Whether the detector is enabled.
            type: bool
          weight:
            description: Weight of the detector in the score aggregation.
            type: float
  actions:
    description:
      - What cephfs-guard does on a detection. Only the actions that are set are managed.
      - When cephfs-guard is enabled, croit disables every action that is not set.
    type: dict
    suboptions:
      snapshot:
        description: Create CephFS snapshots.
        type: bool
      yara_scan:
        description: Scan flagged files against YARA rules.
        type: bool
      block:
        description: Evict (blocklist) the clients flagged as malicious.
        type: bool
"""

EXAMPLES = r"""
- name: Guard the cephfs volume on two nodes, snapshot and block on detection
  croit.ceph.cephfs_guard:
    volume: cephfs
    servers:
      - {server: node1, nic: eth1}
      - {server: node2, nic: eth1}
    detection:
      action_threshold: 0.7
    detectors:
      file_entropy: {enabled: true, weight: 2.0}
    actions:
      snapshot: true
      block: true

- name: Turn off client blocking
  croit.ceph.cephfs_guard:
    volume: cephfs
    actions:
      block: false

- name: Stop guarding the volume
  croit.ceph.cephfs_guard:
    volume: cephfs
    state: absent
"""

RETURN = r"""
config:
  description:
    - The volume's cephfs-guard configuration as croit reports it after the change (C(CephfsGuardConfigResponse)).
      Before the change in check mode; empty when cephfs-guard is not enabled for the volume.
  returned: always
  type: dict
services:
  description: The cephfs-guard instances of the volume (C(CephfsGuardServiceResponse)) after the change.
  returned: when the volume is guarded
  type: list
  elements: dict
task:
  description: The last croit background task the change ran as.
  returned: when a task ran
  type: dict
"""

import copy

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import require_server, resolve_interface
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

DETECTORS = dict(
    extension_change="extensionChange",
    filename_change="filenameChange",
    bulk_operations="bulkOperations",
    ransom_note="ransomNote",
    file_entropy="fileEntropy",
    timeline_analysis="timelineAnalysis",
)
ACTIONS = dict(snapshot="snapshot", yara_scan="yaraScan", block="block")
DETECTION = dict(action_threshold="actionThreshold", min_detectors="minDetectors")
DETECTOR_OPTIONS = dict(enabled=dict(type="bool"), weight=dict(type="float"))


def same(a, b):
    """Equality that ignores float noise from JSON round trips."""
    if isinstance(a, float) or isinstance(b, float):
        try:
            return round(float(a), 6) == round(float(b), 6)
        except (TypeError, ValueError):
            return False
    return a == b


def settings_view(config):
    if not config:
        return {}
    detection = config.get("detection") or {}
    detectors = config.get("detectors") or {}
    actions = config.get("actions") or {}
    return dict(
        detection=dict((opt, detection.get(api)) for opt, api in DETECTION.items()),
        detectors=dict(
            (opt, dict(enabled=(detectors.get(api) or {}).get("enabled"), weight=(detectors.get(api) or {}).get("weight")))
            for opt, api in DETECTORS.items()
        ),
        actions=dict((opt, (actions.get(api) or {}).get("enabled")) for opt, api in ACTIONS.items()),
    )


class CephfsGuardModule(CroitModule):
    def __init__(self):
        super(CephfsGuardModule, self).__init__(
            dict(
                volume=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                servers=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        server=dict(type="str", required=True),
                        nic=dict(type="str", required=True),
                        vlan=dict(type="int"),
                        use_ipv6=dict(type="bool", default=False),
                        mds_port=dict(type="int"),
                        http_port=dict(type="int"),
                    ),
                ),
                detection=dict(
                    type="dict",
                    options=dict(action_threshold=dict(type="float"), min_detectors=dict(type="int")),
                ),
                detectors=dict(
                    type="dict",
                    options=dict((name, dict(type="dict", options=DETECTOR_OPTIONS)) for name in DETECTORS),
                ),
                actions=dict(
                    type="dict",
                    options=dict((name, dict(type="bool")) for name in ACTIONS),
                ),
            ),
        )
        self._servers = None
        self._nics = {}
        self.tasks = []

    # Lookups --------------------------------------------------------------

    def all_servers(self):
        if self._servers is None:
            self._servers = self.get_list("/servers")
        return self._servers

    def nics(self, server_id):
        if server_id not in self._nics:
            self._nics[server_id] = self.get_list(path_join("servers", server_id, "nics"))
        return self._nics[server_id]

    def find_config(self):
        matches = [c for c in self.get_list("/services/cephfsguard") if c.get("volume") == self.params["volume"]]
        if len(matches) > 1:
            self.module.fail_json(msg="croit lists %d cephfs-guard configs for volume %r" % (len(matches), self.params["volume"]))
        return matches[0] if matches else None

    def services(self, config_id):
        return (self.get(path_join("services", "cephfsguard", config_id, "services")) or {}).get("services") or []

    def resolve_server(self, item):
        server = require_server(self, item["server"], self.all_servers())
        server, nic, vlan_id = resolve_interface(
            self, server["id"], item["nic"], item.get("vlan"), servers=self.all_servers(), nics=self.nics(server["id"])
        )
        return dict(
            server_id=server["id"],
            hostname=server.get("hostname"),
            nic_id=nic["id"],
            nic=nic.get("name"),
            vlan_id=vlan_id,
            vlan=item.get("vlan"),
            use_ipv6=bool(item.get("use_ipv6")),
            mds_port=item.get("mds_port"),
            http_port=item.get("http_port"),
        )

    def desired_servers(self):
        if self.params["servers"] is None:
            return None
        resolved = [self.resolve_server(i) for i in self.params["servers"]]
        seen = set()
        for item in resolved:
            if item["server_id"] in seen:
                self.module.fail_json(msg="servers lists %s more than once" % item["hostname"])
            seen.add(item["server_id"])
        return resolved

    # Settings -------------------------------------------------------------

    def settings_changes(self, config):
        """Request blocks for the settings that differ, and the desired view, against ``config`` (None when new)."""
        p = self.params
        current = settings_view(config) if config else None
        if current is not None:
            want = copy.deepcopy(current)
        else:
            want = dict(
                detection=dict((k, None) for k in DETECTION),
                detectors=dict((k, dict(enabled=None, weight=None)) for k in DETECTORS),
                actions=dict((k, None) for k in ACTIONS),
            )
        for opt, value in (p["detection"] or {}).items():
            if value is not None:
                want["detection"][opt] = value
        for name, settings in (p["detectors"] or {}).items():
            for key, value in (settings or {}).items():
                if value is not None:
                    want["detectors"][name][key] = value
        for opt, value in (p["actions"] or {}).items():
            if value is not None:
                want["actions"][opt] = value

        body = {}
        if current is None:
            # Enabling: send what the user set; croit fills in its defaults.
            for name, settings in (p["detectors"] or {}).items():
                if settings and (settings.get("enabled") is None or settings.get("weight") is None):
                    self.module.fail_json(msg="detectors.%s needs both enabled and weight when cephfs-guard is enabled" % name)
            detection_differs = detectors_differ = actions_differ = True
        else:
            detection_differs = any(not same(want["detection"][k], current["detection"][k]) for k in DETECTION)
            detectors_differ = any(
                not same(want["detectors"][n][k], current["detectors"][n][k]) for n in DETECTORS for k in ("enabled", "weight")
            )
            actions_differ = any(not same(want["actions"][k], current["actions"][k]) for k in ACTIONS)

        # Each block is sent whole (merged with the current values) when anything in it differs.
        if detection_differs:
            block = dict((api, want["detection"][opt]) for opt, api in DETECTION.items() if want["detection"][opt] is not None)
            if block:
                body["detection"] = block
        if detectors_differ:
            block = dict(
                (api, dict(enabled=want["detectors"][opt]["enabled"], weight=want["detectors"][opt]["weight"]))
                for opt, api in DETECTORS.items()
                if want["detectors"][opt]["enabled"] is not None and want["detectors"][opt]["weight"] is not None
            )
            if block:
                body["detectors"] = block
        if actions_differ:
            block = dict((api, dict(enabled=want["actions"][opt])) for opt, api in ACTIONS.items() if want["actions"][opt] is not None)
            if block:
                body["actions"] = block
        return body, want

    # Main -----------------------------------------------------------------

    def run(self):
        config = self.find_config()
        if self.params["state"] == "absent":
            return self.absent(config)
        if config is None:
            return self.create()
        return self.update(config)

    def server_view(self, services):
        return sorted(
            (
                dict(
                    server=s.get("serverHostname"),
                    nic=s.get("nicName"),
                    vlan=s.get("vlan"),
                    use_ipv6=bool(s.get("useIpv6")),
                    mds_port=s.get("mdsPort"),
                    http_port=s.get("httpPort"),
                )
                for s in services
            ),
            key=lambda v: str(v["server"]),
        )

    def absent(self, config):
        if config is None:
            self.exit(changed=False, config={})
        before = settings_view(config)
        before["servers"] = self.server_view(self.services(config["id"]))
        result = dict(config={})
        if not self.check_mode:
            self.track(self.write("DELETE", path_join("services", "cephfsguard", config["id"])))
        self.exit(changed=True, before=before, after={}, **self.with_task(result))

    def create(self):
        p = self.params
        servers = self.desired_servers()
        if not servers:
            self.module.fail_json(msg="servers is required to enable cephfs-guard for volume %r" % p["volume"])
        body, want = self.settings_changes(None)
        body.update(
            volume=p["volume"],
            servers=[
                dict(id=s["server_id"], nicId=s["nic_id"], vlanId=s["vlan_id"], useIpv6=s["use_ipv6"]) for s in servers
            ],
        )
        after = dict(want)
        after["servers"] = sorted(
            (
                dict(server=s["hostname"], nic=s["nic"], vlan=s["vlan"], use_ipv6=s["use_ipv6"], mds_port=s["mds_port"], http_port=s["http_port"])
                for s in servers
            ),
            key=lambda v: str(v["server"]),
        )
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, config={})
        self.track(self.write("POST", "/services/cephfsguard", body=body))
        config = self.find_config()
        result = dict(changed=True, before={}, after=after, config=config or {})
        if config is not None:
            services = self.services(config["id"])
            if self.set_ports(config["id"], servers, services):
                services = self.services(config["id"])
            result["services"] = services
        elif p["wait"]:
            self.module.fail_json(msg="croit reported cephfs-guard enabled for %r, but it is not listed" % p["volume"])
        self.exit(**self.with_task(result))

    def update(self, config):
        config_id = config["id"]
        body, want = self.settings_changes(config)
        services = self.services(config_id)
        before = settings_view(config)
        before["servers"] = self.server_view(services)
        after = dict(want)
        after["servers"] = [dict(v) for v in before["servers"]]

        servers = self.desired_servers()
        missing = []
        port_changes = []
        if servers is not None:
            by_server = dict((s.get("serverId"), s) for s in services)
            for item in servers:
                existing = by_server.get(item["server_id"])
                if existing is None:
                    missing.append(item)
                    after["servers"].append(
                        dict(
                            server=item["hostname"],
                            nic=item["nic"],
                            vlan=item["vlan"],
                            use_ipv6=item["use_ipv6"],
                            mds_port=item["mds_port"],
                            http_port=item["http_port"],
                        )
                    )
                    continue
                fixed = (existing.get("nicId"), existing.get("vlanId"), bool(existing.get("useIpv6")))
                if fixed != (item["nic_id"], item["vlan_id"], item["use_ipv6"]):
                    self.module.fail_json(
                        msg="The cephfs-guard instance on %s listens on %s%s (%s); its interface, VLAN and IP version cannot be "
                        "changed" % (
                            item["hostname"],
                            existing.get("nicName"),
                            " VLAN %s" % existing.get("vlan") if existing.get("vlan") is not None else "",
                            "IPv6" if existing.get("useIpv6") else "IPv4",
                        )
                    )
                ports = {}
                if item["mds_port"] is not None and item["mds_port"] != existing.get("mdsPort"):
                    ports["mdsPort"] = item["mds_port"]
                if item["http_port"] is not None and item["http_port"] != existing.get("httpPort"):
                    ports["httpPort"] = item["http_port"]
                if ports:
                    port_changes.append((existing["id"], ports))
                    for view in after["servers"]:
                        if view["server"] == item["hostname"]:
                            view.update(
                                mds_port=ports.get("mdsPort", view["mds_port"]),
                                http_port=ports.get("httpPort", view["http_port"]),
                            )
            after["servers"] = sorted(after["servers"], key=lambda v: str(v["server"]))

        changed = bool(body or missing or port_changes)
        result = dict(config=config, services=services)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, **result)

        if body:
            self.track(self.write("PATCH", path_join("services", "cephfsguard", config_id), body=body))
        if missing:
            self.track(
                self.write(
                    "POST",
                    path_join("services", "cephfsguard", config_id, "services"),
                    body=dict(
                        servers=[dict(id=s["server_id"], nicId=s["nic_id"], vlanId=s["vlan_id"], useIpv6=s["use_ipv6"]) for s in missing]
                    ),
                )
            )
            if any(s["mds_port"] is not None or s["http_port"] is not None for s in missing):
                self.set_ports(config_id, missing, self.services(config_id))
        for service_id, ports in port_changes:
            self.track(self.write("PATCH", path_join("services", "cephfsguard", config_id, "services", service_id), body=ports))

        result["config"] = self.get(path_join("services", "cephfsguard", config_id)) or config
        result["services"] = self.services(config_id)
        self.exit(changed=True, before=before, after=after, **self.with_task(result))

    def set_ports(self, config_id, servers, services):
        """PATCH the ports of new instances where the user set them; returns whether anything was sent."""
        by_server = dict((s.get("serverId"), s) for s in services)
        sent = False
        for item in servers:
            existing = by_server.get(item["server_id"])
            if existing is None:
                continue
            ports = {}
            if item["mds_port"] is not None and item["mds_port"] != existing.get("mdsPort"):
                ports["mdsPort"] = item["mds_port"]
            if item["http_port"] is not None and item["http_port"] != existing.get("httpPort"):
                ports["httpPort"] = item["http_port"]
            if ports:
                self.track(self.write("PATCH", path_join("services", "cephfsguard", config_id, "services", existing["id"]), body=ports))
                sent = True
        return sent

    # Tasks ----------------------------------------------------------------

    def track(self, data):
        task = self.handle_task(data)
        if task is not None:
            self.tasks.append(task)
        return task

    def with_task(self, result):
        if self.tasks:
            result["task"] = self.tasks[-1]
        return result


def main():
    CephfsGuardModule().run()


if __name__ == "__main__":
    main()
