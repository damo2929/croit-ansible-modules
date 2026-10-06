#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /servers
# croit-api: GET /servers/{serverId}/nics
# croit-api: POST /servers/{serverId}/nics/bonds
# croit-api: PATCH /servers/{serverId}/nics/{nicId}
# croit-api: DELETE /servers/{serverId}/nics/{nicId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: server_bond
short_description: Manage network bonds of croit servers
version_added: 0.1.0
description:
  - Creates, changes and deletes a bond (link aggregation) of network interfaces on a croit server.
  - A new bond takes over the addresses and VLANs of its members. Set the bond's own addresses with
    M(croit.ceph.server_nic), using the bond's name.
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
notes:
  - Deleting a bond that carries the address croit reaches the server on is refused unless
    O(allow_management_ip_change=true), also in check mode.
seealso:
  - module: croit.ceph.server_nic
    description: Set the bond's addresses and notes, using the bond's name.
  - module: croit.ceph.server_vlan
    description: Create VLAN interfaces on top of the bond.
  - module: croit.ceph.server_info
    description: Read servers with their interfaces.
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
options:
  server:
    description:
      - The server, by hostname or numeric croit id.
    type: str
    required: true
  name:
    description:
      - Name of the bond, for example V(bond0). It identifies the bond on the server and cannot be changed.
    type: str
    required: true
  state:
    description:
      - V(present) creates the bond, or changes its members, mode and primary.
      - V(absent) deletes the bond and needs O(confirm_delete=true).
    type: str
    choices: [present, absent]
    default: present
  members:
    description:
      - The bond's member interfaces, by croit name, OS name or MAC address. The complete list.
      - Required when creating the bond. croit refuses interfaces it does not manage, non-ethernet or
        non-infiniband interfaces, a mix of both, and interfaces a service binds to directly.
    type: list
    elements: str
  mode:
    description:
      - Bonding mode. croit creates an LACP bond when not set.
    type: str
    choices: [lacp, active_passive]
  primary:
    description:
      - Primary member of an V(active_passive) bond, by croit name, OS name or MAC address. Must be one of O(members).
    type: str
  allow_management_ip_change:
    description:
      - Allow deleting a bond that carries the address croit reaches the server on. Getting this wrong
        cuts the node off from croit.
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing bond.
    type: bool
    default: false
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: LACP bond over two 25G ports
  croit.ceph.server_bond:
    server: storage-07
    name: bond0
    members: [ens1f0, ens1f1]
  register: bond

- name: Show the bond's members as croit ids
  ansible.builtin.debug:
    msg: "{{ bond.bond.name }} bonds interfaces {{ bond.bond.bondedNics }}"

- name: Active/passive bond with a preferred port
  croit.ceph.server_bond:
    server: storage-07
    name: bond1
    members: [ens2f0, ens2f1]
    mode: active_passive
    primary: ens2f0

- name: Delete a bond
  croit.ceph.server_bond:
    server: storage-07
    name: bond1
    state: absent
    confirm_delete: true
"""

RETURN = r"""
bond:
  description:
    - The bond interface as croit reports it after the change (C(NicResponse) in the croit API).
    - Before the change in check mode; empty when it does not exist or after O(state=absent).
  returned: always
  type: dict
  contains:
    id:
      description: croit's numeric interface id of the bond.
      returned: when the bond exists
      type: int
      sample: 44
    name:
      description: Name of the bond.
      returned: when the bond exists
      type: str
      sample: bond0
    type:
      description: Always V(bond) for a bond.
      returned: when the bond exists
      type: str
      sample: bond
    bondedNics:
      description: croit interface ids of the members.
      returned: when the bond exists
      type: list
      elements: int
      sample: [31, 32]
    bondType:
      description: V(lacp) or V(active_passive).
      returned: when the bond exists
      type: str
      sample: lacp
    bondPrimary:
      description: croit interface id of the primary member of an active/passive bond, or null.
      returned: when the bond exists
      type: int
      sample: null
    ip:
      description: IPv4 address of the bond, or null.
      returned: when the bond exists
      type: str
      sample: 10.0.0.17/24
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_nic, require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


class ServerBondModule(CroitModule):
    def __init__(self):
        super(ServerBondModule, self).__init__(
            dict(
                server=dict(type="str", required=True),
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                members=dict(type="list", elements="str"),
                mode=dict(type="str", choices=["lacp", "active_passive"]),
                primary=dict(type="str"),
                allow_management_ip_change=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
            wait=False,
        )

    def nic_id(self, nics, ident):
        found = find_nic(self, nics, ident)
        if found is None:
            self.module.fail_json(
                msg="Server %s has no interface %r. Known interfaces: %s"
                % (self.server["hostname"], ident, ", ".join("%s (%s)" % (n.get("name"), n.get("mac")) for n in nics))
            )
        return found["id"]

    def view(self, bond, nics):
        if not bond:
            return {}
        names = dict((n["id"], n.get("name")) for n in nics)
        return dict(
            members=sorted(names.get(i, str(i)) for i in bond.get("bondedNics") or []),
            mode=bond.get("bondType") or "lacp",
            primary=names.get(bond.get("bondPrimary")) if bond.get("bondPrimary") is not None else None,
        )

    def run(self):
        p = self.params
        self.server = require_server(self, p["server"])
        nics_path = path_join("servers", self.server["id"], "nics")
        nics = self.get_list(nics_path)
        current = find_nic(self, nics, p["name"])
        if current is not None and current.get("type") != "bond":
            self.module.fail_json(msg="Interface %r of %s is not a bond" % (p["name"], self.server["hostname"]))

        if p["state"] == "absent":
            return self.absent(current, nics)

        members = None
        if p["members"] is not None:
            if not p["members"]:
                self.module.fail_json(msg="members must name at least one interface")
            members = sorted(set(self.nic_id(nics, m) for m in p["members"]))
        primary = self.nic_id(nics, p["primary"]) if p["primary"] is not None else None
        if primary is not None:
            if (p["mode"] or (current or {}).get("bondType") or "lacp") != "active_passive":
                self.module.fail_json(msg="primary only applies to mode=active_passive")
            effective_members = members if members is not None else sorted((current or {}).get("bondedNics") or [])
            if primary not in effective_members:
                self.module.fail_json(msg="primary %r is not a member of the bond" % p["primary"])

        if current is None:
            if members is None:
                self.module.fail_json(msg="members is required to create bond %r" % p["name"])
            body = dict(name=p["name"], nics=members, activePassive=p["mode"] == "active_passive", primary=primary)
            names = dict((n["id"], n.get("name")) for n in nics)
            after = dict(
                members=sorted(names[i] for i in members),
                mode=p["mode"] or "lacp",
                primary=names.get(primary),
            )
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, bond={})
            self.write("POST", path_join("servers", self.server["id"], "nics", "bonds"), body=body)
            nics = self.get_list(nics_path)
            self.exit(changed=True, before={}, after=after, bond=find_nic(self, nics, p["name"]) or {})

        bond_changes = {}
        if members is not None and members != sorted(current.get("bondedNics") or []):
            bond_changes["nics"] = members
        if p["mode"] is not None and p["mode"] != (current.get("bondType") or "lacp"):
            bond_changes["activePassive"] = p["mode"] == "active_passive"
        if primary is not None and primary != current.get("bondPrimary"):
            bond_changes["primary"] = primary

        before = self.view(current, nics)
        after = dict(before)
        names = dict((n["id"], n.get("name")) for n in nics)
        if "nics" in bond_changes:
            after["members"] = sorted(names[i] for i in members)
        if "activePassive" in bond_changes:
            after["mode"] = p["mode"]
        if "primary" in bond_changes:
            after["primary"] = names.get(primary)

        if not bond_changes or self.check_mode:
            self.exit(changed=bool(bond_changes), before=before, after=after, bond=current)

        self.write("PATCH", path_join("servers", self.server["id"], "nics", current["id"]), body=dict(bond=bond_changes))
        refreshed = [n for n in self.get_list(nics_path) if n.get("id") == current["id"]]
        self.exit(changed=True, before=before, after=after, bond=refreshed[0] if refreshed else current)

    def absent(self, current, nics):
        p = self.params
        if current is None:
            self.exit(changed=False, bond={})
        if not p["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to delete bond %r of %s without confirm_delete=true" % (current["name"], self.server["hostname"])
            )
        if current.get("ip") and current["ip"].split("/", 1)[0] == self.server.get("ip") and not p["allow_management_ip_change"]:
            self.module.fail_json(
                msg="Bond %r carries %s's management IP %s; deleting it cuts the node off. "
                "Set allow_management_ip_change=true if that is intended."
                % (current["name"], self.server["hostname"], self.server.get("ip"))
            )
        if not self.check_mode:
            self.write("DELETE", path_join("servers", self.server["id"], "nics", current["id"]))
        self.exit(changed=True, before=self.view(current, nics), after={}, bond={})


def main():
    ServerBondModule().run()


if __name__ == "__main__":
    main()
