# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""In-memory fake of croit's NFS gateway and cephfs-guard endpoints, for unit tests."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit

SERVERS = [
    dict(id=1, hostname="node1", ip="10.0.0.1"),
    dict(id=2, hostname="node2", ip="10.0.0.2"),
    dict(id=3, hostname="node3", ip="10.0.0.3"),
]


def nics_for(server_id):
    return [
        dict(id=server_id * 10, server=server_id, name="eth0", linuxName="enp1s0", mac="aa:bb:cc:00:00:%02d" % server_id, vlans=[]),
        dict(
            id=server_id * 10 + 1,
            server=server_id,
            name="eth1",
            linuxName="enp2s0",
            mac="aa:bb:cc:00:01:%02d" % server_id,
            vlans=[dict(id=server_id * 100 + 50, nic=server_id * 10 + 1, vlan=50)],
        ),
    ]


class NfsCroit(FakeCroit):
    """Holds NFS clusters (with exports and HA) and cephfs-guard configs."""

    def __init__(self):
        super(NfsCroit, self).__init__()
        self.serve_tasks()
        self.clusters = {}
        self.guards = {}
        self.next_id = 40
        self.next_export = 0
        self.reply("GET", "/servers", 200, SERVERS)
        self.route("GET", r"/servers/(?P<sid>\d+)/nics", lambda call, sid: (200, nics_for(int(sid))))
        self.route("GET", "/gateways/nfs", self.list_clusters)
        self.route("GET", "/gateways/nfs/exports", self.list_all_exports)
        self.route("GET", "/gateways/nfs/servers", self.list_all_servers)
        self.route("POST", "/services/nfs-gateways", self.create_cluster)
        self.route("GET", r"/services/nfs-gateways/(?P<sid>\d+)", self.get_cluster)
        self.route("PATCH", r"/services/nfs-gateways/(?P<sid>\d+)", self.patch_cluster)
        self.route("PATCH", r"/services/nfs-gateways/(?P<sid>\d+)/implementation", self.switch)
        self.route("GET", r"/services/nfs-gateways/(?P<sid>\d+)/ha", self.get_ha)
        self.route("PUT", r"/services/nfs-gateways/(?P<sid>\d+)/ha", self.put_ha)
        self.route("DELETE", r"/services/nfs-gateways/(?P<sid>\d+)/ha", self.delete_ha)
        self.route("GET", r"/services/nfs-gateways/(?P<sid>\d+)/exports", self.list_exports)
        self.route("POST", r"/services/nfs-gateways/(?P<sid>\d+)/exports", self.create_export)
        self.route("PUT", r"/services/nfs-gateways/(?P<sid>\d+)/exports/(?P<eid>\d+)", self.put_export)
        self.route("DELETE", r"/services/nfs-gateways/(?P<sid>\d+)/exports/(?P<eid>\d+)", self.delete_export)
        self.route("DELETE", r"/services/(?P<sid>\d+)", self.delete_service)
        # cephfs-guard
        self.route("GET", "/services/cephfsguard", self.list_guards)
        self.route("POST", "/services/cephfsguard", self.create_guard)
        self.route("GET", r"/services/cephfsguard/(?P<cid>\d+)", lambda call, cid: (200, self.guard_view(self.guards[int(cid)])))
        self.route("PATCH", r"/services/cephfsguard/(?P<cid>\d+)", self.patch_guard)
        self.route("DELETE", r"/services/cephfsguard/(?P<cid>\d+)", self.delete_guard)
        self.route("GET", r"/services/cephfsguard/(?P<cid>\d+)/services", self.list_guard_services)
        self.route("POST", r"/services/cephfsguard/(?P<cid>\d+)/services", self.add_guard_services)
        self.route("PATCH", r"/services/cephfsguard/(?P<cid>\d+)/services/(?P<svc>\d+)", self.patch_guard_service)
        self.route("GET", r"/services/cephfsguard/(?P<cid>\d+)/webhooks", self.list_webhooks)
        self.route("POST", r"/services/cephfsguard/(?P<cid>\d+)/webhooks", self.add_webhook)
        self.route("PATCH", r"/services/cephfsguard/(?P<cid>\d+)/webhooks/(?P<wid>\d+)", self.patch_webhook)
        self.route("DELETE", r"/services/cephfsguard/(?P<cid>\d+)/webhooks/(?P<wid>\d+)", self.delete_webhook)
        incidents = [dict(id=1, volume="cephfs", state="NEW"), dict(id=2, volume="other", state="NEW")]
        self.reply("GET", "/services/cephfsguard/incidents", 200, incidents)

    # NFS ------------------------------------------------------------------

    def add_cluster(self, name, servers, implementation="ganesha", vips=None, interfaces=None):
        self.next_id += 1
        self.clusters[self.next_id] = dict(
            serviceId=self.next_id,
            description=name,
            implementation=implementation,
            servers=list(servers),
            exports=[],
            vips=list(vips or []),
            interfaces=list(interfaces or []),
        )
        return self.next_id

    def list_clusters(self, call):
        data = [dict(serviceId=c["serviceId"], description=c["description"], implementation=c["implementation"]) for c in self.clusters.values()]
        return 200, dict(data=data, total=len(data), after=0)

    def list_all_exports(self, call):
        data = [dict(e, accessJoined="") for c in self.clusters.values() for e in copy.deepcopy(c["exports"])]
        return 200, dict(data=data, total=len(data), after=0)

    def list_all_servers(self, call):
        data = [
            dict(serviceId=c["serviceId"], serverId=s, hostname="node%d" % s, ip="10.0.0.%d" % s, healthy=True)
            for c in self.clusters.values()
            for s in c["servers"]
        ]
        return 200, dict(data=data, total=len(data), after=0)

    def create_cluster(self, call):
        body = call.body
        sid = self.add_cluster(body["description"], body["servers"], body.get("implementation", "ganesha"))
        for export in body.get("exports") or []:
            self.create_export(call, str(sid), export)
        return 200, self.new_task("Create NFS cluster", body["description"])

    def get_cluster(self, call, sid):
        c = self.clusters.get(int(sid))
        if c is None:
            return 404, dict(code=404, message="Not Found")
        return 200, dict(servers=list(c["servers"]), exports=copy.deepcopy(c["exports"]), implementation=c["implementation"])

    def patch_cluster(self, call, sid):
        c = self.clusters[int(sid)]
        if call.body.get("servers") is not None:
            c["servers"] = list(call.body["servers"])
        if call.body.get("description") is not None:
            c["description"] = call.body["description"]
        return 204, None

    def switch(self, call, sid):
        self.clusters[int(sid)]["implementation"] = call.body["implementation"]
        return 204, None

    def get_ha(self, call, sid):
        c = self.clusters[int(sid)]
        members = []
        for server in c["servers"]:
            iface = next((i for i in c["interfaces"] if i["server"] == server), None)
            members.append(
                dict(
                    server=server,
                    serverHostname="node%d" % server,
                    nic=iface["nic"] if iface else None,
                    vlan=iface.get("vlan") if iface else None,
                    serviceRunning=True,
                    raftRole="follower",
                    placementKnown=True,
                    vipsHeld=[],
                )
            )
        return 200, dict(
            serviceId=c["serviceId"],
            members=members,
            vips=list(c["vips"]),
            identityMismatch=False,
            haPossible=len(c["servers"]) >= 2,
            minimumMembers=2,
        )

    def put_ha(self, call, sid):
        c = self.clusters[int(sid)]
        c["vips"] = list(call.body["vips"])
        c["interfaces"] = [dict(i) for i in call.body.get("interfaces") or []]
        return 204, None

    def delete_ha(self, call, sid):
        self.clusters[int(sid)]["vips"] = []
        return 204, None

    def delete_service(self, call, sid):
        if int(sid) not in self.clusters:
            return 404, dict(code=404, message="Not Found")
        if call.query.get("ignoreWarning") != "confirm-gw":
            warning = dict(token="confirm-gw", warningText="removes the gateway from every node", affirmativeLabel="Remove")
            return 400, dict(code=400, message="w", ignorableWarning=warning)
        del self.clusters[int(sid)]
        return 200, self.new_task("Delete service", sid)

    def list_exports(self, call, sid):
        return 200, copy.deepcopy(self.clusters[int(sid)]["exports"])

    def create_export(self, call, sid, body=None):
        body = body or call.body
        c = self.clusters[int(sid)]
        if c["implementation"] == "ganesha" and not body.get("volume"):
            return 400, dict(code=400, message="nfs-ganesha exports need a volume")
        self.next_export += 1
        export = dict(
            id=self.next_export,
            serviceId=int(sid),
            nfsPath=body["nfsPath"],
            path=body["path"],
            access=[dict(a) for a in body.get("access") or []],
            protocols=dict(body.get("protocols") or dict(nfs3=False, nfs4=True)),
            volume=body.get("volume"),
        )
        c["exports"].append(export)
        return 200, copy.deepcopy(export)

    def put_export(self, call, sid, eid):
        export = next(e for e in self.clusters[int(sid)]["exports"] if e["id"] == int(eid))
        assert "volume" not in call.body
        export.update(nfsPath=call.body["nfsPath"], path=call.body["path"], access=call.body["access"], protocols=call.body["protocols"])
        return 204, None

    def delete_export(self, call, sid, eid):
        c = self.clusters[int(sid)]
        c["exports"] = [e for e in c["exports"] if e["id"] != int(eid)]
        return 204, None

    # cephfs-guard ---------------------------------------------------------

    def list_guards(self, call):
        return 200, dict(data=[self.guard_view(g) for g in self.guards.values()], total=len(self.guards), after=0)

    def list_guard_services(self, call, cid):
        return 200, dict(services=copy.deepcopy(self.guards[int(cid)]["services"]))

    def list_webhooks(self, call, cid):
        return 200, dict(webhooks=copy.deepcopy(self.guards[int(cid)]["webhooks"]))

    DETECTOR_KEYS = ("extensionChange", "filenameChange", "bulkOperations", "ransomNote", "fileEntropy", "timelineAnalysis")
    ACTION_KEYS = ("snapshot", "yaraScan", "block")

    def guard_view(self, g):
        return dict(
            id=g["id"],
            volume=g["volume"],
            detection=dict(g["detection"]),
            detectors=dict((k, dict(label=k, **v)) for k, v in g["detectors"].items()),
            actions=dict((k, dict(label=k, enabled=v)) for k, v in g["actions"].items()),
            health=dict(enabled=True, configId=g["id"], healthy=True, services=[]),
        )

    def make_service(self, g, server):
        self.next_id += 1
        nic = next(n for n in nics_for(server["id"]) if n["id"] == server["nicId"])
        vlan = next((v for v in nic["vlans"] if v["id"] == server.get("vlanId")), None)
        return dict(
            id=self.next_id,
            configId=g["id"],
            volume=g["volume"],
            serverId=server["id"],
            serverHostname="node%d" % server["id"],
            serviceName="cephfs-guard@%d" % self.next_id,
            nicId=nic["id"],
            nicName=nic["name"],
            interfaceName=nic["name"],
            ip="10.0.0.%d" % server["id"],
            useIpv6=bool(server.get("useIpv6")),
            mdsPort=9000,
            httpPort=9100,
            vlanId=server.get("vlanId"),
            vlan=vlan["vlan"] if vlan else None,
        )

    def create_guard(self, call):
        body = call.body
        self.next_id += 1
        g = dict(
            id=self.next_id,
            volume=body["volume"],
            detection=dict(actionThreshold=0.6, minDetectors=1),
            detectors=dict((k, dict(enabled=True, weight=1.0)) for k in self.DETECTOR_KEYS),
            actions=dict((k, False) for k in self.ACTION_KEYS),
            services=[],
            webhooks=[],
            next_hook=0,
        )
        g["detection"].update(body.get("detection") or {})
        for k, v in (body.get("detectors") or {}).items():
            g["detectors"][k] = dict(v)
        for k, v in (body.get("actions") or {}).items():
            g["actions"][k] = v["enabled"]
        g["services"] = [self.make_service(g, s) for s in body["servers"]]
        self.guards[g["id"]] = g
        return 200, self.new_task("Create cephfs-guard", body["volume"])

    def patch_guard(self, call, cid):
        g = self.guards[int(cid)]
        body = call.body
        if body.get("detection"):
            g["detection"].update(body["detection"])
        for k, v in (body.get("detectors") or {}).items():
            g["detectors"][k] = dict(v)
        for k, v in (body.get("actions") or {}).items():
            if v is not None:
                g["actions"][k] = v["enabled"]
        return 200, self.new_task("Update cephfs-guard", g["volume"])

    def delete_guard(self, call, cid):
        del self.guards[int(cid)]
        return 200, self.new_task("Delete cephfs-guard", cid)

    def add_guard_services(self, call, cid):
        g = self.guards[int(cid)]
        g["services"].extend(self.make_service(g, s) for s in call.body["servers"])
        return 200, self.new_task("Add cephfs-guard services", g["volume"])

    def patch_guard_service(self, call, cid, svc):
        service = next(s for s in self.guards[int(cid)]["services"] if s["id"] == int(svc))
        for key in ("mdsPort", "httpPort"):
            if call.body.get(key) is not None:
                service[key] = call.body[key]
        return 200, self.new_task("Update cephfs-guard service", svc)

    def add_webhook(self, call, cid):
        g = self.guards[int(cid)]
        g["next_hook"] += 1
        hook = dict(id=g["next_hook"], url=call.body["url"], timeout=call.body.get("timeout") or "5s")
        g["webhooks"].append(hook)
        return 200, dict(hook)

    def patch_webhook(self, call, cid, wid):
        hook = next(h for h in self.guards[int(cid)]["webhooks"] if h["id"] == int(wid))
        hook.update(url=call.body["url"], timeout=call.body.get("timeout") or hook["timeout"])
        return 204, None

    def delete_webhook(self, call, cid, wid):
        g = self.guards[int(cid)]
        g["webhooks"] = [h for h in g["webhooks"] if h["id"] != int(wid)]
        return 204, None


def assert_only_gets(fake):
    assert fake.writes() == [], "wrote: %r" % fake.writes()
