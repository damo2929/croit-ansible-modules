# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""In-memory croit RGW: gateways, bootstrap, placements and multisite, for the Phase 4 RGW tests."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit

SERVERS = [dict(id=1, hostname="node1"), dict(id=2, hostname="node2"), dict(id=3, hostname="node3")]
EMPTY_CONFIG = dict(dnsName=None, port=None, sslPort=None, zone=None)
TOKEN = "UFJJTUFSWS1UT0tFTi1TRUNSRVQ="


class RgwCluster(FakeCroit):
    def __init__(self, gateways_on=(), multisite=None, placements=None):
        super(RgwCluster, self).__init__()
        self.next_service = 50
        self.services = []
        self.configs = {}
        for server_id in gateways_on:
            self.add_gateway(server_id)
        self.ha_groups = [dict(id=7, description="s3-vip", rgwNodes=[])]
        self.multisite = multisite or dict(enabled=False, type="PRIMARY", readonly=None, metrics={})
        self.placements = placements if placements is not None else [
            dict(name="default-placement", storageClass="STANDARD", dataPool="default.rgw.buckets.data",
                 indexPool="default.rgw.buckets.index", dataExtraPool="default.rgw.buckets.non-ec", isDefault=True),
        ]
        self.bootstrap_body = None
        self.serve_tasks()
        self.reply("GET", "/servers", 200, SERVERS)
        self.route("GET", "/services", lambda call: (200, copy.deepcopy(self.services)))
        self.route("GET", "/servers/ha-groups", lambda call: (200, copy.deepcopy(self.ha_groups)))
        self.route("GET", r"/services/(?P<sid>\d+)/rgw-config", lambda call, sid: (200, copy.deepcopy(self.configs[int(sid)])))
        self.route("POST", "/s3/bootstrap", self.bootstrap)
        self.route("POST", "/s3/services", self.add_services)
        self.route("PATCH", r"/services/(?P<sid>\d+)", self.patch_service)
        self.route("DELETE", r"/services/(?P<sid>\d+)", self.delete_service)
        self.route("GET", "/s3/placements", self.get_placements)
        self.route("PUT", r"/s3/placements/(?P<name>[^/]+)", self.put_rule)
        self.route("PUT", r"/s3/placements/(?P<rule>[^/]+)/storage-classes/(?P<sc>[^/]+)", self.put_class)
        self.route("DELETE", r"/s3/placements/(?P<rule>[^/]+)/storage-classes/(?P<sc>[^/]+)", self.delete_class)
        self.route("PUT", "/s3/default-placement", self.set_default)
        self.route("GET", "/s3/multisite/status", lambda call: (200, copy.deepcopy(self.multisite)))
        self.route("GET", "/s3/multisite/primary/token", self.get_token)
        self.route("POST", "/s3/multisite/primary", self.convert)
        self.route("POST", "/s3/multisite/secondary", self.join)
        self.route("POST", "/s3/multisite/promote", self.promote)
        self.route("PATCH", "/s3/multisite/readonly", self.set_readonly)
        self.route("PATCH", "/s3/multisite/endpoints", lambda call: (200, self.new_task("Endpoints")))

    # Gateways -------------------------------------------------------------

    def add_gateway(self, server_id):
        self.next_service += 1
        self.services.append(
            dict(id=self.next_service, type="radosgw", name="ceph-radosgw@%d" % server_id, server=server_id,
                 multiServer=[], running=True, state="ENABLED", hints=[], loading=False)
        )
        self.configs[self.next_service] = dict(EMPTY_CONFIG)

    def bootstrap(self, call):
        if self.services:
            return 400, dict(code=400, message="cluster already carries an object gateway")
        self.bootstrap_body = call.body
        for server_id in call.body["serverIds"]:
            self.add_gateway(server_id)
        return 200, self.new_task("Bootstrap S3")

    def add_services(self, call):
        for server_id in call.body["serverIds"]:
            self.add_gateway(server_id)
        return 200, self.new_task("Add RGW")

    def patch_service(self, call, sid):
        config = self.configs[int(sid)]
        mapping = dict(port="port", sslPort="sslPort", rgwDnsName="dnsName", rgwZone="zone")
        for key, value in call.body.items():
            config[mapping[key]] = value
        return 200, self.new_task("Reconfigure RGW")

    def delete_service(self, call, sid):
        sid = int(sid)
        if len(self.services) == 1 and call.query.get("ignoreWarning") != "rm-all":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="rm-all", warningText="removes every gateway"))
        self.services = [s for s in self.services if s["id"] != sid]
        return 200, self.new_task("Remove RGW")

    # Placements -----------------------------------------------------------

    def get_placements(self, call):
        default = [p for p in self.placements if p["isDefault"]]
        return 200, dict(
            placements=copy.deepcopy(self.placements),
            defaultPlacementRule=default[0]["name"] if default else None,
            defaultStorageClass=default[0]["storageClass"] if default else None,
        )

    def put_rule(self, call, name):
        self.placements.append(
            dict(name=name, storageClass="STANDARD", dataPool=call.body["dataPool"],
                 indexPool=call.body.get("indexPool") or "default.rgw.buckets.index",
                 dataExtraPool=call.body.get("dataExtraPool") or "default.rgw.buckets.non-ec", isDefault=False)
        )
        return 204, None

    def put_class(self, call, rule, sc):
        base = [p for p in self.placements if p["name"] == rule][0]
        self.placements.append(dict(base, storageClass=sc, dataPool=call.body["dataPool"], isDefault=False))
        return 204, None

    def delete_class(self, call, rule, sc):
        row = [p for p in self.placements if p["name"] == rule and p["storageClass"] == sc][0]
        if row["isDefault"] and call.query.get("ignoreWarning") != "rm-default":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="rm-default", warningText="deletes the default"))
        if sc == "STANDARD":
            self.placements = [p for p in self.placements if p["name"] != rule]
        else:
            self.placements = [p for p in self.placements if not (p["name"] == rule and p["storageClass"] == sc)]
        return 204, None

    def set_default(self, call):
        for p in self.placements:
            p["isDefault"] = p["name"] == call.body["placementRule"] and p["storageClass"] == call.body["storageClass"]
        return 204, None

    # Multisite ------------------------------------------------------------

    def get_token(self, call):
        if not (self.multisite["enabled"] and self.multisite["type"] == "PRIMARY"):
            return 400, dict(code=400, message="not a primary")
        return 200, TOKEN

    def convert(self, call):
        self.multisite.update(enabled=True, type="PRIMARY", readonly=None)
        return 200, self.new_task("Convert to primary")

    def join(self, call):
        self.multisite.update(enabled=True, type="SECONDARY", readonly=bool(call.body.get("readonly")))
        return 200, self.new_task("Join as secondary")

    def promote(self, call):
        if self.multisite.get("behind") and call.query.get("ignoreWarning") != "behind":
            return 400, dict(code=400, message="w", ignorableWarning=dict(token="behind", warningText="site is behind"))
        self.multisite.update(type="PRIMARY", readonly=None)
        return 200, self.new_task("Promote")

    def set_readonly(self, call):
        self.multisite["readonly"] = call.body["readonly"]
        return 200, self.new_task("Readonly")
