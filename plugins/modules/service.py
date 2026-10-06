#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /servers
# croit-api: GET /services
# croit-api: GET /servers/{serverId}/disks
# croit-api: GET /crush
# croit-api: POST /servers/{serverId}/services/mon
# croit-api: POST /servers/{serverId}/services/mds
# croit-api: POST /servers/{serverId}/services/rbd-mirror
# croit-api: DELETE /services/{serviceId}
# croit-api: POST /services/{serviceId}/start
# croit-api: POST /services/{serviceId}/stop
# croit-api: POST /services/restart
# croit-api: POST /services/rolling-restart

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: service
short_description: Manage croit and Ceph services on a croit cluster
version_added: 0.1.0
description:
  - Adds and removes MON, MDS and rbd-mirror services, starts and stops any croit-managed service, and
    restarts services, including a rolling restart that waits for the cluster to recover between services.
  - A service is identified by O(server) and O(type), or by its numeric O(service_id).
  - Gateways (S3, NFS, SMB, iSCSI, NVMe-oF) are created with their own modules; this module can start, stop,
    restart and remove them.
  - OSDs are managed with M(croit.ceph.osd); this module can restart them (O(state=restarted) or
    O(state=rolling_restarted) with O(type=osd)).
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: full
    details:
      - O(state=restarted) and O(state=rolling_restarted) report a change and are skipped in check mode.
  diff_mode:
    support: full
options:
  server:
    description:
      - Server the service runs on, by hostname or numeric id.
      - Required to create a service. With O(state=restarted) or O(state=rolling_restarted), limits the
        services of O(type) to this server; without it, every service of O(type) is restarted.
      - For a service that runs on several servers (gateways), O(state=absent), O(state=started) and
        O(state=stopped) act on this server only.
    type: str
  type:
    description:
      - Service type.
      - V(mon), V(mds) and V(rbd_mirror) can be created by this module.
      - V(osd) is only valid with O(state=restarted) and O(state=rolling_restarted).
    type: str
    choices: [mon, mgr, mds, radosgw, rbd_mirror, nfs_gateway, croit_nfs, iscsi, smb, cephfsguard, keepafloatd, nvmf_tgt, osd]
  service_id:
    description:
      - Numeric croit id of the service, instead of O(server) and O(type).
    type: int
  state:
    description:
      - V(present) makes sure the service exists, creating a MON, MDS or rbd-mirror service if needed.
      - V(started) and V(stopped) also make sure the daemon runs or not. croit queues the start or stop for the
        node; with O(wait=true) the module waits until croit reports the new state.
      - V(absent) removes the service (or, with O(server), the service from that server). Removing a MON or MDS
        needs O(confirm_delete=true). croit refuses to remove the last MON, and asks for confirmation
        (O(ignore_warnings=true)) before removing the last MDS, which would make CephFS unavailable.
      - V(restarted) restarts the selected services at once, and V(rolling_restarted) one at a time, waiting for
        the cluster to be healthy between them. Both always report a change.
    type: str
    choices: [present, absent, started, stopped, restarted, rolling_restarted]
    default: present
  mon_disk:
    description:
      - Disk on O(server) to create a MON on, as a device path, serial, WWN or croit disk id.
      - Required to create a MON. Only used when the MON is created.
    type: str
  mon_ip:
    description:
      - IPv4 or IPv6 address of a new MON. Required to create a MON. Only used when the MON is created.
    type: str
  mds_volume:
    description:
      - CephFS volume a new MDS is created for. croit uses its configured filesystem when not set.
      - Only used when the MDS is created.
    type: str
  confirm_delete:
    description:
      - Must be V(true) to remove a MON or MDS service.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Add a monitor
  croit.ceph.service:
    server: storage-04
    type: mon
    mon_disk: /dev/sda
    mon_ip: 10.0.0.14

- name: Add a metadata server for the cephfs volume
  croit.ceph.service:
    server: storage-04
    type: mds
    mds_volume: cephfs
    state: started

- name: Stop the S3 gateway on one node
  croit.ceph.service:
    server: gw-01
    type: radosgw
    state: stopped

- name: Rolling restart of every OSD on one host
  croit.ceph.service:
    server: storage-01
    type: osd
    state: rolling_restarted
    wait_timeout: 3600

- name: Remove a monitor
  croit.ceph.service:
    server: storage-04
    type: mon
    state: absent
    confirm_delete: true
"""

RETURN = r"""
service:
  description:
    - The service after the change (C(MultiServerServiceResponse) in the croit API). Empty when it does not
      exist, and the state before the change in check mode.
  returned: when one service is managed
  type: dict
services:
  description: The services or OSDs that were (or in check mode would be) restarted, as C(id) and C(server), plus C(osd) for OSDs.
  returned: with O(state=restarted) or O(state=rolling_restarted)
  type: list
  elements: dict
task:
  description: The croit background task the change ran as, when there was one.
  returned: when a task ran
  type: dict
"""

import time

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import list_servers, require_disk, require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

POLL_INTERVAL = 2.0
CREATABLE = dict(mon="mon", mds="mds", rbd_mirror="rbd-mirror")
CONFIRM_DELETE_TYPES = ("mon", "mds")
ACTIONS = ("restarted", "rolling_restarted")


def on_server(service, server_id):
    return service.get("server") == server_id or server_id in (service.get("multiServer") or [])


def view(service):
    if not service:
        return {}
    return dict(
        id=service.get("id"),
        type=service.get("type"),
        server=service.get("server"),
        servers=sorted(service.get("multiServer") or []),
        state=service.get("state"),
        running=bool(service.get("running")),
    )


class ServiceModule(CroitModule):
    def __init__(self):
        super(ServiceModule, self).__init__(
            dict(
                server=dict(type="str"),
                type=dict(
                    type="str",
                    choices=[
                        "mon",
                        "mgr",
                        "mds",
                        "radosgw",
                        "rbd_mirror",
                        "nfs_gateway",
                        "croit_nfs",
                        "iscsi",
                        "smb",
                        "cephfsguard",
                        "keepafloatd",
                        "nvmf_tgt",
                        "osd",
                    ],
                ),
                service_id=dict(type="int"),
                state=dict(
                    type="str",
                    default="present",
                    choices=["present", "absent", "started", "stopped", "restarted", "rolling_restarted"],
                ),
                mon_disk=dict(type="str"),
                mon_ip=dict(type="str"),
                mds_volume=dict(type="str"),
                confirm_delete=dict(type="bool", default=False),
            ),
            required_one_of=[("type", "service_id")],
            mutually_exclusive=[("type", "service_id")],
        )
        self.servers = None
        self.server = None

    # Lookups --------------------------------------------------------------

    def resolve_server(self):
        if self.params["server"] is None:
            return None
        if self.servers is None:
            self.servers = list_servers(self)
        return require_server(self, self.params["server"], self.servers)

    def services(self):
        return [s for s in self.get_list("/services") if s.get("type") != "osd"]

    def find(self, services):
        p = self.params
        if p["service_id"] is not None:
            matches = [s for s in services if s.get("id") == p["service_id"]]
            if not matches:
                self.module.fail_json(msg="Service %s does not exist" % p["service_id"])
            return matches[0]
        if self.server is None:
            self.module.fail_json(msg="server is required to manage a single %s service" % p["type"])
        matches = [s for s in services if s.get("type") == p["type"] and on_server(s, self.server["id"])]
        if len(matches) > 1:
            self.module.fail_json(
                msg="%d %s services run on %s; use service_id: %s"
                % (len(matches), p["type"], self.server.get("hostname"), ", ".join(str(s.get("id")) for s in matches))
            )
        return matches[0] if matches else None

    def server_query(self, service):
        """``server`` query for a multi-server service acting on one node."""
        if self.server is not None and service.get("multiServer"):
            return dict(server=self.server["id"])
        return None

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        if p["type"] == "osd" and p["state"] not in ACTIONS:
            self.module.fail_json(msg="type=osd only supports state=restarted and state=rolling_restarted; use croit.ceph.osd")
        self.server = self.resolve_server()
        if p["state"] in ACTIONS:
            return self.restart()

        service = self.find(self.services())
        if p["state"] == "absent":
            return self.absent(service)

        before = view(service)
        after = dict(before)
        changed = False
        created = False
        if service is None:
            if p["type"] not in CREATABLE:
                self.module.fail_json(
                    msg="No %s service on %s, and this module can only create %s services; use the module for %s"
                    % (p["type"], self.server.get("hostname"), ", ".join(sorted(CREATABLE)), p["type"])
                )
            self.validate_create()
            changed = created = True
            after = dict(id=None, type=p["type"], server=self.server["id"], servers=[], state="enabled", running=True)

        want_running = dict(started=True, stopped=False).get(p["state"])
        if want_running is not None and after.get("running") != want_running:
            after["running"] = want_running
            changed = True

        result = dict(service=service or {})
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, **result)

        if created:
            result["task"] = self.create()
            service = self.find(self.services())
            if service is None:
                if p["wait"]:
                    self.module.fail_json(msg="croit finished creating the service but does not list it", **result)
                self.exit(changed=True, before=before, after=after, **result)
        if want_running is not None and bool(service.get("running")) != want_running:
            self.write(
                "POST",
                path_join("services", service["id"], "start" if want_running else "stop"),
                query=self.server_query(service),
            )
            if p["wait"]:
                service = self.wait_running(service["id"], want_running)
        result["service"] = self.refresh(service["id"]) or service
        self.exit(changed=True, before=before, after=after, **result)

    def validate_create(self):
        p = self.params
        if p["type"] == "mon":
            missing = [o for o in ("mon_disk", "mon_ip") if not p[o]]
            if missing:
                self.module.fail_json(msg="Creating a MON needs %s" % " and ".join(missing))
            self.mon_disk = require_disk(self, self.get_list(path_join("servers", self.server["id"], "disks")), p["mon_disk"], what="mon_disk")

    def create(self):
        p = self.params
        endpoint = path_join("servers", self.server["id"], "services", CREATABLE[p["type"]])
        if p["type"] == "mon":
            body = dict(ip=p["mon_ip"], diskId=self.mon_disk["id"])
        elif p["type"] == "mds":
            body = dict(volume=p["mds_volume"]) if p["mds_volume"] else {}
        else:
            body = None
        return self.handle_task(self.write("POST", endpoint, body=body))

    def absent(self, service):
        p = self.params
        if service is None:
            self.exit(changed=False, before={}, after={}, service={})
        if service.get("type") in CONFIRM_DELETE_TYPES and not p["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to remove %s service %s without confirm_delete=true" % (service.get("type"), service.get("id"))
            )
        before = view(service)
        query = self.server_query(service)
        after = {}
        if query and len(service.get("multiServer") or []) > 1:
            after = dict(before, servers=[s for s in before["servers"] if s != self.server["id"]])
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, service=service)
        result = dict(service=service)
        task = self.handle_task(self.write("DELETE", path_join("services", service["id"]), query=query))
        if task is not None:
            result["task"] = task
        result["service"] = self.refresh(service["id"]) or {}
        self.exit(changed=True, before=before, after=after, **result)

    def restart(self):
        p = self.params
        if p["service_id"] is not None:
            service = self.find(self.services())
            targets = [dict(id=service["id"], server=self.server_query(service) and self.server["id"])]
        elif p["type"] == "osd":
            tree = self.get("/crush") or {}
            nodes = list(tree.get("nodes") or []) + list(tree.get("stray") or [])
            targets = [
                dict(id=n["id"], isOsd=True)
                for n in sorted(nodes, key=lambda n: n["id"])
                if n.get("type") == "OSD"
                and n["id"] >= 0
                and n.get("status") != "DESTROYED"
                and (self.server is None or n.get("serverId") == self.server["id"])
            ]
        else:
            targets = []
            for s in self.services():
                if s.get("type") != p["type"]:
                    continue
                if self.server is None:
                    targets.append(dict(id=s["id"]))
                elif on_server(s, self.server["id"]):
                    targets.append(dict(id=s["id"], server=self.server["id"] if s.get("multiServer") else None))
        if not targets:
            self.module.fail_json(msg="No services match type=%s%s" % (p["type"], " on %s" % p["server"] if p["server"] else ""))
        body = [dict((k, v) for k, v in t.items() if v is not None) for t in targets]
        summary = [dict(id=t["id"], server=t.get("server"), osd=bool(t.get("isOsd"))) for t in body]
        if self.check_mode:
            self.exit(changed=True, services=summary, msg="Restart skipped in check mode")
        endpoint = "/services/rolling-restart" if p["state"] == "rolling_restarted" else "/services/restart"
        result = dict(changed=True, services=summary)
        task = self.handle_task(self.write("POST", endpoint, body=body))
        if task is not None:
            result["task"] = task
        self.exit(**result)

    def refresh(self, service_id):
        for s in self.services():
            if s.get("id") == service_id:
                return s
        return None

    def wait_running(self, service_id, running):
        deadline = time.time() + self.params["wait_timeout"]
        while True:
            service = self.refresh(service_id)
            if service is not None and bool(service.get("running")) == running:
                return service
            if time.time() >= deadline:
                self.module.fail_json(
                    msg="Timed out waiting for service %s to %s" % (service_id, "start" if running else "stop"), service=service
                )
            time.sleep(POLL_INTERVAL)


def main():
    ServiceModule().run()


if __name__ == "__main__":
    main()
