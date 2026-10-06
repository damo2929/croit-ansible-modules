#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /servers
# croit-api: GET /servers/{serverId}/nics
# croit-api: PATCH /servers/{serverId}/nics/{nicId}
# croit-api: DELETE /servers/{serverId}/nics/{nicId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: server_nic
short_description: Manage network interfaces of croit servers
version_added: 0.1.0
description:
  - Manages the addresses and notes croit configures on a network interface of a server, and removes
    interface records.
  - Interfaces cannot be created through this module. Physical interfaces are reported by the node itself,
    bonds are created with M(croit.ceph.server_bond) and VLANs with M(croit.ceph.server_vlan).
  - Only options that are set are managed; anything left out keeps its current value.
  - For an interface croit does not manage (a software interface it only observes), only O(notes) can be set.
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
  - Changing or removing the address croit reaches the server on, or deleting the interface that carries
    it, is refused unless O(allow_management_ip_change=true), also in check mode.
  - Deleting an interface record makes croit stop configuring it, which removes its addresses and VLANs
    from the node at its next configuration run.
seealso:
  - module: croit.ceph.server_bond
    description: Create and change bonds of interfaces.
  - module: croit.ceph.server_vlan
    description: Create and change VLAN interfaces.
  - module: croit.ceph.server_info
    description: Read servers with their interfaces (O(croit.ceph.server_info#module:include_nics=true)).
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
options:
  server:
    description:
      - The server, by hostname or numeric croit id.
    type: str
    required: true
  nic:
    description:
      - The interface, by croit name, OS (Linux) name or MAC address.
    type: str
    required: true
  state:
    description:
      - V(present) manages the interface's settings.
      - V(absent) deletes croit's record of the interface and needs O(confirm_delete=true). croit stops
        configuring it, which removes its addresses and VLANs from the node.
    type: str
    choices: [present, absent]
    default: present
  ip:
    description:
      - IPv4 address of the interface, in the form croit uses (for example V(10.0.0.17/24)). An empty string removes it.
    type: str
  ip6:
    description:
      - IPv6 address of the interface. An empty string removes it.
    type: str
  notes:
    description:
      - Free text croit keeps about the interface. An empty string clears it.
    type: str
  new_mac:
    description:
      - MAC address of a replacement card, when the interface's hardware was swapped. Only for offline
        servers; croit warns about it, see O(ignore_warnings).
    type: str
  allow_management_ip_change:
    description:
      - Allow changing or removing the address croit reaches the server on, or deleting the interface that
        carries it. Getting this wrong cuts the node off from croit.
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to delete an existing interface record.
    type: bool
    default: false
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Address the cluster network interface
  croit.ceph.server_nic:
    server: storage-07
    nic: ens2f1
    ip: 192.168.50.17/24
    notes: cluster network, switch B port 12
  register: cluster_nic

- name: Show the interface's croit name and address
  ansible.builtin.debug:
    msg: "{{ cluster_nic.nic.name }} has {{ cluster_nic.nic.ip }}"

- name: Remove a stale IPv6 address
  croit.ceph.server_nic:
    server: storage-07
    nic: "3c:fd:fe:aa:bb:cc"
    ip6: ""

- name: Forget the record of a removed card (removes its addresses from the node)
  croit.ceph.server_nic:
    server: storage-07
    nic: ens3f0
    state: absent
    confirm_delete: true
"""

RETURN = r"""
nic:
  description:
    - The interface as croit reports it after the change (C(NicResponse) in the croit API).
    - Before the change in check mode; empty after O(state=absent) or when the interface does not exist.
  returned: always
  type: dict
  contains:
    id:
      description: croit's numeric interface id.
      returned: when the interface exists
      type: int
      sample: 31
    name:
      description: croit's name for the interface.
      returned: when the interface exists
      type: str
      sample: eth1
    linuxName:
      description: The interface name the node's OS uses.
      returned: when the interface exists
      type: str
      sample: ens2f1
    mac:
      description: MAC address.
      returned: when the interface exists
      type: str
      sample: "3c:fd:fe:aa:bb:cc"
    ip:
      description: IPv4 address with prefix length, or null.
      returned: when the interface exists
      type: str
      sample: 192.168.50.17/24
    ip6:
      description: IPv6 address with prefix length, or null.
      returned: when the interface exists
      type: str
      sample: null
    notes:
      description: Free text croit keeps about the interface.
      returned: when the interface exists
      type: str
      sample: cluster network, switch B port 12
    type:
      description: V(normal), V(bond), V(infiniband) or V(unknown).
      returned: when the interface exists
      type: str
      sample: normal
    isManaged:
      description: Whether croit configures this interface.
      returned: when the interface exists
      type: bool
      sample: true
    vlans:
      description: VLAN interfaces on top of this interface (C(VlanInfo) in the croit API).
      returned: when the interface exists
      type: list
      elements: dict
      sample: [{id: 512, vlan: 110, ip: 10.110.0.17/24}]
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_nic, normalise_mac, require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

FIELDS = dict(ip="ip", ip6="ip6", notes="notes")


def host_part(address):
    return (address or "").split("/", 1)[0]


def managed_view(nic):
    if not nic:
        return {}
    return dict(ip=nic.get("ip") or "", ip6=nic.get("ip6") or "", notes=nic.get("notes") or "", mac=nic.get("mac"))


class ServerNicModule(CroitModule):
    def __init__(self):
        super(ServerNicModule, self).__init__(
            dict(
                server=dict(type="str", required=True),
                nic=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                ip=dict(type="str"),
                ip6=dict(type="str"),
                notes=dict(type="str"),
                new_mac=dict(type="str"),
                allow_management_ip_change=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
            wait=False,
        )

    def run(self):
        p = self.params
        server = require_server(self, p["server"])
        nics = self.get_list(path_join("servers", server["id"], "nics"))
        current = find_nic(self, nics, p["nic"])
        carries_management_ip = bool(current) and bool(current.get("ip")) and host_part(current.get("ip")) == server.get("ip")

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, nic={})
            if not p["confirm_delete"]:
                self.module.fail_json(
                    msg="Refusing to delete interface %r of %s without confirm_delete=true"
                    % (current["name"], server["hostname"])
                )
            if carries_management_ip and not p["allow_management_ip_change"]:
                self.module.fail_json(
                    msg="Interface %r carries %s's management IP %s; deleting it cuts the node off. "
                    "Set allow_management_ip_change=true if that is intended."
                    % (current["name"], server["hostname"], server.get("ip"))
                )
            if not self.check_mode:
                self.write("DELETE", path_join("servers", server["id"], "nics", current["id"]))
            self.exit(changed=True, before=managed_view(current), after={}, nic={})

        if current is None:
            self.module.fail_json(
                msg="Server %s has no interface %r. Physical interfaces are reported by the node; use "
                "croit.ceph.server_bond or croit.ceph.server_vlan to create bonds and VLANs. Known interfaces: %s"
                % (server["hostname"], p["nic"], ", ".join("%s (%s)" % (n.get("name"), n.get("mac")) for n in nics) or "none")
            )

        before = managed_view(current)
        changes = {}
        for opt, api in FIELDS.items():
            if p[opt] is not None and p[opt] != before[opt]:
                changes[api] = p[opt]
        if p["new_mac"] is not None and normalise_mac(p["new_mac"]) != normalise_mac(current.get("mac")):
            changes["mac"] = p["new_mac"]

        if current.get("isManaged") is False:
            refused = sorted(k for k in changes if k != "notes")
            if refused:
                self.module.fail_json(
                    msg="croit does not manage interface %r, so only notes can be changed (asked for: %s)"
                    % (current["name"], ", ".join(refused))
                )
        if (
            "ip" in changes
            and carries_management_ip
            and host_part(changes["ip"]) != host_part(current.get("ip"))
            and not p["allow_management_ip_change"]
        ):
            self.module.fail_json(
                msg="Interface %r carries %s's management IP %s; changing it cuts the node off. "
                "Set allow_management_ip_change=true if that is intended."
                % (current["name"], server["hostname"], server.get("ip"))
            )

        after = dict(before)
        for opt, api in list(FIELDS.items()) + [("mac", "mac")]:
            if api in changes:
                after[opt] = changes[api]

        if not changes or self.check_mode:
            self.exit(changed=bool(changes), before=before, after=after, nic=current)

        self.write("PATCH", path_join("servers", server["id"], "nics", current["id"]), body=changes)
        refreshed = [n for n in self.get_list(path_join("servers", server["id"], "nics")) if n.get("id") == current["id"]]
        self.exit(changed=True, before=before, after=after, nic=refreshed[0] if refreshed else current)


def main():
    ServerNicModule().run()


if __name__ == "__main__":
    main()
