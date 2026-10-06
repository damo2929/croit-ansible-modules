#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /s3/multisite/status
# croit-api: POST /s3/multisite/primary
# croit-api: GET /s3/multisite/primary/token
# croit-api: POST /s3/multisite/secondary
# croit-api: POST /s3/multisite/promote
# croit-api: PATCH /s3/multisite/readonly
# croit-api: PATCH /s3/multisite/endpoints

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: s3_multisite
short_description: Manage the S3 multisite role of a croit cluster
version_added: 0.1.0
description:
  - Puts a croit cluster's S3 into a multisite setup as the primary or as a secondary, promotes a secondary,
    sets a secondary's read-only flag and rewrites the endpoints other sites reach it on.
  - The cluster is identified by the connection options; its current role is read from croit's multisite status,
    so a converged cluster is not touched again. Options that are not set are left alone.
  - "Role changes: a standalone cluster becomes the V(primary) (convert) or joins another site's setup as a
    V(secondary) (join); a secondary becomes the V(primary) (promote, for failover and failback)."
  - Role changes are one-way and cluster-wide, need O(confirm_action=true), and are never made in check mode.
    croit restarts the S3 gateways one after another while they run. Promoting a site that is behind on sync
    loses the writes it has not received; croit warns first, which needs O(ignore_warnings=true).
  - A cluster cannot leave a multisite setup through croit. A primary becomes a secondary only when another site
    is promoted, so asking for that fails.
  - "Two-cluster flow: 1. On site A, O(role=primary) with O(endpoints), O(sync_user) and O(return_token=true).
    2. On site B (no S3 yet), O(role=secondary) with O(zone), O(endpoints) and the O(token) from step 1.
    3. On site B, add gateways with M(croit.ceph.rgw_service)."
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
      - Role changes and O(update_endpoints=true) report a change and are skipped in check mode.
  diff_mode:
    support: full
options:
  role:
    description:
      - The multisite role this cluster should have. When not set, the role is left alone.
      - See the description for which changes are possible. A primary cannot be turned into a secondary here.
    type: str
    choices: [primary, secondary]
  endpoints:
    description:
      - Where the other sites reach this cluster's S3, as C(http(s)://host:port). List every S3 gateway of
        this site. A secondary handed only some of them syncs only from those.
      - Required to become the primary or to join as a secondary.
      - croit does not report the stored endpoints, so on a cluster that already has its role they are only
        sent with O(update_endpoints=true).
    type: list
    elements: str
  update_endpoints:
    description:
      - Rewrite the stored endpoints with O(endpoints) and commit the period, for example after gateways were
        added or moved.
      - This is a one-shot action. It always reports a change, is skipped in check mode and needs O(endpoints).
    type: bool
    default: false
  sync_user:
    description:
      - S3 user id croit creates as the system user the sites replicate as.
      - Required to become the primary; ignored otherwise.
    type: str
  zone:
    description:
      - Name of this cluster's new zone when joining as a secondary. It must not be used by another site.
      - Required to join as a secondary; ignored otherwise.
    type: str
  token:
    description:
      - Base64 token from the primary site (RV(token) with O(return_token=true) there). It carries the sync user's
        secret key and is never logged.
      - When joining as a secondary, give exactly one of O(token) and O(primary_connection).
      - When promoting after a long outage, the token of whichever site holds the master role, so the stale
        realm is pulled first. Leave unset for an ordinary failover.
    type: str
  primary_connection:
    description:
      - The primary's details spelled out, when the primary is not managed by croit.
      - Alternative to O(token) when joining as a secondary; ignored otherwise.
    type: dict
    suboptions:
      realm:
        description: The realm's name on the primary.
        type: str
        required: true
      zonegroup:
        description: The zonegroup's name on the primary.
        type: str
        required: true
      access_key:
        description: The access key of the sync user, a system user on the primary.
        type: str
        required: true
      secret_key:
        description: The secret key of the sync user. It is never logged.
        type: str
        required: true
      endpoints:
        description: Where this site reaches the primary's S3, as C(http(s)://host:port), tried in order.
        type: list
        elements: str
        required: true
  pull_from_peer:
    description:
      - The current master spelled out, when it is not managed by croit, to pull a stale realm from when
        promoting. Alternative to O(token).
    type: dict
    suboptions:
      url:
        description: A peer RGW endpoint to pull the realm from, as C(http(s)://host:port).
        type: str
        required: true
      access_key:
        description: The access key of the multisite sync user on the peer site.
        type: str
        required: true
      secret_key:
        description: The secret key of that sync user. It is never logged.
        type: str
        required: true
  readonly:
    description:
      - Whether this secondary refuses S3 writes and only pulls from the primary. V(false) makes it
        active-active. Only a secondary has the flag; V(true) on a primary fails.
      - When joining, it is sent with the join. Otherwise it is compared with croit's status and changed in place.
    type: bool
  return_token:
    description:
      - Return the token secondaries join with as RV(token). Only a primary has one.
      - The token is a secret that grants read and write access to this cluster's S3. It is returned unmasked,
        so set C(no_log) on the task.
      - Not available in check mode when the cluster only becomes the primary in that run.
    type: bool
    default: false
  confirm_action:
    description:
      - Must be V(true) to convert, join or promote. These are one-way, cluster-wide changes.
      - Without it the module fails before any change, in check mode as well.
    type: bool
    default: false
notes:
  - The token, the sync user's secret keys and O(primary_connection) / O(pull_from_peer) secrets are never shown in
    logs or diffs. RV(token) is returned unmasked on purpose, so protect the task with C(no_log).
  - croit restarts the S3 gateways of the site one after another during a role change, so S3 clients see brief
    interruptions.
seealso:
  - module: croit.ceph.rgw_bootstrap
    description: Bootstrap S3 on the site that becomes the primary.
  - module: croit.ceph.rgw_service
    description: Add the gateways of a site after it joined as a secondary.
  - module: croit.ceph.s3_placement
    description: Manage placement rules, which croit refuses to change once a cluster is in a multisite setup.
  - name: croit API reference
    description: The croit REST API, including the C(/s3/multisite) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph RGW multi-site
    description: Upstream documentation of RGW realms, zonegroups, zones and multi-site sync.
    link: https://docs.ceph.com/en/latest/radosgw/multisite/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
# The join example targets a second cluster, so it sets that cluster's api_url and api_token itself.

- name: Make site A the multisite primary and fetch the join token
  croit.ceph.s3_multisite:
    role: primary
    endpoints:
      - http://10.1.0.11:80
      - http://10.1.0.12:80
    sync_user: multisite-sync
    return_token: true
    confirm_action: true
  register: site_a
  no_log: true

- name: Join site B as a read-only secondary
  croit.ceph.s3_multisite:
    api_url: https://croit-b/api
    api_token: "{{ vault_croit_b_token }}"
    role: secondary
    zone: site-b
    endpoints:
      - http://10.2.0.11:80
    token: "{{ site_a.token }}"
    readonly: true
    confirm_action: true

- name: Read the sync state of this site
  croit.ceph.s3_multisite:
  register: sync

- name: Show how many data shards are still behind
  ansible.builtin.debug:
    msg: "{{ sync.multisite.metrics.data.behindShards | default('n/a') }} data shard(s) behind"

- name: Fail over by promoting this secondary, accepting croit's sync warning
  croit.ceph.s3_multisite:
    role: primary
    confirm_action: true
    ignore_warnings: true

- name: Make the secondary active-active
  croit.ceph.s3_multisite:
    readonly: false

- name: Rewrite the endpoints after adding a gateway
  croit.ceph.s3_multisite:
    endpoints:
      - http://10.1.0.11:80
      - http://10.1.0.12:80
      - http://10.1.0.13:80
    update_endpoints: true

- name: Rewrite the endpoints for gateways reached over IPv6 (address literals in brackets)
  croit.ceph.s3_multisite:
    endpoints:
      - http://[2001:db8:1::11]:80
      - http://[2001:db8:1::12]:80
    update_endpoints: true
"""

RETURN = r"""
multisite:
  description:
    - croit's multisite status (C(RgwMultisiteStatusResponse) in the croit API) after the run.
    - In check mode, the status as it was before.
  returned: always
  type: dict
  contains:
    enabled:
      description: Whether the cluster takes part in a multisite setup at all.
      returned: always
      type: bool
      sample: true
    type:
      description: Which side of the setup the cluster is, V(PRIMARY), V(SECONDARY) or V(UNKNOWN) (a secondary whose sync status could not be read).
      returned: always
      type: str
      sample: SECONDARY
    readonly:
      description: Whether this zone refuses S3 writes. Only meaningful for a secondary, null otherwise.
      returned: always
      type: bool
      sample: true
    metrics:
      description: How far behind the sync of a secondary is, with C(data) and C(metadata), each with C(behindShards) and C(lastSync).
      returned: always
      type: dict
      sample:
        data:
          behindShards: 0
        metadata:
          behindShards: 0
token:
  description:
    - The base64 token secondaries join with. It is a secret that grants read and write access to this cluster's S3,
      and it is returned unmasked, so protect the task with C(no_log).
  returned: when O(return_token=true) and the cluster is (or, outside check mode, became) the primary
  type: str
  sample: "********"
tasks:
  description: Every croit background task the changes ran as, in order.
  returned: when a change ran as one or more croit background tasks
  type: list
  elements: dict
  sample:
    - id: 412
      name: Convert S3 to multisite primary
      state: FINISHED
      done: true
task:
  description:
    - The last croit background task the changes ran as (C(ManagedTask) in the croit API).
    - With O(wait=true) this is the finished task; with O(wait=false) it may still be running.
  returned: when the change ran as a croit background task
  type: dict
  contains:
    id:
      description: The task's id, usable with M(croit.ceph.task) and M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as croit's task list shows it.
      returned: always
      type: str
      sample: Convert S3 to multisite primary
    state:
      description: The task's state, one of V(WAITING), V(RUNNING), V(FINISHED), V(FAILED) or V(CANCELED).
      returned: always
      type: str
      sample: FINISHED
    done:
      description: Whether the task has ended.
      returned: always
      type: bool
      sample: true
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: Creating user backup ... done
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def current_role(status):
    if not status.get("enabled"):
        return "standalone"
    # UNKNOWN is a secondary whose sync status could not be read.
    return "primary" if status.get("type") == "PRIMARY" else "secondary"


def normalise_endpoints(endpoints):
    return [e.strip().rstrip("/") for e in endpoints or []]


class S3MultisiteModule(CroitModule):
    def __init__(self):
        super(S3MultisiteModule, self).__init__(
            dict(
                role=dict(type="str", choices=["primary", "secondary"]),
                endpoints=dict(type="list", elements="str"),
                update_endpoints=dict(type="bool", default=False),
                sync_user=dict(type="str"),
                zone=dict(type="str"),
                token=dict(type="str", no_log=True),
                primary_connection=dict(
                    type="dict",
                    options=dict(
                        realm=dict(type="str", required=True),
                        zonegroup=dict(type="str", required=True),
                        access_key=dict(type="str", required=True, no_log=False),
                        secret_key=dict(type="str", required=True, no_log=True),
                        endpoints=dict(type="list", elements="str", required=True),
                    ),
                ),
                pull_from_peer=dict(
                    type="dict",
                    options=dict(
                        url=dict(type="str", required=True),
                        access_key=dict(type="str", required=True, no_log=False),
                        secret_key=dict(type="str", required=True, no_log=True),
                    ),
                ),
                readonly=dict(type="bool"),
                return_token=dict(type="bool", default=False),
                confirm_action=dict(type="bool", default=False),
            ),
            mutually_exclusive=[("token", "primary_connection"), ("token", "pull_from_peer")],
        )
        self.tasks = []

    def status(self):
        return self.get("/s3/multisite/status") or {}

    def run_task(self, data):
        task = self.handle_task(data)
        if task is not None:
            self.tasks.append(task)

    def require_confirm(self, what):
        if not self.params["confirm_action"]:
            self.module.fail_json(msg="Refusing to %s without confirm_action=true; it is one-way and cluster-wide" % what)

    def plan_transition(self, role, wanted):
        """Validate the role change and return (description, method, path, body), or None."""
        p = self.params
        if wanted is None or wanted == role:
            return None
        if role == "primary" and wanted == "secondary":
            self.module.fail_json(
                msg="This cluster is the multisite primary. It becomes a secondary only when another site is promoted."
            )
        if role == "standalone" and wanted == "primary":
            missing = [o for o in ("endpoints", "sync_user") if not p[o]]
            if missing:
                self.module.fail_json(
                    msg="%s %s required to make this cluster the multisite primary"
                    % (" and ".join(missing), "is" if len(missing) == 1 else "are")
                )
            self.require_confirm("make this cluster the multisite primary")
            body = dict(endpoints=normalise_endpoints(p["endpoints"]), syncUser=p["sync_user"])
            return "convert to primary", "/s3/multisite/primary", body
        if role == "standalone" and wanted == "secondary":
            missing = [o for o in ("zone", "endpoints") if not p[o]]
            if missing:
                self.module.fail_json(msg="%s required to join as a secondary" % ", ".join(missing))
            if bool(p["token"]) == bool(p["primary_connection"]):
                self.module.fail_json(msg="Give exactly one of token and primary_connection to join as a secondary")
            self.require_confirm("join this cluster to a multisite setup as a secondary")
            body = dict(zone=p["zone"], endpoints=normalise_endpoints(p["endpoints"]))
            if p["readonly"] is not None:
                body["readonly"] = p["readonly"]
            if p["token"]:
                body["token"] = p["token"]
            else:
                conn = p["primary_connection"]
                body["primaryConnection"] = dict(
                    realm=conn["realm"],
                    zoneGroup=conn["zonegroup"],
                    accessKey=conn["access_key"],
                    secretKey=conn["secret_key"],
                    endpoints=normalise_endpoints(conn["endpoints"]),
                )
            return "join as secondary", "/s3/multisite/secondary", body
        # secondary -> primary
        self.require_confirm("promote this site to the multisite primary")
        body = {}
        if p["token"]:
            body["token"] = p["token"]
        elif p["pull_from_peer"]:
            peer = p["pull_from_peer"]
            body["pullFromPeer"] = dict(url=peer["url"], accessKey=peer["access_key"], secretKey=peer["secret_key"])
        return "promote", "/s3/multisite/promote", body

    def run(self):
        p = self.params
        if p["update_endpoints"] and not p["endpoints"]:
            self.module.fail_json(msg="update_endpoints=true needs endpoints")

        status = self.status()
        role = current_role(status)
        wanted = p["role"]
        transition = self.plan_transition(role, wanted)
        final_role = wanted or role

        if p["readonly"] and final_role != "secondary":
            self.module.fail_json(msg="Only a secondary has the read-only flag; this cluster is %s" % final_role)
        if p["return_token"] and final_role != "primary":
            self.module.fail_json(msg="return_token: only the multisite primary has a token; this cluster is %s" % final_role)

        before = dict(role=role, readonly=status.get("readonly") if role == "secondary" else None)
        after = dict(role=final_role, readonly=before["readonly"] if transition is None else None)
        readonly_change = False
        if final_role == "secondary" and p["readonly"] is not None:
            if transition is not None:
                after["readonly"] = p["readonly"]
            elif p["readonly"] != bool(status.get("readonly")):
                readonly_change = True
                after["readonly"] = p["readonly"]
        if final_role == "secondary" and after["readonly"] is None and transition is not None:
            after["readonly"] = False

        changed = bool(transition or readonly_change or p["update_endpoints"])
        result = dict(multisite=status)

        if self.check_mode:
            if p["return_token"]:
                if role == "primary":
                    result["token"] = self.get("/s3/multisite/primary/token")
                else:
                    self.module.warn("return_token: no token in check mode, because the cluster only becomes the primary in this run")
            self.exit(changed=changed, before=before, after=after, **result)

        if transition is not None:
            _what, path, body = transition
            self.run_task(self.write("POST", path, body=body))
            status = self.status()
            if final_role == "secondary" and p["readonly"] is not None and bool(status.get("readonly")) != p["readonly"]:
                readonly_change = True
        if readonly_change:
            self.run_task(self.write("PATCH", "/s3/multisite/readonly", body=dict(readonly=p["readonly"])))
        if p["update_endpoints"]:
            self.run_task(self.write("PATCH", "/s3/multisite/endpoints", body=dict(endpoints=normalise_endpoints(p["endpoints"]))))
        if changed:
            status = self.status()
        result["multisite"] = status
        if p["return_token"]:
            result["token"] = self.get("/s3/multisite/primary/token")
        if self.tasks:
            result["tasks"] = self.tasks
            result["task"] = self.tasks[-1]
        self.exit(changed=changed, before=before, after=after, **result)


def main():
    S3MultisiteModule().run()


if __name__ == "__main__":
    main()
