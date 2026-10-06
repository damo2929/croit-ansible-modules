# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""In-memory fake of croit's /gateways/nvmeof API for the nvmeof_* module tests."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit

SERVERS = [dict(id=1, hostname="nvme1"), dict(id=2, hostname="nvme2")]
NICS = {
    1: [dict(id=11, name="eth0", linuxName="enp1s0", mac="aa:bb:cc:00:01:00", vlans=[dict(id=111, vlan=50)])],
    2: [dict(id=21, name="eth0", linuxName="enp1s0", mac="aa:bb:cc:00:02:00", vlans=[])],
}
TRANSPORT_KEYS = ("inCapsuleDataSize", "ioUnitSize", "maxIoQpairsPerCtrlr", "maxIoSize")


def _transport_rows(items, gateway_id=None, service_id=None):
    rows = []
    for item in items or []:
        row = dict(type=item["type"])
        for key in TRANSPORT_KEYS:
            row[key] = item.get(key)
        if service_id is not None:
            row.update(gatewayId=gateway_id, serviceId=service_id)
        rows.append(row)
    return rows


def _page(items):
    """Answer list endpoints in croit's pagination wrapper, as the spec documents."""
    return dict(data=[copy.deepcopy(i) for i in items], total=len(items), after=0)


class NvmeofCluster(FakeCroit):
    def __init__(self):
        super(NvmeofCluster, self).__init__()
        self.gateways = {}
        self.services = {}
        self.ceph_clusters = {}
        self.subsystems = {}
        self.disks = {}
        self.hosts = {}
        self.images = set([("rbd", "vm1"), ("rbd", "vm2"), ("rbd", "vm3")])
        self.deleted_images = []
        self._ids = 0
        self.serve_tasks()
        self.reply("GET", "/servers", 200, SERVERS)
        self.route("GET", r"/servers/(?P<server_id>\d+)/nics", lambda call, server_id: (200, copy.deepcopy(NICS[int(server_id)])))

        r = self.route
        r("GET", "/gateways/nvmeof", lambda call: (200, _page(self.gateways.values())))
        r("POST", "/gateways/nvmeof", self.create_gateway)
        r("PATCH", r"/gateways/nvmeof/(?P<gid>\d+)", self.patch_gateway)
        r("DELETE", r"/gateways/nvmeof/(?P<gid>\d+)", self.delete_gateway)
        r("POST", r"/gateways/nvmeof/(?P<gid>\d+)", self.create_service)
        r("POST", r"/gateways/nvmeof/(?P<gid>\d+)/reconfigure", lambda call, gid: (200, self.task("Reconfigure")))
        r("PATCH", r"/gateways/nvmeof/(?P<gid>\d+)/services/(?P<sid>\d+)", self.patch_service)
        r("POST", r"/gateways/nvmeof/(?P<gid>\d+)/services/(?P<sid>\d+)/listeners", self.create_listener)
        r("PATCH", r"/gateways/nvmeof/(?P<gid>\d+)/services/(?P<sid>\d+)/listeners/(?P<lid>\d+)", self.patch_listener)
        r("DELETE", r"/gateways/nvmeof/(?P<gid>\d+)/services/(?P<sid>\d+)/listeners/(?P<lid>\d+)", self.delete_listener)
        r("GET", "/gateways/nvmeof/services", lambda call: (200, _page(self.services.values())))
        r("GET", "/gateways/nvmeof/listeners", lambda call: (200, _page(self.listeners())))
        r("GET", "/gateways/nvmeof/ceph-clusters", lambda call: (200, _page(self.ceph_clusters.values())))
        r("POST", "/gateways/nvmeof/ceph-clusters", self.create_ceph_cluster)
        r("DELETE", r"/gateways/nvmeof/ceph-clusters/(?P<name>[^/]+)", self.delete_ceph_cluster)
        r("GET", "/gateways/nvmeof/subsystems", lambda call: (200, _page(self.subsystems.values())))
        r("POST", "/gateways/nvmeof/subsystems", self.create_subsystem)
        r("PATCH", r"/gateways/nvmeof/subsystems/(?P<sub>\d+)", self.patch_subsystem)
        r("DELETE", r"/gateways/nvmeof/subsystems/(?P<sub>\d+)", self.delete_subsystem)
        r("POST", r"/gateways/nvmeof/subsystems/(?P<sub>\d+)/(?P<op>attach|detach)-(?P<kind>disks|hosts)", self.attach)
        r("GET", "/gateways/nvmeof/disks", lambda call: (200, _page(self.disks.values())))
        r("POST", "/gateways/nvmeof/disks", self.create_disk)
        r("PATCH", r"/gateways/nvmeof/disks/(?P<did>\d+)", self.patch_disk)
        r("DELETE", r"/gateways/nvmeof/disks/(?P<did>\d+)", self.delete_disk)
        r("GET", "/gateways/nvmeof/hosts", lambda call: (200, _page(self.masked_hosts(call))))
        r("POST", "/gateways/nvmeof/hosts", self.create_host)
        r("PUT", r"/gateways/nvmeof/hosts/(?P<hid>\d+)", self.put_host)
        r("DELETE", r"/gateways/nvmeof/hosts/(?P<hid>\d+)", self.delete_host)
        # Set to True to answer every host's key as "(masked)", like a non-admin token sees it.
        self.mask_keys = False

    # Helpers --------------------------------------------------------------

    def seed_gateway(self, name="gw", server_ids=(1, 2)):
        """Directly create a gateway with one target service per server; returns its id."""
        gid = self.next_id()
        self.gateways[gid] = dict(gatewayId=gid, name=name, description="", forceSecure=False, transportDefaults=[], hints=[])
        for server_id in server_ids:
            self._add_service(gid, dict(serverId=server_id))
        return gid

    def seed_subsystem(self, gid, nqn):
        return self._add_subsystem(gid, nqn)["id"]

    def service_on(self, hostname):
        return next(s for s in self.services.values() if s["serverHostname"] == hostname)

    def next_id(self):
        self._ids += 1
        return self._ids

    def task(self, name):
        return self.new_task(name)

    def listeners(self):
        return [lst for s in self.services.values() for lst in s["listeners"]]

    def sync_relations(self):
        """Recompute the derived id lists croit returns on disks and hosts."""
        for disk in self.disks.values():
            subs = [s for s in self.subsystems.values() if disk["id"] in s["disks"]]
            disk["subsystemNqns"] = [s["nqn"] for s in subs]
            disk["hosts"] = sorted(set(h for s in subs for h in s["hosts"]))
        for host in self.hosts.values():
            subs = [s for s in self.subsystems.values() if host["id"] in s["hosts"]]
            host["subsystems"] = [s["id"] for s in subs]
            host["disks"] = sorted(set(d for s in subs for d in s["disks"]))

    # Gateways and services -----------------------------------------------

    def create_gateway(self, call):
        body = call.body
        gid = self.next_id()
        self.gateways[gid] = dict(
            gatewayId=gid,
            name=body.get("name") or "NVMe over Fabrics",
            description=body.get("description") or "",
            forceSecure=bool(body.get("forceSecure")),
            transportDefaults=_transport_rows(body.get("transportDefaults")),
            hints=[],
        )
        for svc in body.get("services") or []:
            self._add_service(gid, svc)
        self._add_subsystem(gid, "nqn.2016-06.io.spdk:gw%d" % gid)
        return 200, self.task("Create NVMe-oF cluster")

    def _add_service(self, gid, body):
        sid = self.next_id()
        server = next(s for s in SERVERS if s["id"] == body["serverId"])
        self.services[sid] = dict(
            gatewayId=gid,
            serviceId=sid,
            serverId=server["id"],
            serverHostname=server["hostname"],
            nrHugepages=body.get("nrHugepages") or 0,
            anaState="optimized",
            name="nvmf_tgt@%d" % sid,
            description=body.get("description") or "",
            cpuCores=body.get("cpuCores") or "",
            fencesItself=True,
            transports=_transport_rows(body.get("transports"), gid, sid),
            listeners=[],
            hints=[],
        )
        for listener in body.get("listeners") or []:
            self._add_listener(self.services[sid], listener)
        return self.services[sid]

    def patch_gateway(self, call, gid):
        gw = self.gateways[int(gid)]
        body = call.body
        if "description" in body:
            gw["description"] = body["description"]
        if "forceSecure" in body:
            gw["forceSecure"] = body["forceSecure"]
        if "transportDefaults" in body:
            gw["transportDefaults"] = _transport_rows(body["transportDefaults"])
        return 200, self.task("Update NVMe-oF cluster")

    def delete_gateway(self, call, gid):
        gid = int(gid)
        del self.gateways[gid]
        for table in (self.services, self.subsystems, self.disks, self.hosts):
            for key in [k for k, v in table.items() if v["gatewayId"] == gid]:
                del table[key]
        return 200, self.task("Delete NVMe-oF cluster")

    def create_service(self, call, gid):
        self._add_service(int(gid), call.body)
        return 200, self.task("Create NVMe-oF service")

    def patch_service(self, call, gid, sid):
        svc = self.services[int(sid)]
        body = call.body
        for key in ("description", "nrHugepages", "cpuCores", "anaState"):
            if key in body:
                svc[key] = body[key]
        if "transports" in body:
            svc["transports"] = _transport_rows(body["transports"], svc["gatewayId"], svc["serviceId"])
        return 200, self.task("Update NVMe-oF service")

    # Listeners ------------------------------------------------------------

    def _add_listener(self, svc, body):
        nic = next(n for n in NICS[svc["serverId"]] if n["id"] == body["nicId"])
        vlan = next((v for v in nic["vlans"] if v["id"] == body.get("vlanId")), None)
        listener = dict(
            gatewayId=svc["gatewayId"],
            serviceId=svc["serviceId"],
            listenerId=self.next_id(),
            type=body["type"],
            nicId=nic["id"],
            nicName=nic["name"],
            port=body["port"],
            secure=bool(body.get("secure")),
            vlan=vlan["vlan"] if vlan else None,
            vlanId=vlan["id"] if vlan else None,
        )
        svc["listeners"].append(listener)
        return listener

    def create_listener(self, call, gid, sid):
        self._add_listener(self.services[int(sid)], call.body)
        return 200, self.task("Add listener")

    def patch_listener(self, call, gid, sid, lid):
        listener = next(lst for lst in self.services[int(sid)]["listeners"] if lst["listenerId"] == int(lid))
        for key in ("port", "secure"):
            if key in call.body:
                listener[key] = call.body[key]
        return 200, self.task("Update listener")

    def delete_listener(self, call, gid, sid, lid):
        svc = self.services[int(sid)]
        svc["listeners"] = [lst for lst in svc["listeners"] if lst["listenerId"] != int(lid)]
        return 200, self.task("Delete listener")

    # Ceph clusters --------------------------------------------------------

    def create_ceph_cluster(self, call):
        self.ceph_clusters[call.body["name"]] = dict(name=call.body["name"], clientId=call.body.get("clientId") or "admin")
        return 200, self.task("Add ceph cluster")

    def delete_ceph_cluster(self, call, name):
        if any(d.get("cluster") == name for d in self.disks.values()):
            return 400, dict(code=400, message="ceph cluster %s is used by exported disks" % name)
        del self.ceph_clusters[name]
        return 200, self.task("Remove ceph cluster")

    # Subsystems -----------------------------------------------------------

    def _add_subsystem(self, gid, nqn):
        sub_id = self.next_id()
        self.subsystems[sub_id] = dict(
            id=sub_id,
            gatewayId=gid,
            nqn=nqn,
            serialNumber="SPDK%08d" % sub_id,
            modelNumber="croit NVMe-oF",
            maxNamespaces=32,
            hosts=[],
            disks=[],
            hostsFormatted="",
            disksFormatted="",
            anaStates=[],
            optimizedOn=None,
            optimizedOnFormatted="",
        )
        return self.subsystems[sub_id]

    def create_subsystem(self, call):
        if any(s["nqn"] == call.body["nqn"] and s["gatewayId"] == call.body["gatewayId"] for s in self.subsystems.values()):
            return 400, dict(code=400, message="NQN already used")
        self._add_subsystem(call.body["gatewayId"], call.body["nqn"])
        return 200, self.task("Create subsystem")

    def patch_subsystem(self, call, sub):
        s = self.subsystems[int(sub)]
        for key in ("serialNumber", "modelNumber", "maxNamespaces"):
            if call.body.get(key) is not None:
                s[key] = call.body[key]
        if call.body.get("anaStates") is not None:
            s["anaStates"] = [dict(serviceId=a["serviceId"], anaState=a["anaState"]) for a in call.body["anaStates"]]
        return 200, self.task("Update subsystem")

    def delete_subsystem(self, call, sub):
        del self.subsystems[int(sub)]
        self.sync_relations()
        return 200, self.task("Delete subsystem")

    def attach(self, call, sub, op, kind):
        s = self.subsystems[int(sub)]
        ids = call.body[kind]
        if op == "attach":
            s[kind] = sorted(set(s[kind]) | set(ids))
        else:
            s[kind] = [i for i in s[kind] if i not in ids]
        self.sync_relations()
        return 200, self.task("%s %s" % (op, kind))

    # Disks ----------------------------------------------------------------

    def create_disk(self, call):
        body = call.body
        if (body.get("pool"), body.get("image")) not in self.images:
            return 400, dict(code=400, message="image %s/%s does not exist" % (body.get("pool"), body.get("image")))
        cluster = body.get("cluster") or "croit"
        self.ceph_clusters.setdefault(cluster, dict(name=cluster, clientId="admin"))
        did = self.next_id()
        self.disks[did] = dict(
            type="CEPH",
            id=did,
            gatewayId=body["gatewayId"],
            bdevNames={},
            namespaceNGUID="nguid-%d" % did,
            namespaceEUI64="eui-%d" % did,
            namespaceUUID="00000000-0000-0000-0000-%012d" % did,
            hints=[],
            subsystemNqns=[],
            hosts=[],
            blockSize=body.get("blockSize") or 512,
            blockSizeFormatted="512 B",
            size=10 * 1024 ** 3,
            sizeFormatted="10 GiB",
            cluster=cluster,
            pool=body["pool"],
            image=body["image"],
        )
        for sub_id in body.get("subsystems") or []:
            self.subsystems[sub_id]["disks"].append(did)
        self.sync_relations()
        return 200, self.task("Export disk")

    def patch_disk(self, call, did):
        if call.body.get("size") is None:
            return 204, None
        self.disks[int(did)]["size"] = call.body["size"]
        return 200, self.task("Resize disk")

    def delete_disk(self, call, did):
        disk = self.disks.pop(int(did))
        for s in self.subsystems.values():
            s["disks"] = [d for d in s["disks"] if d != disk["id"]]
        if (call.body or {}).get("deleteData"):
            self.images.discard((disk["pool"], disk["image"]))
            self.deleted_images.append("%s/%s" % (disk["pool"], disk["image"]))
        self.sync_relations()
        return 200, self.task("Remove disk")

    # Hosts ----------------------------------------------------------------

    def masked_hosts(self, call):
        rows = []
        for host in self.hosts.values():
            row = copy.deepcopy(host)
            row["hasSharedKey"] = bool(host.get("sharedKey"))
            if self.mask_keys and host.get("sharedKey"):
                row["sharedKey"] = "(masked)"
            rows.append(row)
        return rows

    def create_host(self, call):
        body = call.body
        if any(h["nqn"] == body["nqn"] and h["gatewayId"] == body["gatewayId"] for h in self.hosts.values()):
            return 400, dict(code=400, message="NQN already used")
        hid = self.next_id()
        self.hosts[hid] = dict(
            id=hid,
            gatewayId=body["gatewayId"],
            nqn=body["nqn"],
            sharedKey=body.get("sharedKey"),
            subsystems=[],
            disks=[],
            subsystemsFormatted="",
            disksFormatted="",
        )
        for sub_id in body.get("subsystems") or []:
            self.subsystems[sub_id]["hosts"].append(hid)
        self.sync_relations()
        return 200, self.task("Add host")

    def put_host(self, call, hid):
        self.hosts[int(hid)]["sharedKey"] = call.body.get("sharedKey")
        return 200, self.task("Update host")

    def delete_host(self, call, hid):
        hid = int(hid)
        del self.hosts[hid]
        for s in self.subsystems.values():
            s["hosts"] = [h for h in s["hosts"] if h != hid]
        self.sync_relations()
        return 200, self.task("Remove host")
