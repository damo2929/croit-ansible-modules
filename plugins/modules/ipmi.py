#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /ipmi
# croit-api: GET /ipmi/poll-state
# croit-api: POST /ipmi/add
# croit-api: DELETE /ipmi/{ipmiId}
# croit-api: POST /ipmi/{ipmiId}/power-on
# croit-api: POST /ipmi/{ipmiId}/power-off
# croit-api: POST /ipmi/{ipmiId}/power-cycle
# croit-api: POST /ipmi/{ipmiId}/reboot-to-bios
# croit-api: POST /ipmi/{ipmiId}/identify
# croit-api: POST /ipmi/{ipmiId}/ipmi-controller-reset
# croit-api: POST /ipmi/{ipmiId}/initialize
# croit-api: GET /servers

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: ipmi
short_description: Manage IPMI devices and server power through croit
version_added: 0.1.0
description:
  - Registers and removes croit's record of a server's BMC (IPMI device), sets the server's power state,
    and runs one-shot IPMI actions such as identify or power cycle.
  - O(power) is declarative and compared with the power state the BMC last reported.
  - O(action) runs a one-shot action. It always reports a change and is skipped in check mode.
  - Actions that cut a running server's power (O(power=off), O(action=power_cycle), O(action=reboot_to_bios))
    need O(confirm_action=true), because the operating system is not asked to shut down first.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
seealso:
  - module: croit.ceph.server
    description: Reboot or shut down a node through croit, behind ceph's safety checks.
  - module: croit.ceph.server_info
    description: Read servers and their BMCs.
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
options:
  server:
    description:
      - The server whose BMC to act on, by hostname or numeric id.
      - Exactly one of O(server), O(ip) and O(ipmi_id) is required.
    type: str
  ip:
    description:
      - Address the BMC answers on. Needed to register a BMC croit does not know yet.
    type: str
  ipmi_id:
    description:
      - croit's numeric id of the IPMI device.
    type: int
  state:
    description:
      - V(present) makes sure croit knows the BMC, registering it with O(ip), O(username) and O(password) when
        it does not.
      - V(absent) removes croit's record of the BMC. Nothing is done to the device itself, and croit's DHCP server
        adds a BMC on its network back on its next lease.
    type: str
    choices: [present, absent]
    default: present
  power:
    description:
      - Desired power state of the server. V(off) cuts the power without shutting the operating system down
        and needs O(confirm_action=true).
      - V(on) PXE-boots the server with the image croit has configured for it.
    type: str
    choices: ['on', 'off']
  action:
    description:
      - One-shot action. Always reports a change; skipped in check mode.
      - V(identify) blinks the chassis LED for a few minutes.
      - V(power_cycle) cuts the power and PXE-boots the server again (needs O(confirm_action=true)).
      - V(reboot_to_bios) power-cycles into the firmware setup (needs O(confirm_action=true)).
      - V(controller_reset) restarts the BMC itself; the server keeps running.
      - V(initialize) sets PXE as boot device, powers the server on and, with O(keep_admin_password=false),
        sets croit's IPMI password on the device.
    type: str
    choices: [identify, power_cycle, reboot_to_bios, controller_reset, initialize]
  confirm_action:
    description:
      - Must be V(true) for O(power=off), O(action=power_cycle) and O(action=reboot_to_bios).
    type: bool
    default: false
  username:
    description:
      - BMC user, used only when registering the device or with O(action=initialize).
    type: str
  password:
    description:
      - BMC password, used only when registering the device or with O(action=initialize). It cannot be read back,
        so it is never compared.
    type: str
  keep_admin_password:
    description:
      - V(true) keeps the device's own ADMIN password; V(false) lets croit set its IPMI password on the device.
    type: bool
    default: true
notes:
  - O(power=off), O(action=power_cycle) and O(action=reboot_to_bios) cut a running server's power without
    shutting the OS down, and bypass ceph's safety checks; prefer M(croit.ceph.server) with O(croit.ceph.server#module:action=reboot)
    for planned maintenance. They are refused without O(confirm_action=true), also in check mode.
  - The BMC password is never returned by croit and is not compared; it is only sent when registering or
    initialising a device.
  - croit polls the BMCs every few seconds, so a power change can take a few seconds to show. With O(wait=true)
    the module waits until the BMC reports the new power state.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Make sure a node is powered on
  croit.ceph.ipmi:
    server: node7
    power: "on"
  register: bmc

- name: Show the BMC's address
  ansible.builtin.debug:
    msg: "BMC of node7 is at {{ bmc.ipmi.ip }}"

- name: Blink the LED of a node to find it in the rack
  croit.ceph.ipmi:
    server: node7
    action: identify

- name: Hard power cycle a hung node (cuts power without shutting down)
  croit.ceph.ipmi:
    server: node7
    action: power_cycle
    confirm_action: true

- name: Register a BMC that is not on croit's DHCP network
  croit.ceph.ipmi:
    ip: 10.10.0.27
    username: ADMIN
    password: "{{ vault_bmc_password }}"

- name: Forget a BMC record (the device itself is not touched)
  croit.ceph.ipmi:
    ip: 10.10.0.27
    state: absent
"""

RETURN = r"""
ipmi:
  description:
    - The IPMI device as croit reports it after the change (C(IpmiDevice) in the croit API).
    - Before the change in check mode; empty when the device does not exist.
  returned: always
  type: dict
  contains:
    id:
      description: croit's numeric IPMI device id.
      returned: when the device exists
      type: int
      sample: 5
    ip:
      description: Address of the BMC.
      returned: when the device exists
      type: str
      sample: 10.10.0.27
    mac:
      description: MAC address of the BMC.
      returned: when the device exists
      type: str
      sample: "0c:c4:7a:11:22:33"
    server:
      description: The node this BMC belongs to (C(ServerInfo) in the croit API), or null when croit does not know.
      returned: when the device exists
      type: dict
      sample: {id: 7, hostname: node7}
    state:
      description: What the BMC last reported (C(IpmiDeviceState) in the croit API), including C(power) (true when on); null when it did not answer.
      returned: when the device exists
      type: dict
      sample: {power: true}
task:
  description: The croit background task O(action=initialize) ran as (C(TaskResponse) in the croit API).
  returned: when a task ran
  type: dict
  contains:
    id:
      description: Task id, usable with M(croit.ceph.task) and M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as croit's task list shows it.
      returned: always
      type: str
      sample: Update server
    state:
      description: V(WAITING), V(RUNNING), V(FINISHED), V(FAILED) or V(CANCELED).
      returned: always
      type: str
      sample: FINISHED
    done:
      description: Whether the task has ended.
      returned: always
      type: bool
      sample: true
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: "done"
"""

import time

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

ACTIONS = dict(
    identify="identify",
    power_cycle="power-cycle",
    reboot_to_bios="reboot-to-bios",
    controller_reset="ipmi-controller-reset",
    initialize="initialize",
)
NEEDS_CONFIRM = ("power_cycle", "reboot_to_bios")
POLL_INTERVAL = 5


def power_of(device):
    state = (device or {}).get("state")
    if not state or state.get("power") is None:
        return None
    return "on" if state["power"] else "off"


class IpmiModule(CroitModule):
    def __init__(self):
        super(IpmiModule, self).__init__(
            dict(
                server=dict(type="str"),
                ip=dict(type="str"),
                ipmi_id=dict(type="int"),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                power=dict(type="str", choices=["on", "off"]),
                action=dict(type="str", choices=list(ACTIONS)),
                confirm_action=dict(type="bool", default=False),
                username=dict(type="str"),
                password=dict(type="str", no_log=True),
                keep_admin_password=dict(type="bool", default=True, no_log=False),
            ),
            warnings=False,
            mutually_exclusive=[("server", "ip", "ipmi_id"), ("power", "action")],
            required_one_of=[("server", "ip", "ipmi_id")],
        )

    def find(self):
        p = self.params
        devices = self.get_list("/ipmi")
        if p["ipmi_id"] is not None:
            return next((d for d in devices if d.get("id") == p["ipmi_id"]), None)
        if p["ip"] is not None:
            return next((d for d in devices if d.get("ip") == p["ip"]), None)
        server = require_server(self, p["server"])
        return next((d for d in devices if (d.get("server") or {}).get("id") == server["id"]), None)

    def access(self):
        p = self.params
        if p["username"] is None or p["password"] is None:
            return None
        return dict(username=p["username"], password=p["password"], keepAdminPassword=p["keep_admin_password"])

    def polled_power(self, device):
        power = power_of(device)
        if power is None:
            states = self.get("/ipmi/poll-state", query=dict(ipmiIds=[device["id"]])) or {}
            entry = states.get(str(device["id"])) or states.get(device["id"]) or {}
            power = power_of(entry)
        return power

    def wait_power(self, device, wanted):
        deadline = time.monotonic() + self.params["wait_timeout"]
        while True:
            states = self.get("/ipmi/poll-state", query=dict(ipmiIds=[device["id"]])) or {}
            entry = states.get(str(device["id"])) or states.get(device["id"]) or {}
            if power_of(entry) == wanted:
                return
            if time.monotonic() >= deadline:
                self.module.fail_json(msg="Timed out waiting for the BMC to report power %s" % wanted, ipmi=device)
            time.sleep(POLL_INTERVAL)

    def run(self):
        p = self.params
        device = self.find()

        if p["state"] == "absent":
            if p["power"] or p["action"]:
                self.module.fail_json(msg="power and action cannot be used with state=absent")
            if device is None:
                self.exit(changed=False, ipmi={})
            if not self.check_mode:
                self.write("DELETE", path_join("ipmi", device["id"]))
            self.exit(changed=True, before=dict(id=device["id"], ip=device.get("ip")), after={}, ipmi={})

        if (p["power"] == "off" or p["action"] in NEEDS_CONFIRM) and not p["confirm_action"]:
            self.module.fail_json(
                msg="Cutting a server's power needs confirm_action=true; the operating system is not shut down first"
            )

        changed = False
        before, after = {}, {}
        if device is None:
            if p["ip"] is None or self.access() is None:
                self.module.fail_json(
                    msg="croit knows no IPMI device for %s; give ip, username and password to register one"
                    % (p["server"] or p["ipmi_id"])
                )
            changed = True
            after = dict(ip=p["ip"])
            if self.check_mode:
                if p["power"] or p["action"]:
                    after["power"] = p["power"]
                self.exit(changed=True, before={}, after=after, ipmi={})
            self.write("POST", "/ipmi/add", body=dict(ip=p["ip"], access=self.access()))
            device = self.find()
            if device is None:
                self.module.fail_json(msg="croit accepted IPMI device %s but does not list it" % p["ip"])
        else:
            before = dict(id=device["id"], ip=device.get("ip"))
            after = dict(before)

        result = dict(ipmi=device)
        if p["power"] is not None:
            current = self.polled_power(device)
            if current is None:
                self.module.fail_json(msg="The BMC at %s did not report its power state" % device.get("ip"), ipmi=device)
            before["power"], after["power"] = current, p["power"]
            if current != p["power"]:
                changed = True
                if not self.check_mode:
                    self.write("POST", path_join("ipmi", device["id"], "power-%s" % p["power"]))
                    if p["wait"]:
                        self.wait_power(device, p["power"])

        if p["action"] is not None:
            changed = True
            after["action"] = p["action"]
            if not self.check_mode:
                body = self.access() if p["action"] == "initialize" else None
                task = self.handle_task(self.write("POST", path_join("ipmi", device["id"], ACTIONS[p["action"]]), body=body))
                if task is not None:
                    result["task"] = task

        if changed and not self.check_mode:
            result["ipmi"] = self.find() or device
        self.exit(changed=changed, before=before, after=after, **result)


def main():
    IpmiModule().run()


if __name__ == "__main__":
    main()
