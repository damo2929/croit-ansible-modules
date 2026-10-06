#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /servers
# croit-api: GET /servers/{serverId}/nics
# croit-api: GET /servers/{serverId}/nics/{nicId}/vlans
# croit-api: POST /servers/{serverId}/nics/{nicId}/vlans
# croit-api: PATCH /servers/{serverId}/nics/{nicId}/vlans/{vlanId}
# croit-api: DELETE /servers/{serverId}/nics/{nicId}/vlans/{vlanId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: server_vlan
short_description: Manage VLAN interfaces of croit servers
version_added: 0.1.0
description:
  - Creates, changes and deletes a VLAN on a network interface (or bond) of a croit server.
  - croit refuses VLANs on interfaces it does not manage and on bond members; put them on the bond instead.
  - Only options that are set are managed; anything left out keeps its current value.
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
  server:
    description:
      - The server, by hostname or numeric croit id.
    type: str
    required: true
  nic:
    description:
      - The parent interface or bond, by croit name, OS name or MAC address.
    type: str
    required: true
  vlan:
    description:
      - VLAN tag (1-4094).
    type: int
    required: true
  state:
    description:
      - V(absent) deletes the VLAN and needs O(confirm_delete=true).
    type: str
    choices: [present, absent]
    default: present
  ip:
    description:
      - IPv4 address of the VLAN interface, in the form croit uses (for example V(10.10.0.17/24)). An empty string removes it.
      - croit warns when the address is already used elsewhere, see O(ignore_warnings).
    type: str
  ip6:
    description:
      - IPv6 address of the VLAN interface. An empty string removes it.
    type: str
  allow_management_ip_change:
    description:
      - Allow changing, removing or deleting the address croit reaches the server on. Getting this wrong
        cuts the node off from croit.
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing VLAN.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Public network on VLAN 110 of the bond
  croit.ceph.server_vlan:
    server: storage-07
    nic: bond0
    vlan: 110
    ip: 10.110.0.17/24

- name: Remove VLAN 120
  croit.ceph.server_vlan:
    server: storage-07
    nic: bond0
    vlan: 120
    state: absent
    confirm_delete: true
"""

RETURN = r"""
vlan:
  description:
    - The VLAN as croit reports it after the change (C(VlanInfo) in the croit API).
    - Before the change in check mode; empty when it does not exist.
  returned: always
  type: dict
  sample:
    id: 512
    nic: 41
    vlan: 110
    ip: 10.110.0.17/24
    ip6: null
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_nic, require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def host_part(address):
    return (address or "").split("/", 1)[0]


def managed_view(vlan):
    if not vlan:
        return {}
    return dict(vlan=vlan.get("vlan"), ip=vlan.get("ip") or "", ip6=vlan.get("ip6") or "")


class ServerVlanModule(CroitModule):
    def __init__(self):
        super(ServerVlanModule, self).__init__(
            dict(
                server=dict(type="str", required=True),
                nic=dict(type="str", required=True),
                vlan=dict(type="int", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                ip=dict(type="str"),
                ip6=dict(type="str"),
                allow_management_ip_change=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
            wait=False,
        )

    def guard_management_ip(self, server, current, new_ip):
        """Fail when the VLAN carries the management IP and would lose it."""
        if self.params["allow_management_ip_change"] or not current or not current.get("ip"):
            return
        if host_part(current["ip"]) != server.get("ip"):
            return
        if new_ip is None or host_part(new_ip) != host_part(current["ip"]):
            self.module.fail_json(
                msg="VLAN %s carries %s's management IP %s; changing or removing it cuts the node off. "
                "Set allow_management_ip_change=true if that is intended." % (current["vlan"], server["hostname"], server.get("ip"))
            )

    def run(self):
        p = self.params
        if not 1 <= p["vlan"] <= 4094:
            self.module.fail_json(msg="vlan must be between 1 and 4094")
        server = require_server(self, p["server"])
        nics = self.get_list(path_join("servers", server["id"], "nics"))
        parent = find_nic(self, nics, p["nic"])
        if parent is None:
            self.module.fail_json(
                msg="Server %s has no interface %r. Known interfaces: %s"
                % (server["hostname"], p["nic"], ", ".join("%s (%s)" % (n.get("name"), n.get("mac")) for n in nics) or "none")
            )
        vlans_path = path_join("servers", server["id"], "nics", parent["id"], "vlans")
        vlans = self.get_list(vlans_path)
        current = next((v for v in vlans if v.get("vlan") == p["vlan"]), None)

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, vlan={})
            if not p["confirm_delete"]:
                self.module.fail_json(
                    msg="Refusing to delete VLAN %s on %s of %s without confirm_delete=true"
                    % (p["vlan"], parent["name"], server["hostname"])
                )
            self.guard_management_ip(server, current, None)
            if not self.check_mode:
                self.write("DELETE", path_join("servers", server["id"], "nics", parent["id"], "vlans", current["id"]))
            self.exit(changed=True, before=managed_view(current), after={}, vlan={})

        if current is None:
            body = dict(vlan=p["vlan"])
            for key in ("ip", "ip6"):
                if p[key]:
                    body[key] = p[key]
            after = dict(vlan=p["vlan"], ip=p["ip"] or "", ip6=p["ip6"] or "")
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, vlan={})
            self.write("POST", vlans_path, body=body)
            created = next((v for v in self.get_list(vlans_path) if v.get("vlan") == p["vlan"]), {})
            self.exit(changed=True, before={}, after=after, vlan=created)

        before = managed_view(current)
        changes = dict((k, p[k]) for k in ("ip", "ip6") if p[k] is not None and p[k] != before[k])
        if "ip" in changes:
            self.guard_management_ip(server, current, changes["ip"] or None)
        after = dict(before)
        after.update(changes)

        if not changes or self.check_mode:
            self.exit(changed=bool(changes), before=before, after=after, vlan=current)

        self.write("PATCH", path_join("servers", server["id"], "nics", parent["id"], "vlans", current["id"]), body=changes)
        refreshed = next((v for v in self.get_list(vlans_path) if v.get("id") == current["id"]), current)
        self.exit(changed=True, before=before, after=after, vlan=refreshed)


def main():
    ServerVlanModule().run()


if __name__ == "__main__":
    main()
