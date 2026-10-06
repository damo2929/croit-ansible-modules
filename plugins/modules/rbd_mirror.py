#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /pools/{pool}/rbd-mirror
# croit-api: PATCH /pools/{pool}/rbd-mirror
# croit-api: PATCH /pools/{pool}/rbd-mirror/token
# croit-api: GET /pools/{pool}/rbd-mirror/token
# croit-api: POST /pools/{pool}/rbd-mirror/peers
# croit-api: PATCH /pools/{pool}/rbd-mirror/peers/{peerId}
# croit-api: DELETE /pools/{pool}/rbd-mirror/peers/{peerId}
# croit-api: GET /pools/rbd-mirror/schedules
# croit-api: POST /pools/rbd-mirror/schedules
# croit-api: DELETE /pools/rbd-mirror/schedules
# croit-api: GET /pools/{pool}/rbds/{rbd}
# croit-api: PATCH /pools/{pool}/rbds/{rbd}/rbd-mirror

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: rbd_mirror
short_description: Manage RBD mirroring of a pool on a croit cluster
version_added: 0.1.0
description:
  - Manages RBD mirroring of one pool (or one namespace in it). This covers the mirroring mode, the name this
    cluster goes by, the peer cluster, mirror snapshot schedules, and how individual images mirror.
  - Only the options that are set are managed.
  - "Connecting two clusters takes three steps:"
  - 1. Enable mirroring on the same pool on both clusters, with an rbd-mirror daemon running on the receiving
    side.
  - 2. Read a bootstrap token on one cluster with O(return_token=true).
  - 3. Import that token on the other cluster with O(peer). See the examples.
  - The rbd-mirror daemon itself is started with M(croit.ceph.service) (O(croit.ceph.service#module:type=rbd_mirror)).
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
  diff_mode:
    support: full
options:
  pool:
    description:
      - Name of the pool to mirror. Erasure coded pools cannot be mirrored.
    type: str
    required: true
  namespace:
    description:
      - Namespace within the pool whose mirroring is managed. The pool's default namespace when not set.
    type: str
  mode:
    description:
      - V(pool) mirrors every image with journaling enabled; V(image) mirrors only the images enabled one by one;
        V(disabled) turns mirroring off.
      - Turning mirroring off removes the pool's peers and needs every mirrored image disabled. croit confirms
        it with a warning, see O(ignore_warnings).
    type: str
    choices: [disabled, pool, image]
  site_name:
    description:
      - The name this cluster goes by on its peers. Needs mirroring enabled on the pool.
    type: str
  peer:
    description:
      - The peer cluster of the pool. ceph supports one peer per pool, so registering a new one replaces the old one.
      - Peers are identified by O(peer.site_name).
    type: dict
    suboptions:
      site_name:
        description: What to call the peer on this cluster. Identifies the peer.
        type: str
        required: true
      token:
        description:
          - Bootstrap token produced on the peer cluster (see O(return_token)). Needed only to register the peer;
            it carries the peer's mon addresses and a ceph key, so keep it in a vault.
        type: str
      direction:
        description: Which way data flows. ceph uses V(rx-tx) when not set.
        type: str
        choices: [rx-tx, rx-only, tx-only]
      local_site_name:
        description: What this cluster should be called on the peer. Only used when registering the peer.
        type: str
      state:
        description: Whether the peer should be registered.
        type: str
        choices: [present, absent]
        default: present
  schedules:
    description:
      - Mirror snapshot schedules at the pool (or namespace) level. They only affect images mirroring in snapshot mode.
      - Listed schedules are added when missing; others at this level are removed only with O(purge_schedules=true).
    type: list
    elements: dict
    suboptions:
      interval:
        description: How often, as a number and a unit such as V(30m), V(12h) or V(7d).
        type: str
        required: true
      start_time:
        description: When the first snapshot of a day is due, such as V(14:00:00).
        type: str
  purge_schedules:
    description:
      - Remove pool (or namespace) level schedules that are not listed in O(schedules).
    type: bool
    default: false
  images:
    description:
      - How individual images mirror. Only possible on a pool in V(image) mode.
    type: list
    elements: dict
    suboptions:
      name:
        description: Name of the image within O(pool) and O(namespace).
        type: str
        required: true
      mode:
        description:
          - How the image mirrors. V(disabled) stops mirroring it.
          - V(journal) also enables the image's journaling feature, which journal mode replicates.
        type: str
        choices: [disabled, journal, snapshot]
      primary:
        description: Whether this cluster's copy is the one being written to (promote or demote).
        type: bool
  return_token:
    description:
      - Return a bootstrap token for this pool in RV(bootstrap_token), to import on the peer cluster.
      - The token is a secret; use C(no_log) on the task that registers it.
      - Not done in check mode, because ceph creates the peer key the token carries the first time.
    type: bool
    default: false
notes:
  - The bootstrap token carries the peer's monitor addresses and a Ceph key. Never put it in a playbook in
    clear text, and use C(no_log) on tasks that read or register it.
  - Turning mirroring off on a pool removes its peers.
seealso:
  - module: croit.ceph.service
    description: Start the rbd-mirror daemon on the receiving cluster.
  - module: croit.ceph.rbd
    description: Create the images that are mirrored.
  - name: croit API reference
    description: The C(/pools/{pool}/rbd-mirror) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph RBD mirroring
    description: Upstream documentation of RBD mirroring modes, peers and schedules.
    link: https://docs.ceph.com/en/latest/rbd/rbd-mirroring/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

# On the backup cluster: enable mirroring and hand out a token
- name: Enable mirroring and get a token
  croit.ceph.rbd_mirror:
    pool: rbd
    mode: image
    site_name: backup
    return_token: true
  register: backup
  no_log: true

# On the primary cluster: import the token and mirror two images by snapshot
- name: Connect the primary to the backup cluster
  croit.ceph.rbd_mirror:
    pool: rbd
    mode: image
    site_name: primary
    peer:
      site_name: backup
      token: "{{ backup.bootstrap_token }}"
      direction: tx-only
    schedules:
      - interval: 1h
    images:
      - {name: vm-disk-01, mode: snapshot}
      - {name: vm-disk-02, mode: snapshot}
  no_log: true

- name: Read the mirroring state
  croit.ceph.rbd_mirror:
    pool: rbd
  register: mirroring

- name: Show how the rbd-mirror daemon sees the pool
  ansible.builtin.debug:
    msg: "{{ mirroring.mirror.statusHealth }}"

- name: Fail over to the backup cluster
  croit.ceph.rbd_mirror:
    pool: rbd
    images:
      - {name: vm-disk-01, primary: true}
"""

RETURN = r"""
mirror:
  description:
    - The pool's mirroring as croit reports it after the change (C(RbdMirrorPoolInfo) in the croit API).
    - In check mode, the mirroring before the change.
  returned: always
  type: dict
  contains:
    pool:
      description: The pool this is about.
      returned: always
      type: str
      sample: rbd
    namespace:
      description: The namespace, or V(null) for the pool itself.
      returned: always
      type: str
      sample: null
    poolMirrorMode:
      description: The mirroring mode, V(disabled), V(pool) or V(image).
      returned: always
      type: str
      sample: image
    siteName:
      description: What this cluster calls itself to its peers, or V(null).
      returned: always
      type: str
      sample: primary
    peers:
      description: The registered peer clusters, each with C(id), C(siteName), C(direction) and C(clientName).
      returned: always
      type: list
      elements: dict
      sample:
        - id: 5f8a2c1e-0000-4000-8000-000000000001
          siteName: backup
          direction: tx-only
          clientName: client.rbd-mirror-peer
    statusHealth:
      description: What the rbd-mirror daemon makes of the pool, or V(null) while mirroring is off.
      returned: always
      type: str
      sample: OK
    statusStates:
      description: How many images are in each mirroring state, or V(null) while mirroring is off.
      returned: always
      type: dict
      sample:
        replaying: 2
bootstrap_token:
  description:
    - A bootstrap token for the pool, to import on the peer cluster with O(peer.token). B(Secret.)
    - Returned unmasked so it can be used; set C(no_log) on the task.
  returned: when O(return_token=true) and not in check mode
  type: str
  sample: "********"
task:
  description: The croit background task the last change ran as.
  returned: when a change ran as a croit task
  type: dict
  contains:
    id:
      description: The task's id, usable with M(croit.ceph.task).
      returned: always
      type: int
      sample: 421
    state:
      description: The task's state; V(FINISHED) after a successful wait.
      returned: always
      type: str
      sample: FINISHED
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import CroitError, CroitWarning, path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def schedule_key(entry):
    return (str(entry.get("interval")).strip(), entry.get("startTime") or None)


class RbdMirrorModule(CroitModule):
    def __init__(self):
        super(RbdMirrorModule, self).__init__(
            dict(
                pool=dict(type="str", required=True),
                namespace=dict(type="str"),
                mode=dict(type="str", choices=["disabled", "pool", "image"]),
                site_name=dict(type="str"),
                peer=dict(
                    type="dict",
                    options=dict(
                        site_name=dict(type="str", required=True),
                        token=dict(type="str", no_log=True),
                        direction=dict(type="str", choices=["rx-tx", "rx-only", "tx-only"]),
                        local_site_name=dict(type="str"),
                        state=dict(type="str", default="present", choices=["present", "absent"]),
                    ),
                ),
                schedules=dict(
                    type="list",
                    elements="dict",
                    options=dict(interval=dict(type="str", required=True), start_time=dict(type="str")),
                ),
                purge_schedules=dict(type="bool", default=False),
                images=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        name=dict(type="str", required=True),
                        mode=dict(type="str", choices=["disabled", "journal", "snapshot"]),
                        primary=dict(type="bool"),
                    ),
                ),
                return_token=dict(type="bool", default=False, no_log=False),
            ),
        )
        p = self.params
        self.namespace = p["namespace"] or None
        self.query = dict(namespace=self.namespace) if self.namespace else None
        self.mirror_path = path_join("pools", p["pool"], "rbd-mirror")
        self.task = None

    # Reads ----------------------------------------------------------------

    def info(self):
        info = self.get_or_none(self.mirror_path, query=self.query)
        if info is None:
            self.module.fail_json(
                msg="croit cannot mirror pool %r%s: it does not exist or is erasure coded"
                % (self.params["pool"], " namespace %r" % self.namespace if self.namespace else "")
            )
        return info

    def level_schedules(self):
        return [
            s
            for s in self.get_list("/pools/rbd-mirror/schedules")
            if s.get("pool") == self.params["pool"] and (s.get("namespace") or None) == self.namespace and not s.get("rbd")
        ]

    def image(self, name):
        image = self.get_or_none(path_join("pools", self.params["pool"], "rbds", name), query=self.query)
        if image is None:
            self.module.fail_json(msg="Image %r does not exist in pool %r" % (name, self.params["pool"]))
        return image

    # Writes ---------------------------------------------------------------

    def apply(self, method, path, body=None, query=None):
        task = self.handle_task(self.write(method, path, body=body, query=query))
        if task is not None:
            self.task = task

    # Planning -------------------------------------------------------------

    def plan(self):
        """Compute before/after views and the list of writes to make, in order."""
        p = self.params
        info = self.info()
        before, after, early, late = {}, {}, [], []
        current_mode = info.get("poolMirrorMode")
        effective_mode = p["mode"] or current_mode

        if p["mode"] is not None:
            before["mode"], after["mode"] = current_mode, p["mode"]
            if current_mode != p["mode"]:
                step = ("PATCH", self.mirror_path, dict(poolMirrorMode=p["mode"]), self.query)
                (late if p["mode"] == "disabled" else early).append(step)

        if p["site_name"] is not None:
            before["site_name"], after["site_name"] = info.get("siteName"), p["site_name"]
            if info.get("siteName") != p["site_name"]:
                if effective_mode == "disabled":
                    self.module.fail_json(msg="site_name needs mirroring enabled on the pool")
                early.append(("PATCH", self.mirror_path + "/token", dict(siteName=p["site_name"]), None))

        if p["peer"] is not None:
            early.extend(self.plan_peer(info, before, after, effective_mode))

        if p["schedules"] is not None or p["purge_schedules"]:
            early.extend(self.plan_schedules(before, after))

        if p["images"]:
            # After the pool is enabled (early), and before it is disabled (late).
            early.extend(self.plan_images(before, after, effective_mode))
        return info, before, after, early + late

    def plan_peer(self, info, before, after, effective_mode):
        wanted = self.params["peer"]
        peers = info.get("peers") or []
        current = next((x for x in peers if x.get("siteName") == wanted["site_name"]), None)
        before["peers"] = sorted("%s (%s)" % (x.get("siteName"), x.get("direction")) for x in peers)
        steps = []
        if wanted["state"] == "absent":
            after["peers"] = [x for x in before["peers"] if not x.startswith("%s (" % wanted["site_name"])]
            if current is not None:
                steps.append(("DELETE", path_join("pools", self.params["pool"], "rbd-mirror", "peers", current["id"]), None, None))
            return steps
        if effective_mode == "disabled":
            self.module.fail_json(msg="A peer needs mirroring enabled on the pool")
        direction = wanted["direction"] or (current or {}).get("direction") or "rx-tx"
        after["peers"] = ["%s (%s)" % (wanted["site_name"], direction)]
        if current is None:
            if not wanted["token"]:
                self.module.fail_json(msg="peer.token is needed to register peer %r" % wanted["site_name"])
            body = dict(peerToken=wanted["token"], siteName=wanted["site_name"])
            if wanted["direction"]:
                body["direction"] = wanted["direction"]
            if wanted["local_site_name"]:
                body["localSiteName"] = wanted["local_site_name"]
            steps.append(("POST", self.mirror_path + "/peers", body, None))
        elif wanted["direction"] and current.get("direction") != wanted["direction"]:
            steps.append(
                (
                    "PATCH",
                    path_join("pools", self.params["pool"], "rbd-mirror", "peers", current["id"]),
                    dict(direction=wanted["direction"]),
                    None,
                )
            )
        return steps

    def plan_schedules(self, before, after):
        current = self.level_schedules()
        have = set(schedule_key(s) for s in current)
        wanted = [dict(interval=s["interval"].strip(), startTime=s.get("start_time") or None) for s in self.params["schedules"] or []]
        want = set(schedule_key(s) for s in wanted)
        base = dict(pool=self.params["pool"], namespace=self.namespace)
        steps = []
        for entry in wanted:
            if schedule_key(entry) not in have:
                steps.append(("POST", "/pools/rbd-mirror/schedules", dict(base, **entry), None))
        remaining = set(have)
        if self.params["purge_schedules"]:
            for entry in current:
                if schedule_key(entry) not in want:
                    body = dict(base, interval=entry.get("interval"), startTime=entry.get("startTime"))
                    steps.append(("DELETE", "/pools/rbd-mirror/schedules", body, None))
                    remaining.discard(schedule_key(entry))
        fmt = sorted("%s%s" % (k[0], " at %s" % k[1] if k[1] else "") for k in have)
        before["schedules"] = fmt
        after["schedules"] = sorted("%s%s" % (k[0], " at %s" % k[1] if k[1] else "") for k in remaining | want)
        return steps

    def plan_images(self, before, after, effective_mode):
        before["images"], after["images"] = {}, {}
        steps = []
        for wanted in self.params["images"]:
            image = self.image(wanted["name"])
            mirror = image.get("mirrorInfo") or {}
            current = dict(mode=mirror.get("imageMirrorMode"), primary=mirror.get("primary"))
            target = dict(current)
            body = {}
            if wanted["mode"] is not None and wanted["mode"] != current["mode"]:
                # Disabling is always allowed (it runs before a pool is disabled); enabling needs image mode.
                if wanted["mode"] != "disabled" and effective_mode != "image":
                    self.module.fail_json(msg="Image %r can only change its mirroring mode on a pool in image mode" % wanted["name"])
                body["imageMirrorMode"] = wanted["mode"]
                target["mode"] = wanted["mode"]
                features = [str(f).upper() for f in image.get("features") or []]
                if wanted["mode"] == "journal" and "JOURNALING" not in features:
                    body["journaling"] = True
            if wanted["primary"] is not None and wanted["primary"] != current["primary"]:
                body["primary"] = wanted["primary"]
                target["primary"] = wanted["primary"]
            before["images"][wanted["name"]] = current
            after["images"][wanted["name"]] = target
            if body:
                steps.append(
                    ("PATCH", path_join("pools", self.params["pool"], "rbds", wanted["name"], "rbd-mirror"), body, self.query)
                )
        return steps

    # Main -----------------------------------------------------------------

    def bootstrap_token(self):
        try:
            return self.client.request(
                "GET", self.mirror_path + "/token", ignore_warnings=self.params["ignore_warnings"]
            )[1]
        except CroitWarning as e:
            self.module.fail_json(msg="%s. Re-run with ignore_warnings=true to confirm it." % e.message, warning=e.warning_text)
        except CroitError as e:
            self.fail_from(e)

    def run(self):
        p = self.params
        info, before, after, steps = self.plan()
        changed = bool(steps)
        result = dict(mirror=info)
        if self.check_mode:
            self.exit(changed=changed, before=before, after=after, **result)
        for method, path, body, query in steps:
            self.apply(method, path, body=body, query=query)
        if changed:
            result["mirror"] = self.info()
        if self.task is not None:
            result["task"] = self.task
        if p["return_token"]:
            result["bootstrap_token"] = self.bootstrap_token()
        self.exit(changed=changed, before=before, after=after, **result)


def main():
    RbdMirrorModule().run()


if __name__ == "__main__":
    main()
