# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stateful fake of croit's SMB gateway endpoints (test-only)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit

SERVERS = [
    dict(id=1, hostname="node1", ip="10.0.0.1"),
    dict(id=2, hostname="node2", ip="10.0.0.2"),
    dict(id=3, hostname="node3", ip="10.0.0.3"),
]
NICS = {
    1: [dict(id=11, name="eth0", linuxName="eth0", mac="aa:00:00:00:00:11", vlans=[dict(id=111, vlan=20)])],
    2: [dict(id=21, name="eth0", linuxName="eth0", mac="aa:00:00:00:00:21", vlans=[]),
        dict(id=22, name="eth1", linuxName="eth1", mac="aa:00:00:00:00:22", vlans=[])],
    3: [dict(id=31, name="eth0", linuxName="eth0", mac="aa:00:00:00:00:31", vlans=[])],
}
CONFIG_KEYS = (
    "serviceId", "description", "type", "virtualIps", "posixSharesAllowed", "configGeneration", "cephSnapshots",
    "migrationInProgress", "dnsServers", "domain", "domainController", "globalParameters", "netbiosDomainName",
    "organizationalUnit", "serviceDnsName", "shareDefaults",
)
EMPTY_OPTIONS = dict(parameters={}, vfsObjects=[], vfsObjectsBefore=[])


def nic_name(server_id, nic_id):
    for nic in NICS.get(server_id, []):
        if nic["id"] == nic_id:
            return nic["name"]
    return None


class SmbCluster(FakeCroit):
    """Holds SMB clusters, shares, ACLs, users and groups; remembers every password it was sent."""

    def __init__(self):
        super(SmbCluster, self).__init__()
        self.clusters = {}
        self.acls = {}
        self.passwords = []
        self.next_id = 100
        self.serve_tasks()
        self.reply("GET", "/servers", 200, SERVERS)
        self.route("GET", r"/servers/(?P<sid>\d+)/nics", lambda call, sid: (200, copy.deepcopy(NICS.get(int(sid), []))))
        self.route("GET", "/gateways/smb", self.list_configs)
        self.route("GET", "/gateways/smb/servers", self.list_servers)
        self.route("GET", "/gateways/smb/shares", self.list_shares)
        self.route("POST", "/services/smb", lambda call: self.create(call, "simple"))
        self.route("POST", "/services/smb/active-directory-authentication", lambda call: self.create(call, "active-directory"))
        base = r"/services/smb/(?P<cid>\d+)"
        self.route("GET", base, self.detail)
        self.route("PATCH", base, self.patch)
        self.route("DELETE", base, self.delete)
        self.route("POST", base + "/servers", self.add_server)
        self.route("DELETE", base + r"/servers/(?P<sid>\d+)", self.remove_server)
        self.route("POST", base + "/service-dns-name", self.dns_name)
        self.route("POST", base + "/migrate-generation", self.migrate)
        self.route("POST", base + "/shares", self.add_share)
        self.route("PUT", base + r"/shares/(?P<share_id>\d+)", self.put_share)
        self.route("DELETE", base + r"/shares/(?P<share_id>\d+)", self.delete_share)
        self.route("GET", base + r"/shares/(?P<share_id>\d+)/acl", self.get_acl)
        self.route("PUT", base + r"/shares/(?P<share_id>\d+)/acl", self.put_acl)
        self.route("PUT", base + r"/shares/(?P<share_id>\d+)/options", self.put_options)
        self.route("GET", base + "/users", lambda call, cid: (200, dict(data=copy.deepcopy(self.c(cid)["users"]), total=0, after=0)))
        self.route("POST", base + "/users", self.add_user)
        self.route("DELETE", base + r"/users/(?P<uid>\d+)", self.delete_user)
        self.route("PUT", base + r"/users/(?P<uid>\d+)/groups", self.user_groups)
        self.route("POST", base + r"/users/(?P<uid>\d+)/password", self.user_password)
        self.route("GET", base + "/groups", self.list_groups)
        self.route("POST", base + "/groups", self.add_group)
        self.route("DELETE", base + r"/groups/(?P<gid>\d+)", self.delete_group)

    # Helpers --------------------------------------------------------------

    def new_id(self):
        self.next_id += 1
        return self.next_id

    def c(self, cid):
        return self.clusters[int(cid)]

    def add_cluster(self, description, kind="simple", gen=2, servers=((1, 11, None),), **extra):
        cid = self.new_id()
        cluster = dict(
            serviceId=cid,
            description=description,
            type=kind,
            virtualIps=["10.0.0.200/24"],
            posixSharesAllowed=kind == "simple",
            configGeneration=gen,
            cephSnapshots=False,
            migrationInProgress=False,
            dnsServers=[] if kind == "active-directory" else None,
            domain="MY-ORG.LOCAL" if kind == "active-directory" else None,
            domainController="dc01" if kind == "active-directory" else None,
            globalParameters={},
            netbiosDomainName="MY-ORG" if kind == "active-directory" else None,
            organizationalUnit=None,
            serviceDnsName="files" if kind == "active-directory" else None,
            shareDefaults=copy.deepcopy(EMPTY_OPTIONS),
            customizeIdmap=False,
            idmapConfigs=[],
            members=[dict(server=s, nic=nic_name(s, n), vlan=v) for s, n, v in servers],
            shares=[],
            users=[],
            groups=[],
        )
        cluster.update(extra)
        self.clusters[cid] = cluster
        return cluster

    def add_share_row(self, cluster, name, path, **extra):
        share = dict(
            id=self.new_id(),
            serviceId=cluster["serviceId"],
            type=cluster["type"],
            share=name,
            path=path,
            volume="cephfs" if cluster["configGeneration"] >= 2 else None,
            aclMode="WINDOWS" if cluster["configGeneration"] >= 2 else None,
            guest=False,
            ro=False,
            rw=True,
            roUsers=[],
            rwUsers=[],
            parameters={},
            vfsObjects=[],
            vfsObjectsBefore=[],
        )
        share.update(extra)
        cluster["shares"].append(share)
        self.acls[share["id"]] = dict(grants=[], unresolved=[], unrepresentable=[])
        return share

    def config(self, cluster):
        return dict((k, copy.deepcopy(cluster.get(k))) for k in CONFIG_KEYS)

    def task(self, name, obj=None):
        return 200, self.new_task(name, obj)

    # Clusters -------------------------------------------------------------

    def list_configs(self, call):
        return 200, dict(data=[self.config(c) for c in self.clusters.values()], total=len(self.clusters), after=0)

    def list_servers(self, call):
        rows = []
        for c in self.clusters.values():
            for m in c["members"]:
                host = next(s["hostname"] for s in SERVERS if s["id"] == m["server"])
                rows.append(dict(serviceId=c["serviceId"], serverId=m["server"], hostname=host, nic=m["nic"], vlan=m["vlan"], virtualIps=[], healthy=True))
        return 200, dict(data=rows, total=len(rows), after=0)

    def list_shares(self, call):
        rows = [copy.deepcopy(s) for c in self.clusters.values() for s in c["shares"]]
        return 200, dict(data=rows, total=len(rows), after=0)

    def detail(self, call, cid):
        if int(cid) not in self.clusters:
            return 404, dict(code=404, message="Not Found")
        c = self.c(cid)
        detail = self.config(c)
        detail.update(
            servers=[dict(server=m["server"], nic=m["nic"], vlan=m["vlan"], virtualIps=[], healthy=True) for m in c["members"]],
            shares=copy.deepcopy(c["shares"]),
            customizeIdmap=c["customizeIdmap"],
            idmapConfigs=copy.deepcopy(c["idmapConfigs"]),
        )
        return 200, detail

    def create(self, call, kind):
        body = call.body
        for server in body["servers"]:
            if server.get("domainAdminPassword"):
                self.passwords.append(server["domainAdminPassword"])
        cluster = self.add_cluster(
            body.get("description"),
            kind=kind,
            servers=[(s["server"], s.get("nic"), s.get("vlan")) for s in body["servers"]],
            virtualIps=list(body["virtualIps"]),
            cephSnapshots=bool(body.get("cephSnapshots")),
            globalParameters=dict(body.get("globalParameters") or {}),
            shareDefaults=dict(EMPTY_OPTIONS, **(body.get("shareDefaults") or {})),
        )
        if kind == "active-directory":
            cluster.update(
                domain=body["domain"],
                netbiosDomainName=body["netbiosDomainName"],
                domainController=body["domainController"],
                dnsServers=list(body["dnsServers"]),
                serviceDnsName=body.get("serviceDnsName"),
                customizeIdmap=bool(body.get("customizeIdmap")),
            )
        for user in body.get("users") or []:
            if user.get("password"):
                self.passwords.append(user["password"])
            cluster["users"].append(dict(id=self.new_id(), username=user["username"], uid=user.get("uid") or 2000, groupIds=[]))
        return self.task("Create SMB cluster", body.get("description"))

    def patch(self, call, cid):
        c = self.c(cid)
        for key, value in call.body.items():
            c[key] = copy.deepcopy(value)
        return self.task("Update SMB cluster")

    def delete(self, call, cid):
        c = self.c(cid)
        if len(c["members"]) > 1 and call.query.get("ignoreWarning") != "del-many":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="del-many", warningText="several members", affirmativeLabel="Remove"))
        del self.clusters[int(cid)]
        return 204, None

    def add_server(self, call, cid):
        body = call.body
        if body.get("domainAdminPassword"):
            self.passwords.append(body["domainAdminPassword"])
        self.c(cid)["members"].append(dict(server=body["server"], nic=nic_name(body["server"], body.get("nic")), vlan=body.get("vlan")))
        return self.task("Add SMB server")

    def remove_server(self, call, cid, sid):
        c = self.c(cid)
        c["members"] = [m for m in c["members"] if m["server"] != int(sid)]
        return self.task("Remove SMB server")

    def dns_name(self, call, cid):
        self.passwords.append(call.body.get("domainAdminPassword"))
        self.c(cid)["serviceDnsName"] = call.body["serviceDnsName"]
        return self.task("Change SMB DNS name")

    def migrate(self, call, cid):
        c = self.c(cid)
        c.update(configGeneration=2, migrationInProgress=False)
        for share in c["shares"]:
            share["volume"] = "cephfs"
            share["aclMode"] = "POSIX" if share["id"] in (call.body.get("posixShareIds") or []) else "WINDOWS"
        if "customizeIdmap" in call.body:
            c["customizeIdmap"] = call.body["customizeIdmap"]
        return self.task("Migrate SMB cluster")

    # Shares ---------------------------------------------------------------

    def share(self, cid, share_id):
        for share in self.c(cid)["shares"]:
            if share["id"] == int(share_id):
                return share
        raise AssertionError("no share %s" % share_id)

    def add_share(self, call, cid):
        c = self.c(cid)
        body = call.body
        assert body["type"] == c["type"]
        share = self.add_share_row(
            c,
            body["share"],
            body["path"],
            guest=body.get("guest"),
            ro=body.get("ro"),
            rw=body.get("rw"),
            roUsers=body.get("roUsers"),
            rwUsers=body.get("rwUsers"),
            parameters=dict(body.get("parameters") or {}),
            vfsObjects=list(body.get("vfsObjects") or []),
            vfsObjectsBefore=list(body.get("vfsObjectsBefore") or []),
        )
        if c["configGeneration"] >= 2:
            share["volume"] = body.get("volume") or "cephfs"
            share["aclMode"] = body.get("aclMode") or "WINDOWS"
            self.acls[share["id"]]["grants"] = copy.deepcopy(body.get("grants") or [])
        return self.task("Create SMB share", body["share"])

    def put_share(self, call, cid, share_id):
        if self.c(cid)["configGeneration"] >= 2:
            return 400, dict(code=400, message="generation-2 shares cannot be replaced")
        share = self.share(cid, share_id)
        for key in ("path", "guest", "ro", "rw", "roUsers", "rwUsers"):
            if key in call.body:
                share[key] = copy.deepcopy(call.body[key])
        return 204, None

    def delete_share(self, call, cid, share_id):
        c = self.c(cid)
        c["shares"] = [s for s in c["shares"] if s["id"] != int(share_id)]
        return 204, None

    def get_acl(self, call, cid, share_id):
        return 200, copy.deepcopy(self.acls[int(share_id)])

    def put_acl(self, call, cid, share_id):
        acl = self.acls[int(share_id)]
        acl.update(grants=copy.deepcopy(call.body["grants"]), unrepresentable=[], unresolved=[])
        return self.task("Apply share ACL")

    def put_options(self, call, cid, share_id):
        share = self.share(cid, share_id)
        share.update(
            parameters=dict(call.body.get("parameters") or {}),
            vfsObjects=list(call.body.get("vfsObjects") or []),
            vfsObjectsBefore=list(call.body.get("vfsObjectsBefore") or []),
        )
        return 204, None

    # Users and groups -----------------------------------------------------

    def add_user(self, call, cid):
        body = call.body
        if body.get("password"):
            self.passwords.append(body["password"])
        users = self.c(cid)["users"]
        users.append(
            dict(id=self.new_id(), username=body["username"], uid=body.get("uid") or 2000 + len(users), groupIds=sorted(body.get("groupIds") or []))
        )
        return self.task("Create SMB user", body["username"])

    def delete_user(self, call, cid, uid):
        c = self.c(cid)
        c["users"] = [u for u in c["users"] if u["id"] != int(uid)]
        return self.task("Delete SMB user")

    def user_groups(self, call, cid, uid):
        for user in self.c(cid)["users"]:
            if user["id"] == int(uid):
                user["groupIds"] = sorted(call.body["groupIds"])
        return 204, None

    def user_password(self, call, cid, uid):
        self.passwords.append(call.body["password"])
        return self.task("Set SMB password")

    def list_groups(self, call, cid):
        c = self.c(cid)
        rows = []
        for group in c["groups"]:
            row = dict(group)
            row["memberIds"] = sorted(u["id"] for u in c["users"] if group["id"] in u["groupIds"])
            rows.append(row)
        return 200, dict(data=rows, total=len(rows), after=0)

    def add_group(self, call, cid):
        c = self.c(cid)
        gid = self.new_id()
        c["groups"].append(dict(id=gid, groupname=call.body["groupname"], gid=call.body.get("gid") or 3000 + len(c["groups"])))
        return 200, dict(id=gid)

    def delete_group(self, call, cid, gid):
        c = self.c(cid)
        c["groups"] = [g for g in c["groups"] if g["id"] != int(gid)]
        for user in c["users"]:
            user["groupIds"] = [i for i in user["groupIds"] if i != int(gid)]
        return 204, None
