# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""In-memory croit servers, disks, CRUSH OSDs and services, for the osd and service module tests."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit

SERVERS = [dict(id=1, hostname="node1"), dict(id=2, hostname="node2")]


def disk(disk_id, server, path, serial, role="unassigned", osd_id=None, wwn=None, **extra):
    d = dict(
        id=disk_id,
        server=server,
        hostname="node%d" % server,
        path=path,
        pathRaw=path,
        pathFormatted=path,
        serial=serial,
        serials={"by-id": "ata-%s" % serial},
        wwn=wwn,
        wwns={},
        role=role,
        roleLabel=role.upper(),
        osdId=osd_id,
        encrypted=False,
        dbDisk=None,
        walDisk=None,
        missing=False,
    )
    d.update(extra)
    return d


def osd_node(osd_id, server, disk_id, reweight=1.0, status="UP", device_class="hdd"):
    return dict(
        id=osd_id,
        name="osd.%d" % osd_id,
        type="OSD",
        serverId=server,
        diskId=disk_id,
        reweight=reweight,
        status=status,
        deviceClass=device_class,
    )


def service(service_id, stype, server, running=True, multi=None):
    return dict(
        id=service_id,
        type=stype,
        name="ceph-%s@%s" % (stype, service_id),
        server=server if not multi else -1,
        serverHostname="node%d" % server if not multi else None,
        multiServer=list(multi or []),
        state="enabled",
        running=running,
        loading=False,
        hints=[],
    )


class Cluster(FakeCroit):
    """Applies OSD and service changes so modules converge on a re-run.

    ``lag`` makes start/stop take effect only after that many service/CRUSH reads,
    like croit queueing the change for croitd's next poll.
    """

    def __init__(self, disks=None, osds=None, services=None, lag=0):
        super(Cluster, self).__init__()
        self.disks = dict((d["id"], d) for d in (disks or []))
        self.osds = dict((n["id"], n) for n in (osds or []))
        self.services = dict((s["id"], s) for s in (services or []))
        self.pending = []
        self.lag = lag
        self.next_service = 100
        self.restarted = []
        self.serve_tasks()
        self.reply("GET", "/servers", 200, SERVERS)
        self.route("GET", r"/servers/(?P<sid>\d+)/disks", self.list_disks)
        self.route("GET", "/crush", self.crush)
        self.route("POST", "/disks/create-osds", self.create_osds)
        self.route("POST", "/disks/replace-osds", self.replace_osds)
        self.route("POST", r"/crush/osd/(?P<osd>\d+)/(?P<how>in|out)", self.in_out)
        self.route("POST", r"/services/osds/(?P<osd>\d+)/(?P<how>start|stop)", self.osd_start_stop)
        self.route("GET", "/services", self.list_services)
        self.route("POST", r"/servers/(?P<sid>\d+)/services/(?P<kind>mon|mds|rbd-mirror)", self.create_service)
        self.route("DELETE", r"/services/(?P<svc>\d+)", self.delete_service)
        self.route("POST", r"/services/(?P<svc>\d+)/(?P<how>start|stop)", self.service_start_stop)
        self.route("POST", "/services/restart", self.restart)
        self.route("POST", "/services/rolling-restart", self.rolling_restart)

    # Async start/stop -----------------------------------------------------

    def tick(self):
        still = []
        for countdown, apply in self.pending:
            if countdown <= 0:
                apply()
            else:
                still.append((countdown - 1, apply))
        self.pending = still

    def later(self, apply):
        if self.lag:
            self.pending.append((self.lag, apply))
        else:
            apply()

    # Disks and OSDs -------------------------------------------------------

    def list_disks(self, call, sid):
        return 200, [copy.deepcopy(d) for d in self.disks.values() if d["server"] == int(sid)]

    def crush(self, call):
        self.tick()
        return 200, dict(nodes=[copy.deepcopy(n) for n in self.osds.values()], stray=[])

    def create_osds(self, call):
        tasks = []
        for entry in call.body["osds"]:
            d = self.disks[entry["disk"]]
            assert d["role"] == "unassigned", "fake: croit refuses assigned disks"
            new_id = max(list(self.osds) + [-1]) + 1
            d.update(role="osd", osdId=new_id, encrypted=entry["encrypted"], dbDisk=entry.get("dbDisk"), walDisk=entry.get("walDisk"))
            self.osds[new_id] = osd_node(new_id, entry["server"], d["id"], device_class=entry.get("crushDeviceClass") or "hdd")
            tasks.append(self.new_task("Create OSD", "osd.%d" % new_id))
        return 200, tasks

    def replace_osds(self, call):
        for entry in call.body["osds"]:
            node = self.osds[entry["osd"]]
            old = self.disks.get(node["diskId"])
            if old:
                old.update(role="unassigned", osdId=None)
            new = self.disks[entry["disk"]]
            assert new["role"] == "unassigned"
            new.update(role="osd", osdId=entry["osd"])
            node.update(diskId=new["id"], serverId=new["server"])
        return 200, self.new_task("Replace OSDs")

    def in_out(self, call, osd, how):
        self.osds[int(osd)]["reweight"] = 1.0 if how == "in" else 0.0
        return 204, None

    def osd_start_stop(self, call, osd, how):
        node = self.osds[int(osd)]
        self.later(lambda: node.update(status="UP" if how == "start" else "DOWN"))
        return 204, None

    # Services ---------------------------------------------------------------

    def list_services(self, call):
        self.tick()
        return 200, [copy.deepcopy(s) for s in self.services.values()]

    def create_service(self, call, sid, kind):
        self.next_service += 1
        stype = kind.replace("-", "_")
        self.services[self.next_service] = service(self.next_service, stype, int(sid))
        if kind == "mon":
            assert set(call.body) == set(["ip", "diskId"])
            self.disks[call.body["diskId"]]["role"] = "mon"
        return 200, self.new_task("Create %s" % kind)

    def delete_service(self, call, svc):
        s = self.services[int(svc)]
        server = call.query.get("server")
        if server is not None and s["multiServer"]:
            s["multiServer"].remove(int(server))
            if s["multiServer"]:
                return 204, None
        if s["type"] == "mon" and len([x for x in self.services.values() if x["type"] == "mon"]) == 1:
            return 400, dict(code=400, message="The last monitor cannot be removed")
        del self.services[int(svc)]
        return 200, self.new_task("Delete service")

    def service_start_stop(self, call, svc, how):
        s = self.services[int(svc)]
        self.later(lambda: s.update(running=how == "start"))
        return 204, None

    def restart(self, call):
        self.restarted.append(("restart", call.body))
        return 204, None

    def rolling_restart(self, call):
        self.restarted.append(("rolling", call.body))
        return 200, self.new_task("Rolling restart")
