# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stateful fake of croit's iSCSI gateway endpoints (test-only)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit

MIB = 1024 * 1024
IQN = "iqn.2001-07.com.ceph:1700000000000"
SERVERS = [
    dict(id=1, hostname="storage-1", ip="10.0.0.1"),
    dict(id=2, hostname="storage-2", ip="10.0.0.2"),
    dict(id=3, hostname="storage-3", ip="10.0.0.3"),
]


def warning(token, text):
    return 400, dict(code=400, message=text, ignorableWarning=dict(token=token, warningText=text, affirmativeLabel="Yes"))


class IscsiCluster(FakeCroit):
    """In-memory iSCSI gateway, its initiators, groups, exported disks and RBD images."""

    def __init__(self, gateway=False, masked_passwords=False):
        super(IscsiCluster, self).__init__()
        self.service = None
        self.portals = []
        self.selected_target = None
        self.targets = []
        self.clients = {}  # iqn -> dict(username, password, group, own=[keys])
        self.groups = {}  # name -> dict(members=[iqns], luns=[keys])
        self.disks = {}  # "pool/image" -> wwn
        self.images = {}  # "pool/image" -> size in bytes
        self.masked_passwords = masked_passwords
        self._wwn = 0
        self.serve_tasks()
        self.reply("GET", "/servers", 200, SERVERS)
        r = self.route
        r("GET", "/gateways/iscsi", lambda call: (200, dict(data=self.service_rows(), total=len(self.service_rows()), after=0)))
        r("GET", "/gateways/iscsi/servers", lambda call: (200, [dict(p, serviceId=7) for p in self.portals]))
        r("GET", "/gateways/iscsi/disks", lambda call: (200, self.disk_rows()))
        r("GET", "/gateways/iscsi/groups", lambda call: (200, self.group_rows()))
        r("GET", "/gateways/iscsi/hosts", lambda call: (200, self.host_rows()))
        r("POST", "/services/iscsi", self.create_gateway)
        base = r"/services/iscsi/(?P<sid>\d+)"
        r("GET", base, lambda call, sid: (200, self.config()))
        r("PATCH", base, self.patch_gateway)
        r("POST", base, self.add_portal)
        r("DELETE", base, self.delete_gateway)
        r("DELETE", base + r"/servers/(?P<hostname>[^/]+)", self.remove_portal)
        r("PUT", base + r"/target", self.set_target)
        r("PUT", base + r"/clients/(?P<name>[^/]+)", self.create_client)
        r("PATCH", base + r"/clients/(?P<name>[^/]+)", self.patch_client)
        r("DELETE", base + r"/clients/(?P<name>[^/]+)", self.delete_client)
        r("PUT", base + r"/clients/(?P<name>[^/]+)/disks", self.map_client_disks)
        r("DELETE", base + r"/clients/(?P<name>[^/]+)/disks", self.unmap_client_disk)
        r("PUT", base + r"/groups/(?P<group>[^/]+)", self.create_group)
        r("DELETE", base + r"/groups/(?P<group>[^/]+)", self.delete_group)
        r("PUT", base + r"/groups/(?P<group>[^/]+)/hosts", self.add_hosts)
        r("DELETE", base + r"/groups/(?P<group>[^/]+)/hosts", self.remove_hosts)
        r("PUT", base + r"/groups/(?P<group>[^/]+)/hosts/(?P<host>[^/]+)", self.add_host)
        r("DELETE", base + r"/groups/(?P<group>[^/]+)/hosts/(?P<host>[^/]+)", self.remove_host)
        r("PUT", base + r"/groups/(?P<group>[^/]+)/disks", self.map_group_disks)
        r("DELETE", base + r"/groups/(?P<group>[^/]+)/disks", self.unmap_group_disk)
        r("PATCH", base + r"/disks/(?P<wwn>[^/]+)", self.resize_disk)
        r("DELETE", base + r"/disks/(?P<wwn>[^/]+)", self.delete_disk)
        r("GET", r"/pools/(?P<pool>[^/]+)/rbds/(?P<rbd>[^/]+)", self.get_image)
        if gateway:
            self.service = dict(serviceId=7, description="")
            self.portals = [dict(serverId=1, hostname="storage-1", ip="10.10.0.11", healthy=True)]
            self.targets = [IQN]
            self.selected_target = IQN

    # Serialisation ----------------------------------------------------------

    def service_rows(self):
        return [copy.deepcopy(self.service)] if self.service else []

    def lun(self, key):
        pool, image = key.split("/", 1)
        return dict(pool=pool, image=image, wwn=self.disks[key])

    def client_luns(self, iqn):
        client = self.clients[iqn]
        keys = list(client["own"])
        if client["group"]:
            keys += [k for k in self.groups[client["group"]]["luns"] if k not in keys]
        return keys

    def config(self):
        return dict(
            iqn=self.selected_target or "",
            selectedTarget=self.selected_target or "",
            targets=list(self.targets),
            gatewayVersion=1,
            gateways=[dict(name=p["hostname"], ip=p["ip"]) for p in self.portals],
            disks=[self.lun(k) for k in sorted(self.disks)],
            clients=[
                dict(
                    name=iqn,
                    username=c["username"],
                    password="(masked)" if self.masked_passwords else c["password"],
                    group=c["group"] or "",
                    luns=[self.lun(k) for k in self.client_luns(iqn)],
                )
                for iqn, c in sorted(self.clients.items())
            ],
            groups=[
                dict(name=name, members=list(g["members"]), luns=[self.lun(k) for k in g["luns"]])
                for name, g in sorted(self.groups.items())
            ],
        )

    def disk_rows(self):
        rows = []
        for key in sorted(self.disks):
            row = dict(self.lun(key), serviceId=7, lunId=None)
            row["hosts"] = [iqn for iqn in self.clients if key in self.client_luns(iqn)]
            row["groups"] = [name for name, g in self.groups.items() if key in g["luns"]]
            rows.append(row)
        return rows

    def group_rows(self):
        return [dict(serviceId=7, group=name, members=list(g["members"]), luns=[]) for name, g in self.groups.items()]

    def host_rows(self):
        return [
            dict(serviceId=7, iqn=iqn, username=c["username"], password=c["password"], group=c["group"] or "", luns=[])
            for iqn, c in self.clients.items()
        ]

    # Gateway ------------------------------------------------------------------

    def create_gateway(self, call):
        if self.service:
            return 400, dict(code=400, message="the cluster already has an iSCSI gateway")
        self.service = dict(serviceId=7, description=call.body.get("description") or "")
        for entry in call.body["servers"]:
            host = [s for s in SERVERS if s["id"] == entry["serverId"]][0]
            self.portals.append(dict(serverId=host["id"], hostname=host["hostname"], ip=entry["ip"], healthy=True))
        self.targets = [IQN]
        self.selected_target = IQN
        return 200, self.new_task("Create iSCSI gateway")

    def patch_gateway(self, call, sid):
        if "description" in call.body:
            self.service["description"] = call.body["description"] or ""
        return 204, None

    def add_portal(self, call, sid):
        host = [s for s in SERVERS if s["id"] == call.body["serverId"]][0]
        self.portals.append(dict(serverId=host["id"], hostname=host["hostname"], ip=call.body["ip"], healthy=True))
        return 200, self.new_task("Add iSCSI gateway", host["hostname"])

    def remove_portal(self, call, sid, hostname):
        self.portals = [p for p in self.portals if p["hostname"] != hostname]
        return 200, self.new_task("Remove iSCSI gateway", hostname)

    def delete_gateway(self, call, sid):
        if call.query.get("ignoreWarning") != "del-gw":
            return warning("del-gw", "This removes every gateway of the target")
        self.service = None
        self.portals = []
        self.clients, self.groups, self.disks = {}, {}, {}
        self.selected_target, self.targets = None, []
        return 204, None

    def set_target(self, call, sid):
        if call.body not in self.targets and call.query.get("ignoreWarning") != "target":
            return warning("target", "The configuration does not carry this target")
        self.selected_target = call.body
        return 204, None

    # Clients --------------------------------------------------------------------

    def create_client(self, call, sid, name):
        body = call.body
        if not 8 <= len(body["username"]) <= 64 or not 12 <= len(body["password"]) <= 16:
            return 400, dict(code=400, message="invalid CHAP credential")
        self.clients[name] = dict(username=body["username"], password=body["password"], group=None, own=[])
        if body.get("group"):
            self.groups[body["group"]]["members"].append(name)
            self.clients[name]["group"] = body["group"]
        return 204, None

    def patch_client(self, call, sid, name):
        for field in ("username", "password"):
            if call.body.get(field) is not None:
                self.clients[name][field] = call.body[field]
        return 204, None

    def delete_client(self, call, sid, name):
        client = self.clients.pop(name)
        if client["group"]:
            self.groups[client["group"]]["members"].remove(name)
        return 204, None

    def export(self, entry):
        key = "%s/%s" % (entry["pool"], entry["name"])
        if key not in self.images:
            if entry.get("size") is None:
                return None, (400, dict(code=400, message="RBD image %s does not exist" % key))
            self.images[key] = entry["size"] * MIB
        if key not in self.disks:
            self._wwn += 1
            self.disks[key] = "wwn-%04d" % self._wwn
        return key, None

    def map_client_disks(self, call, sid, name):
        for entry in call.body:
            key, error = self.export(entry)
            if error:
                return error
            if key not in self.clients[name]["own"]:
                self.clients[name]["own"].append(key)
        return 204, None

    def unmap_client_disk(self, call, sid, name):
        key = "%s/%s" % (call.body["pool"], call.body["name"])
        self.clients[name]["own"].remove(key)
        return 204, None

    # Groups -----------------------------------------------------------------------

    def create_group(self, call, sid, group):
        self.groups.setdefault(group, dict(members=[], luns=[]))
        return 204, None

    def delete_group(self, call, sid, group):
        if call.query.get("ignoreWarning") != "del-group":
            return warning("del-group", "Its hosts keep the group's disks")
        for iqn in self.groups.pop(group)["members"]:
            self.clients[iqn]["group"] = None
        return 204, None

    def add_host(self, call, sid, group, host):
        client = self.clients[host]
        if client["own"]:
            return 400, dict(code=400, message="initiator %s has mappings of its own" % host)
        client["group"] = group
        self.groups[group]["members"].append(host)
        return 204, None

    def remove_host(self, call, sid, group, host):
        if call.query.get("ignoreWarning") != "rm-host":
            return warning("rm-host", "The host keeps the group's disks")
        self.groups[group]["members"].remove(host)
        self.clients[host]["group"] = None
        return 204, None

    def add_hosts(self, call, sid, group):
        for host in call.body:
            status, body = self.add_host(call, sid, group, host)
            if status != 204:
                return status, body
        return 204, None

    def remove_hosts(self, call, sid, group):
        for host in call.body:
            status, body = self.remove_host(call, sid, group, host)
            if status != 204:
                return status, body
        return 204, None

    def map_group_disks(self, call, sid, group):
        for entry in call.body:
            key, error = self.export(entry)
            if error:
                return error
            if key not in self.groups[group]["luns"]:
                self.groups[group]["luns"].append(key)
        return 204, None

    def unmap_group_disk(self, call, sid, group):
        self.groups[group]["luns"].remove("%s/%s" % (call.body["pool"], call.body["name"]))
        return 204, None

    # Disks ---------------------------------------------------------------------------

    def key_for(self, wwn):
        return [k for k, w in self.disks.items() if w == wwn][0]

    def resize_disk(self, call, sid, wwn):
        key = self.key_for(wwn)
        size = call.body["size"] * MIB
        if size < self.images[key]:
            return 400, dict(code=400, message="ceph-iscsi only grows images")
        self.images[key] = size
        return 204, None

    def delete_disk(self, call, sid, wwn):
        key = self.key_for(wwn)
        assert call.body["pool"] + "/" + call.body["image"] == key
        del self.disks[key]
        for client in self.clients.values():
            if key in client["own"]:
                client["own"].remove(key)
        for g in self.groups.values():
            if key in g["luns"]:
                g["luns"].remove(key)
        if call.body.get("deleteData"):
            del self.images[key]
        return 200, self.new_task("Delete iSCSI disk", key)

    def get_image(self, call, pool, rbd):
        key = "%s/%s" % (pool, rbd)
        if key not in self.images:
            return 404, dict(code=404, message="Not Found")
        return 200, dict(name=rbd, pool=pool, size=self.images[key])
