#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /networks
# croit-api: POST /networks
# croit-api: PUT /networks/{networkId}
# croit-api: DELETE /networks/{networkId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: network
short_description: Manage the networks croit knows on a croit cluster
version_added: 0.1.0
description:
  - Creates, updates and deletes the subnets croit manages. A network is identified by its O(cidr).
  - croit uses them to place node addresses, to serve DHCP and PXE boot, and to write the Ceph public and
    cluster networks to C(ceph.conf).
  - Only options that are set are managed; anything left out keeps its current value. croit replaces the whole
    network on update, so the module sends the current settings merged with the requested ones, and only when
    something differs.
  - Gateway and DHCP pool addresses must lie inside the network; this is checked before anything is written.
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
    details:
      - The diff shows the type, description, MTU, gateway and DHCP pool in canonical form.
options:
  cidr:
    description:
      - The network in CIDR notation, for example V(10.10.0.0/24). It identifies the network and must include a
        prefix length.
      - A host address with a prefix such as V(10.10.0.5/24) names the same network, and is sent to croit as the
        network's address when it is created. IPv6 networks work the same way.
    type: str
    required: true
  state:
    description:
      - V(present) creates the network or updates it.
      - V(absent) deletes it. Deleting a network does not take addresses away from nodes, but croit stops handing
        out new ones from it, stops serving DHCP for it, and no longer lists it in C(ceph.conf) for its type.
    type: str
    choices: [present, absent]
    default: present
  type:
    description:
      - What croit uses the network for. V(croit) networks are used for PXE booting; V(ceph_public) and
        V(ceph_internal) become the Ceph public and cluster networks; V(ipmi) holds the BMCs.
      - croit uses V(other) when a network is created without it.
    type: str
    choices: [other, ceph_public, ceph_internal, croit, ipmi]
  description:
    description:
      - Free-text notes croit shows for the network. An empty string clears them.
    type: str
  gateway:
    description:
      - Gateway installed as the default route on servers with an address in this network. Must lie inside the
        network.
      - An empty string removes it.
    type: str
  mtu:
    description:
      - MTU of the network, for example V(9000) for jumbo frames. V(1500) is croit's default and matches a network
        that has no custom MTU.
    type: int
  dhcp_pool_start:
    description:
      - First address of the DHCP pool. Must be set together with O(dhcp_pool_end) and lie inside the network.
      - An empty string for both removes the pool.
    type: str
  dhcp_pool_end:
    description:
      - Last address of the DHCP pool. Must be set together with O(dhcp_pool_start) and lie inside the network.
    type: str
notes:
  - Every change rewrites the management node's NTP access list, restarts its NTP service and reloads the DHCP
    server.
  - Deleting a network needs no C(confirm_delete) flag, because nodes keep their addresses.
seealso:
  - module: croit.ceph.network_info
    description: Read the networks croit knows.
  - module: croit.ceph.server_nic
    description: Set the addresses of server interfaces in these networks.
  - name: croit API reference
    description: The C(/networks) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph network configuration
    description: How Ceph uses the public and cluster networks.
    link: https://docs.ceph.com/en/latest/rados/configuration/network-config-ref/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Ceph public network with jumbo frames
  croit.ceph.network:
    cidr: 10.10.0.0/24
    type: ceph_public
    mtu: 9000
    description: public network, bond0
  register: public_net

- name: Show croit's id of the network
  ansible.builtin.debug:
    msg: "Network {{ public_net.network.ip }}/{{ public_net.network.netmask }} has id {{ public_net.network.id }}"

- name: PXE boot network with a DHCP pool
  croit.ceph.network:
    cidr: 192.168.100.0/24
    type: croit
    gateway: 192.168.100.1
    dhcp_pool_start: 192.168.100.100
    dhcp_pool_end: 192.168.100.200

- name: Remove the DHCP pool again
  croit.ceph.network:
    cidr: 192.168.100.0/24
    dhcp_pool_start: ""
    dhcp_pool_end: ""

- name: Remove a network
  croit.ceph.network:
    cidr: 172.16.0.0/16
    state: absent
"""

RETURN = r"""
network:
  description:
    - The network as croit reports it after the change (C(NetworkInfo) in the croit API).
    - In check mode, the network before the change. Empty when the network does not exist.
  returned: always
  type: dict
  contains:
    id:
      description: croit's id of the network.
      returned: when the network exists
      type: int
      sample: 4
    ip:
      description: An address in the network, not necessarily the network address; together with C(netmask) it gives the CIDR.
      returned: when the network exists
      type: str
      sample: 10.10.0.0
    netmask:
      description: The CIDR prefix length.
      returned: when the network exists
      type: int
      sample: 24
    type:
      description: What croit uses the network for.
      returned: when the network exists
      type: str
      sample: ceph_public
    description:
      description: Free-text notes.
      returned: when the network exists
      type: str
      sample: public network, bond0
    gateway:
      description: Default route installed on servers in this network, or null.
      returned: when the network exists
      type: str
      sample: 10.10.0.1
    mtu:
      description: Custom MTU, or null for the default of 1500.
      returned: when the network exists
      type: int
      sample: 9000
    poolStart:
      description: First address of the DHCP pool, or null.
      returned: when the network exists
      type: str
      sample: 192.168.100.100
    poolEnd:
      description: Last address of the DHCP pool, or null.
      returned: when the network exists
      type: str
      sample: 192.168.100.200
"""

from ansible.module_utils.common.text.converters import to_text

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.ip import ip_address, ip_interface, ip_network
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

DEFAULT_MTU = 1500
DEFAULT_TYPE = "other"

# Ansible option -> croit API field.
FIELDS = dict(
    type="type",
    description="description",
    gateway="gateway",
    mtu="mtu",
    dhcp_pool_start="poolStart",
    dhcp_pool_end="poolEnd",
)


def network_of(item):
    """The network a NetworkInfo describes, or None if croit's row is unusable."""
    try:
        return ip_network(u"%s/%s" % (to_text(item.get("ip")), item.get("netmask")))
    except ValueError:
        return None


def norm_ip(value):
    """Canonical text of an address; '' and None mean unset."""
    if value in (None, ""):
        return None
    return str(ip_address(to_text(value)))


def normalised(item):
    """A NetworkInfo's managed fields, canonicalised for comparison and diffs."""
    if not item:
        return {}
    view = dict(
        type=item.get("type") or DEFAULT_TYPE,
        description=item.get("description") or "",
        mtu=item.get("mtu") or DEFAULT_MTU,
    )
    for opt in ("gateway", "dhcp_pool_start", "dhcp_pool_end"):
        try:
            view[opt] = norm_ip(item.get(FIELDS[opt]))
        except ValueError:
            view[opt] = item.get(FIELDS[opt])
    return view


class NetworkModule(CroitModule):
    def __init__(self):
        super(NetworkModule, self).__init__(
            dict(
                cidr=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                type=dict(type="str", choices=["other", "ceph_public", "ceph_internal", "croit", "ipmi"]),
                description=dict(type="str"),
                gateway=dict(type="str"),
                mtu=dict(type="int"),
                dhcp_pool_start=dict(type="str"),
                dhcp_pool_end=dict(type="str"),
            ),
            wait=False,
            warnings=False,
            required_together=[("dhcp_pool_start", "dhcp_pool_end")],
        )

    def parse_cidr(self):
        try:
            interface = ip_interface(to_text(self.params["cidr"]))
        except ValueError as e:
            self.module.fail_json(msg="cidr: %s" % e)
        if "/" not in self.params["cidr"]:
            self.module.fail_json(msg="cidr %r needs a prefix length, such as 10.0.0.0/24" % self.params["cidr"])
        return interface

    def desired(self, network):
        """Managed options the user set, canonicalised and validated against ``network``."""
        p = self.params
        desired = {}
        for opt in FIELDS:
            if p[opt] is not None:
                desired[opt] = p[opt]
        if "description" in desired:
            desired["description"] = desired["description"] or ""
        for opt in ("gateway", "dhcp_pool_start", "dhcp_pool_end"):
            if opt not in desired:
                continue
            try:
                desired[opt] = norm_ip(desired[opt])
            except ValueError as e:
                self.module.fail_json(msg="%s: %s" % (opt, e))
            if desired[opt] is not None and ip_address(desired[opt]) not in network:
                self.module.fail_json(msg="%s %s is not inside %s" % (opt, desired[opt], network))
        if (desired.get("dhcp_pool_start") is None) != (desired.get("dhcp_pool_end") is None):
            self.module.fail_json(msg="dhcp_pool_start and dhcp_pool_end must both be set or both be empty")
        if desired.get("mtu") is not None and desired["mtu"] <= 0:
            self.module.fail_json(msg="mtu must be positive")
        return desired

    @staticmethod
    def request_body(interface, view):
        """The full NetworkUpdateRequest for a canonical view."""
        return dict(
            ip=str(interface.ip),
            netmask=interface.network.prefixlen,
            type=view["type"],
            description=view["description"],
            gateway=view["gateway"],
            mtu=None if view["mtu"] == DEFAULT_MTU else view["mtu"],
            poolStart=view["dhcp_pool_start"],
            poolEnd=view["dhcp_pool_end"],
        )

    def find(self, network):
        for item in self.get_list("/networks"):
            if network_of(item) == network:
                return item
        return None

    def run(self):
        p = self.params
        interface = self.parse_cidr()
        network = interface.network
        current = self.find(network)

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, network={})
            if not self.check_mode:
                self.write("DELETE", path_join("networks", current["id"]))
            self.exit(changed=True, before=normalised(current), after={}, network={})

        desired = self.desired(network)
        if current is None:
            after = dict(
                type=DEFAULT_TYPE, description="", mtu=DEFAULT_MTU, gateway=None, dhcp_pool_start=None, dhcp_pool_end=None
            )
            after.update(desired)
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, network={})
            created = self.write("POST", "/networks", body=self.request_body(interface, after))
            self.exit(changed=True, before={}, after=after, network=created or self.find(network) or {})

        before = normalised(current)
        after = dict(before)
        after.update(desired)
        if after == before:
            self.exit(changed=False, before=before, after=after, network=current)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, network=current)
        # Keep croit's stored address for the network rather than replacing it with the CIDR's.
        stored = ip_interface(u"%s/%s" % (to_text(current["ip"]), current["netmask"]))
        self.write("PUT", path_join("networks", current["id"]), body=self.request_body(stored, after))
        self.exit(changed=True, before=before, after=after, network=self.find(network) or {})


def main():
    NetworkModule().run()


if __name__ == "__main__":
    main()
