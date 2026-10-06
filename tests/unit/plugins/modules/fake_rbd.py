# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stateful fake of croit's pool QoS, RBD image, snapshot and namespace endpoints."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit

MIB = 1024 * 1024
QOS_COMMANDS = [
    "rbd_qos_iops_limit",
    "rbd_qos_bps_limit",
    "rbd_qos_read_iops_limit",
    "rbd_qos_write_iops_limit",
    "rbd_qos_read_bps_limit",
    "rbd_qos_write_bps_limit",
]
SEG = "(?P<%s>[^/]+)"


def qos_rows(values, inherited=None):
    return [
        dict(
            setting=dict(command=c, displayName=c, description=c),
            value=values.get(c),
            inherited=(inherited or {}).get(c),
        )
        for c in QOS_COMMANDS
    ]


class RbdCluster(FakeCroit):
    def __init__(self, pools=("rbd",)):
        super(RbdCluster, self).__init__()
        self.pools = list(pools)
        self.namespaces = dict((p, set()) for p in pools)
        self.images = {}
        self.image_qos = {}
        self.pool_qos = dict((p, {}) for p in pools)
        self.next_snap = 1
        self.serve_tasks()

        self.route("GET", "/pools", lambda call: (200, [dict(name=p, poolId=i) for i, p in enumerate(self.pools)]))
        self.route("GET", "/rbds/rbd-names", self.names)
        self.route("GET", "/rbds/rbd-infos", self.infos)
        self.route("POST", "/pools/%s/rbds" % (SEG % "pool"), self.create)
        img = "/pools/%s/rbds/%s" % (SEG % "pool", SEG % "rbd")
        self.route("GET", img, self.get_image)
        self.route("PATCH", img, self.patch_image)
        self.route("DELETE", img, self.delete_image)
        self.route("POST", img + "/flatten", self.flatten)
        self.route("GET", img + "/qos", self.get_image_qos)
        self.route("POST", img + "/qos", self.set_image_qos)
        snap = img + "/snapshots/" + SEG % "snap"
        self.route("PUT", snap, self.take_snap)
        self.route("PATCH", snap, self.patch_snap)
        self.route("DELETE", snap, self.delete_snap)
        self.route("POST", snap + "/clone", self.clone)
        self.route("GET", "/pools/%s/qos" % (SEG % "pool"), self.get_pool_qos)
        self.route("POST", "/pools/%s/qos" % (SEG % "pool"), self.set_pool_qos)
        ns = "/pools/%s/rbd-namespaces" % (SEG % "pool")
        self.route("GET", ns, lambda call, pool: (200, [dict(name=n) for n in sorted(self.namespaces[pool])]))
        self.route("PUT", ns + "/" + SEG % "namespace", self.put_ns)
        self.route("DELETE", ns + "/" + SEG % "namespace", self.delete_ns)

    # helpers ---------------------------------------------------------------

    @staticmethod
    def ns(call):
        return call.query.get("namespace") or None

    def add_image(self, pool, name, size, namespace=None, features=None, parent=None, ec=None, snaps=None):
        key = (pool, namespace, name)
        self.images[key] = dict(
            name=name,
            pool=pool,
            namespace=namespace,
            size=-(-size // MIB) * MIB,
            sizeFormatted="",
            features=sorted(features if features is not None else ["LAYERING", "EXCLUSIVE_LOCK"]),
            erasureCodedPool=ec,
            parent=parent,
            snaps=snaps or [],
            mirrorInfo=dict(imageMirrorMode="disabled", mirrorState="disabled"),
            withDetails=True,
            hints=[],
        )
        self.image_qos[key] = {}
        if namespace:
            self.namespaces[pool].add(namespace)
        return self.images[key]

    def image(self, call, pool, rbd):
        return self.images.get((pool, self.ns(call), rbd))

    # routes ----------------------------------------------------------------

    def names(self, call):
        return 200, [dict(pool=p, namespace=n, rbd=r) for (p, n, r) in sorted(self.images, key=str)]

    def infos(self, call):
        wanted = call.query.get("image")
        wanted = wanted if isinstance(wanted, list) else [wanted]
        result = {}
        for ref in wanted:
            parts = ref.split("/")
            key = (parts[0], parts[1] if len(parts) == 3 else None, parts[-1])
            if key in self.images:
                image = copy.deepcopy(self.images[key])
                image["snaps"] = None
                result[ref] = image
        return 200, result

    def create(self, call, pool):
        body = call.body
        if (pool, body.get("namespace"), body["name"]) in self.images:
            return 400, dict(code=400, message="exists")
        self.add_image(
            pool,
            body["name"],
            body["size"],
            namespace=body.get("namespace"),
            features=body.get("features"),
            ec=body.get("erasureCodedPool"),
        )
        return 204, None

    def get_image(self, call, pool, rbd):
        image = self.image(call, pool, rbd)
        if image is None:
            return 404, dict(code=404, message="no such image")
        return 200, copy.deepcopy(image)

    def patch_image(self, call, pool, rbd):
        image = self.image(call, pool, rbd)
        body = call.body
        if body.get("size") is not None:
            if body["size"] < image["size"]:
                return 400, dict(code=400, message="cannot shrink")
            image["size"] = body["size"]
        if body.get("features") is not None:
            image["features"] = sorted(body["features"])
        return 204, None

    def delete_image(self, call, pool, rbd):
        image = self.image(call, pool, rbd)
        if image["snaps"]:
            return 400, dict(code=400, message="image has snapshots")
        del self.images[(pool, self.ns(call), rbd)]
        return 200, self.new_task("Delete image", rbd)

    def flatten(self, call, pool, rbd):
        self.image(call, pool, rbd)["parent"] = None
        return 200, self.new_task("Flatten", rbd)

    def get_image_qos(self, call, pool, rbd):
        return 200, qos_rows(self.image_qos[(pool, self.ns(call), rbd)], self.pool_qos[pool])

    def set_image_qos(self, call, pool, rbd):
        return 200, self._set_qos(self.image_qos[(pool, self.ns(call), rbd)], call.body)

    def get_pool_qos(self, call, pool):
        return 200, qos_rows(self.pool_qos[pool])

    def set_pool_qos(self, call, pool):
        return 200, self._set_qos(self.pool_qos[pool], call.body)

    @staticmethod
    def _set_qos(store, body):
        applied = []
        for row in body:
            if row["command"] not in QOS_COMMANDS:
                applied.append(dict(command=row["command"], success=False, errorMessage="unknown"))
                continue
            if row.get("limit") is None:
                store.pop(row["command"], None)
            else:
                store[row["command"]] = row["limit"]
            applied.append(dict(command=row["command"], success=True, errorMessage=""))
        return applied

    def take_snap(self, call, pool, rbd, snap):
        image = self.image(call, pool, rbd)
        if any(s["name"] == snap for s in image["snaps"]):
            return 400, dict(code=400, message="exists")
        self.next_snap += 1
        image["snaps"].append(dict(id=self.next_snap, name=snap, protect=False))
        return 204, None

    def _snap(self, call, pool, rbd, snap):
        for s in self.image(call, pool, rbd)["snaps"]:
            if s["name"] == snap:
                return s
        return None

    def patch_snap(self, call, pool, rbd, snap):
        s = self._snap(call, pool, rbd, snap)
        if call.body.get("protect") is not None:
            s["protect"] = call.body["protect"]
        return 204, None

    def delete_snap(self, call, pool, rbd, snap):
        s = self._snap(call, pool, rbd, snap)
        if s["protect"]:
            return 400, dict(code=400, message="snapshot is protected")
        self.image(call, pool, rbd)["snaps"].remove(s)
        return 204, None

    def clone(self, call, pool, rbd, snap):
        parent = self.image(call, pool, rbd)
        body = call.body
        self.add_image(
            body["pool"],
            body["name"],
            parent["size"],
            namespace=body.get("namespace"),
            features=parent["features"],
            parent=dict(pool=pool, image=rbd, snapshot=snap),
        )
        return 204, None

    def put_ns(self, call, pool, namespace):
        self.namespaces[pool].add(namespace)
        return 204, None

    def delete_ns(self, call, pool, namespace):
        if any(k[0] == pool and k[1] == namespace for k in self.images):
            return 400, dict(code=400, message="namespace not empty")
        self.namespaces[pool].discard(namespace)
        return 204, None
