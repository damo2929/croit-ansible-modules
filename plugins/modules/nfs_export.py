#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/nfs
# croit-api: GET /services/nfs-gateways/{serviceId}
# croit-api: GET /services/nfs-gateways/{serviceId}/exports
# croit-api: POST /services/nfs-gateways/{serviceId}/exports
# croit-api: PUT /services/nfs-gateways/{serviceId}/exports/{exportId}
# croit-api: DELETE /services/nfs-gateways/{serviceId}/exports/{exportId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: nfs_export
short_description: Manage exports of a croit NFS gateway cluster
version_added: 0.1.0
description:
  - Create, update and delete the CephFS exports of a croit NFS cluster.
  - An export is identified by its O(cluster) and the O(nfs_path) clients mount, not by croit's numeric id.
  - Only options that are set are managed; anything left out keeps its current value.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  cluster:
    description:
      - The NFS cluster, by name (see M(croit.ceph.nfs_cluster)) or croit service id.
    type: str
    required: true
  nfs_path:
    description:
      - The path clients mount on the NFS server (the pseudo path), for example V(/projects).
    type: str
    required: true
  state:
    description:
      - Whether the export should exist.
      - V(absent) removes the export. Clients that mount it lose access, but no CephFS data is touched,
        so no confirmation is needed.
    type: str
    choices: [present, absent]
    default: present
  path:
    description:
      - The CephFS directory to export, for example V(/volumes/_nogroup/projects). Required to create an export.
    type: str
  volume:
    description:
      - CephFS volume to export. nfs-ganesha clusters need it when an export is created; croit-nfs serves only
        Ceph's default filesystem and takes none.
      - Fixed at creation; a different value for an existing export fails the task.
    type: str
  access:
    description:
      - The complete list of clients allowed to mount the export. Order does not matter.
      - croit creates an export without any client access when this is not set.
    type: list
    elements: dict
    suboptions:
      subnet:
        description: Client subnet such as V(10.0.0.0/24); a single address means just that host.
        type: str
        required: true
      rw:
        description: Read and write access; V(false) gives read-only access.
        type: bool
        default: false
  nfs3:
    description:
      - Serve the export over NFSv3.
    type: bool
  nfs4:
    description:
      - Serve the export over NFSv4. New exports are served over NFSv4 unless this is V(false).
    type: bool
"""

EXAMPLES = r"""
- name: Export a CephFS subvolume read-write to one subnet, read-only to another
  croit.ceph.nfs_export:
    cluster: nfs-prod
    nfs_path: /projects
    path: /volumes/_nogroup/projects
    volume: cephfs
    access:
      - {subnet: 10.0.0.0/24, rw: true}
      - {subnet: 10.1.0.0/16}

- name: Also serve NFSv3
  croit.ceph.nfs_export:
    cluster: nfs-prod
    nfs_path: /projects
    nfs3: true

- name: Remove the export
  croit.ceph.nfs_export:
    cluster: nfs-prod
    nfs_path: /projects
    state: absent
"""

RETURN = r"""
export:
  description:
    - The export as croit reports it after the change (C(NfsGatewayExport)). Before the change in check mode; empty when
      the export does not exist.
  returned: always
  type: dict
  sample:
    id: 7
    serviceId: 41
    nfsPath: /projects
    path: /volumes/_nogroup/projects
    volume: cephfs
    access: [{subnet: 10.0.0.0/24, rw: true}]
    protocols: {nfs3: false, nfs4: true}
"""

import ipaddress
import posixpath

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_one
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def normalise_path(value):
    """'/a/b/' and 'a//b' compare as '/a/b'."""
    if value is None:
        return None
    text = posixpath.normpath("/" + str(value).strip())
    return "/" + text.lstrip("/")


def normalise_subnet(value):
    text = str(value).strip()
    try:
        return str(ipaddress.ip_network(text, strict=False))
    except ValueError:
        return text


def access_set(entries):
    return sorted(set((normalise_subnet(e.get("subnet")), bool(e.get("rw"))) for e in entries or []))


def access_view(entries):
    return [dict(subnet=s, rw=rw) for s, rw in access_set(entries)]


def view(export):
    if not export:
        return {}
    protocols = export.get("protocols") or {}
    return dict(
        nfs_path=normalise_path(export.get("nfsPath")),
        path=normalise_path(export.get("path")),
        volume=export.get("volume"),
        access=access_view(export.get("access")),
        nfs3=bool(protocols.get("nfs3")),
        nfs4=bool(protocols.get("nfs4")),
    )


class NfsExportModule(CroitModule):
    def __init__(self):
        super(NfsExportModule, self).__init__(
            dict(
                cluster=dict(type="str", required=True),
                nfs_path=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                path=dict(type="str"),
                volume=dict(type="str"),
                access=dict(
                    type="list",
                    elements="dict",
                    options=dict(subnet=dict(type="str", required=True), rw=dict(type="bool", default=False)),
                ),
                nfs3=dict(type="bool"),
                nfs4=dict(type="bool"),
            ),
            wait=False,
        )

    def find_cluster(self):
        wanted = self.params["cluster"]
        clusters = self.get_list("/gateways/nfs")
        try:
            found = find_one(clusters, "NFS cluster", "description", wanted)
        except ValueError as e:
            self.module.fail_json(msg=str(e))
        if found is None and wanted.isdigit():
            found = find_one(clusters, "NFS cluster", "serviceId", int(wanted))
        if found is None:
            self.module.fail_json(
                msg="NFS cluster %r does not exist. Known clusters: %s"
                % (wanted, ", ".join("%s (%s)" % (c.get("description"), c.get("serviceId")) for c in clusters) or "none")
            )
        return found

    def find_export(self, service_id, nfs_path):
        exports = self.get_list(path_join("services", "nfs-gateways", service_id, "exports"))
        matches = [e for e in exports if normalise_path(e.get("nfsPath")) == nfs_path]
        if len(matches) > 1:
            self.module.fail_json(msg="%d exports of the cluster use nfs_path %s; remove the duplicates in croit" % (len(matches), nfs_path))
        return matches[0] if matches else None

    def run(self):
        p = self.params
        cluster = self.find_cluster()
        service_id = cluster["serviceId"]
        nfs_path = normalise_path(p["nfs_path"])
        current = self.find_export(service_id, nfs_path)

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, export={})
            if not self.check_mode:
                self.write("DELETE", path_join("services", "nfs-gateways", service_id, "exports", current["id"]))
            self.exit(changed=True, before=view(current), after={}, export={})

        if current is None:
            return self.create(cluster, nfs_path)
        return self.update(service_id, nfs_path, current)

    def create(self, cluster, nfs_path):
        p = self.params
        if not p["path"]:
            self.module.fail_json(msg="path is required to create the export %s" % nfs_path)
        implementation = cluster.get("implementation")
        if implementation == "ganesha" and not p["volume"]:
            self.module.fail_json(
                msg="NFS cluster %r runs nfs-ganesha, so volume is required to create an export" % cluster.get("description")
            )
        if implementation == "croit_nfs" and p["volume"]:
            self.module.fail_json(
                msg="NFS cluster %r runs croit-nfs, which serves only the default filesystem; leave volume unset" % cluster.get("description")
            )
        body = dict(
            nfsPath=nfs_path,
            path=normalise_path(p["path"]),
            access=access_view(p["access"]),
            protocols=dict(nfs3=bool(p["nfs3"]), nfs4=p["nfs4"] is not False),
        )
        if not (body["protocols"]["nfs3"] or body["protocols"]["nfs4"]):
            self.module.fail_json(msg="an export must be served over NFSv3, NFSv4 or both")
        if p["volume"]:
            body["volume"] = p["volume"]
        after = view(body)
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, export={})
        created = self.write("POST", path_join("services", "nfs-gateways", cluster["serviceId"], "exports"), body=body)
        export = self.find_export(cluster["serviceId"], nfs_path) or created or {}
        self.exit(changed=True, before={}, after=after, export=export)

    def update(self, service_id, nfs_path, current):
        p = self.params
        if p["volume"] is not None and (p["volume"] or None) != current.get("volume"):
            self.module.fail_json(
                msg="volume of export %s is %r and cannot be changed to %r after creation"
                % (nfs_path, current.get("volume"), p["volume"])
            )
        before = view(current)
        after = dict(before)
        if p["path"] is not None:
            after["path"] = normalise_path(p["path"])
        if p["access"] is not None:
            after["access"] = access_view(p["access"])
        if p["nfs3"] is not None:
            after["nfs3"] = p["nfs3"]
        if p["nfs4"] is not None:
            after["nfs4"] = p["nfs4"]
        if after == before:
            self.exit(changed=False, before=before, after=after, export=current)
        if not (after["nfs3"] or after["nfs4"]):
            self.module.fail_json(msg="an export must be served over NFSv3, NFSv4 or both")
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, export=current)
        # The PUT replaces the whole export, so send the merged result.
        body = dict(
            nfsPath=nfs_path,
            path=after["path"],
            access=after["access"],
            protocols=dict(nfs3=after["nfs3"], nfs4=after["nfs4"]),
        )
        self.write("PUT", path_join("services", "nfs-gateways", service_id, "exports", current["id"]), body=body)
        self.exit(changed=True, before=before, after=after, export=self.find_export(service_id, nfs_path) or current)


def main():
    NfsExportModule().run()


if __name__ == "__main__":
    main()
