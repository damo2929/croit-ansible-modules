# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stateful fake of croit's server, NIC, VLAN and disk endpoints (test-only)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit


def server(sid, hostname, ip="10.0.0.%d", **extra):
    data = dict(
        id=sid,
        hostname=hostname,
        ip=ip % sid if "%d" in ip else ip,
        ips=[ip % sid if "%d" in ip else ip],
        image="img-%d" % sid,
        imageDescription="croit image",
        notes=None,
        nrHugepages=0,
        state="running",
        isJoined=True,
        macs=[],
        lastSeen=0,
        health={},
        machineId="m%d" % sid,
        bootMode="pxe",
    )
    data.update(extra)
    return data


def nic(nid, sid, name, mac, ip=None, ip6=None, **extra):
    data = dict(
        id=nid,
        server=sid,
        name=name,
        linuxName=name,
        mac=mac,
        ip=ip,
        ip6=ip6,
        notes=None,
        type="normal",
        bond=None,
        bondType=None,
        bondPrimary=None,
        bondedNics=None,
        isManaged=True,
        isPresent=True,
        vlans=[],
        speed=10000,
        lastSeen=0,
        serverLastSeen=0,
        lldp=[],
    )
    data.update(extra)
    return data


def disk(did, sid, hostname, role="unassigned", device_class="ssd", **extra):
    data = dict(
        id=did,
        server=sid,
        hostname=hostname,
        role=role,
        deviceClass=device_class,
        size=1024 ** 4,
        serial="S%d" % did,
        path="/dev/sd%s" % chr(ord("a") + did),
        missing=False,
    )
    data.update(extra)
    return data


class ServerCluster(FakeCroit):
    def __init__(self, servers=None, nics=None, disks=None):
        super(ServerCluster, self).__init__()
        self.servers = dict((s["id"], s) for s in (servers or []))
        self.nics = dict((n["id"], n) for n in (nics or []))
        self.disks = list(disks or [])
        self.next_nic = 100
        self.next_vlan = 500
        self.serve_tasks()
        self.route("GET", "/servers", lambda call: (200, [copy.deepcopy(s) for s in self.servers.values()]))
        self.route("PATCH", r"/servers/(?P<sid>\d+)", self.patch_server)
        self.route("DELETE", r"/servers/(?P<sid>\d+)", self.delete_server)
        for action in ("reboot", "shutdown"):
            self.route("POST", r"/servers/(?P<sid>\d+)/%s" % action, self.task_action(action))
        self.route("POST", r"/servers/(?P<sid>\d+)/redetect", lambda call, sid: (204, None))
        self.route("GET", "/servers/nics", lambda call: (200, [copy.deepcopy(n) for n in self.nics.values()]))
        self.route("GET", r"/servers/(?P<sid>\d+)/nics", self.list_nics)
        self.route("POST", r"/servers/(?P<sid>\d+)/nics/bonds", self.create_bond)
        self.route("PATCH", r"/servers/(?P<sid>\d+)/nics/(?P<nid>\d+)", self.patch_nic)
        self.route("DELETE", r"/servers/(?P<sid>\d+)/nics/(?P<nid>\d+)", self.delete_nic)
        self.route("GET", r"/servers/(?P<sid>\d+)/nics/(?P<nid>\d+)/vlans", self.list_vlans)
        self.route("POST", r"/servers/(?P<sid>\d+)/nics/(?P<nid>\d+)/vlans", self.create_vlan)
        self.route("PATCH", r"/servers/(?P<sid>\d+)/nics/(?P<nid>\d+)/vlans/(?P<vid>\d+)", self.patch_vlan)
        self.route("DELETE", r"/servers/(?P<sid>\d+)/nics/(?P<nid>\d+)/vlans/(?P<vid>\d+)", self.delete_vlan)
        self.route("GET", "/disks", lambda call: (200, copy.deepcopy(self.disks)))
        self.route(
            "GET",
            r"/servers/(?P<sid>\d+)/disks",
            lambda call, sid: (200, [copy.deepcopy(d) for d in self.disks if d["server"] == int(sid)]),
        )

    # Servers --------------------------------------------------------------

    def patch_server(self, call, sid):
        s = self.servers[int(sid)]
        body = call.body
        if body.get("ip") is not None and body["ip"] not in s["ips"]:
            return 400, dict(code=400, message="IP is not assigned to one of the server's interfaces")
        for key, value in body.items():
            if value is not None:
                s[key] = value
        return 200, self.new_task("Update server", s["hostname"])

    def delete_server(self, call, sid):
        del self.servers[int(sid)]
        return 204, None

    def task_action(self, action):
        def handler(call, sid):
            return 200, self.new_task(action.capitalize(), self.servers[int(sid)]["hostname"])

        return handler

    # NICs -----------------------------------------------------------------

    def list_nics(self, call, sid):
        return 200, [copy.deepcopy(n) for n in self.nics.values() if n["server"] == int(sid)]

    def create_bond(self, call, sid):
        body = call.body
        self.next_nic += 1
        bond = nic(
            self.next_nic,
            int(sid),
            body["name"],
            "02:00:00:00:00:%02x" % self.next_nic,
            type="bond",
            bondType="active_passive" if body.get("activePassive") else "lacp",
            bondPrimary=body.get("primary"),
            bondedNics=list(body["nics"]),
        )
        self.nics[bond["id"]] = bond
        for member in body["nics"]:
            self.nics[member]["bond"] = bond["id"]
        return 204, None

    def patch_nic(self, call, sid, nid):
        n = self.nics[int(nid)]
        body = dict(call.body)
        bond = body.pop("bond", None)
        if bond:
            if bond.get("nics") is not None:
                for member in n["bondedNics"] or []:
                    self.nics[member]["bond"] = None
                n["bondedNics"] = list(bond["nics"])
                for member in bond["nics"]:
                    self.nics[member]["bond"] = n["id"]
            if bond.get("activePassive") is not None:
                n["bondType"] = "active_passive" if bond["activePassive"] else "lacp"
            if "primary" in bond:
                n["bondPrimary"] = bond["primary"]
        for key, value in body.items():
            if value is None:
                continue
            n[key] = value or None  # blank string clears
        return 204, None

    def delete_nic(self, call, sid, nid):
        n = self.nics.pop(int(nid))
        for member in n.get("bondedNics") or []:
            self.nics[member]["bond"] = None
        return 204, None

    # VLANs ----------------------------------------------------------------

    def list_vlans(self, call, sid, nid):
        return 200, copy.deepcopy(self.nics[int(nid)]["vlans"])

    def create_vlan(self, call, sid, nid):
        body = call.body
        self.next_vlan += 1
        self.nics[int(nid)]["vlans"].append(
            dict(id=self.next_vlan, nic=int(nid), vlan=body["vlan"], ip=body.get("ip") or None, ip6=body.get("ip6") or None)
        )
        return 204, None

    def _vlan(self, nid, vid):
        for vlan in self.nics[int(nid)]["vlans"]:
            if vlan["id"] == int(vid):
                return vlan
        raise AssertionError("no vlan %s" % vid)

    def patch_vlan(self, call, sid, nid, vid):
        vlan = self._vlan(nid, vid)
        for key, value in call.body.items():
            if value is not None:
                vlan[key] = value or None
        return 204, None

    def delete_vlan(self, call, sid, nid, vid):
        vlan = self._vlan(nid, vid)
        self.nics[int(nid)]["vlans"].remove(vlan)
        return 204, None
