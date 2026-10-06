#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/smb
# croit-api: GET /services/smb/{serviceId}
# croit-api: POST /services/smb/{serviceId}/shares
# croit-api: PUT /services/smb/{serviceId}/shares/{shareId}
# croit-api: DELETE /services/smb/{serviceId}/shares/{shareId}
# croit-api: GET /services/smb/{serviceId}/shares/{shareId}/acl
# croit-api: PUT /services/smb/{serviceId}/shares/{shareId}/acl
# croit-api: PUT /services/smb/{serviceId}/shares/{shareId}/options

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: smb_share
short_description: Manage shares of an SMB gateway cluster on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete the shares of a croit SMB cluster.
  - A share is identified by its O(cluster) and its O(name). Options that are not set keep their current value, and
    options that do not apply to the cluster's type and generation fail the task.
  - On a generation-2 cluster a share's path, volume and ACL mode are fixed once it exists; access is managed
    through its on-disk ACL (O(grants)) and its C(smb.conf) additions (O(parameters), O(vfs_objects),
    O(vfs_objects_before)).
  - On a legacy generation-1 cluster access is managed with O(rw_access), O(ro_access) and O(guest) (simple
    clusters) or O(rw_users) and O(ro_users) (Active Directory clusters).
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
  cluster:
    description:
      - The SMB cluster the share belongs to, by name (croit's description, see M(croit.ceph.smb_cluster)) or numeric
        service id. The task fails when the cluster does not exist.
    type: str
    required: true
  name:
    description:
      - Name of the share as clients see it, for example V(projects). It identifies the share within O(cluster).
    type: str
    required: true
  state:
    description:
      - Whether the share should exist.
      - V(absent) removes the share only. The exported directory and everything in it, including its
        on-disk ACL, stay, so no confirmation is needed.
    type: str
    choices: [present, absent]
    default: present
  path:
    description:
      - Directory in CephFS to export, for example V(/volumes/_nogroup/projects). Required when the share is created.
      - Fixed once a generation-2 share exists; a generation-1 share can be moved to another directory.
    type: str
  volume:
    description:
      - CephFS volume the share exports. croit uses the cluster's volume when it is not set.
      - Generation-2 clusters only; fixed once the share exists.
    type: str
  acl_mode:
    description:
      - ACL semantics of the share. V(posix) needs a simple cluster or an Active Directory cluster with
        customised idmap. Generation-2 clusters only; fixed once the share exists.
      - New shares get V(windows) when it is not set.
    type: str
    choices: [windows, posix]
  grants:
    description:
      - The complete access list of a generation-2 share. When the share is created it seeds the directory's
        on-disk ACL; afterwards it replaces the on-disk ACL, it is not merged into it.
      - Compared as a set. On-disk entries croit cannot express as a grant (deny entries, unusual rights
        masks) are dropped when the ACL is replaced; the module warns when that would happen.
      - When not set, the on-disk ACL is left alone. Generation-2 clusters only.
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - Bare user or group name, without an C(@) prefix.
        type: str
        required: true
      group:
        description:
          - Whether O(grants[].name) is a group rather than a user.
        type: bool
        default: false
      access:
        description:
          - The access the principal gets. V(read) allows reading and traversing, V(read_write) full read and write.
        type: str
        choices: [read, read_write]
        default: read_write
  parameters:
    description:
      - Additional C(smb.conf) parameters of the share as key/value pairs, replacing the stored set. V({}) removes
        every additional parameter. Generation-2 clusters only.
    type: dict
  vfs_objects:
    description:
      - Additional VFS modules stacked after the ones croit manages, in this order. Generation-2 clusters only.
    type: list
    elements: str
  vfs_objects_before:
    description:
      - Additional VFS modules stacked ahead of the ones croit manages, in this order. Generation-2 clusters only.
    type: list
    elements: str
  rw_access:
    description:
      - Generation-1 simple clusters - whether croit's admin user has read/write access.
      - New shares get V(true) when it is not set.
    type: bool
  ro_access:
    description:
      - Generation-1 simple clusters - whether croit's read-only user has access.
      - New shares get V(false) when it is not set.
    type: bool
  guest:
    description:
      - Generation-1 simple clusters - whether guests may access the share without a password.
      - New shares get V(false) when it is not set.
    type: bool
  rw_users:
    description:
      - Generation-1 Active Directory clusters - users and groups (prefixed with C(@)) with read/write access.
        Compared as a set.
    type: list
    elements: str
  ro_users:
    description:
      - Generation-1 Active Directory clusters - users and groups (prefixed with C(@)) with read-only access.
        Compared as a set.
    type: list
    elements: str
notes:
  - Replacing a generation-2 ACL with O(grants) changes who can access the data immediately, and drops on-disk entries
    croit cannot express as a grant.
  - Removing a share disconnects its clients; the exported directory and its data stay.
  - The share ACL mode of a generation-1 share is assumed to be V(windows) when croit reports none. This has not yet
    been verified against a live croit cluster.
seealso:
  - module: croit.ceph.smb_cluster
    description: Manage the SMB cluster a share belongs to.
  - module: croit.ceph.smb_user
    description: Manage the local users O(grants) can refer to.
  - module: croit.ceph.smb_group
    description: Manage the local groups O(grants) can refer to.
  - module: croit.ceph.smb_info
    description: Read SMB clusters with their shares and ACLs.
  - name: croit API reference
    description: The croit REST API this module uses (SMB gateways).
    link: https://www.croit.io/api-docs
  - name: smb.conf reference
    description: Samba's documentation of the parameters accepted by O(parameters) and the VFS modules.
    link: https://www.samba.org/samba/docs/current/man-html/smb.conf.5.html
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Create a generation-2 share with an on-disk ACL
  croit.ceph.smb_share:
    cluster: smb-office
    name: projects
    path: /volumes/_nogroup/projects
    grants:
      - name: admins
        group: true
        access: read_write
      - name: auditor
        access: read

- name: Add an Apple-friendly VFS stack to an existing share
  croit.ceph.smb_share:
    cluster: smb-office
    name: projects
    vfs_objects: [catia, fruit, streams_xattr]
    parameters:
      fruit:metadata: stream

- name: Give the auditor write access as well
  croit.ceph.smb_share:
    cluster: smb-office
    name: projects
    grants:
      - name: admins
        group: true
      - name: auditor
  register: share

- name: Show what croit reports for the share's ACL
  ansible.builtin.debug:
    var: share.acl.grants

- name: Generation-1 Active Directory share
  croit.ceph.smb_share:
    cluster: smb-legacy-ad
    name: finance
    path: /finance
    rw_users: ["@finance-admins"]
    ro_users: ["@auditors", jdoe]

- name: Remove the share (the directory and data stay)
  croit.ceph.smb_share:
    cluster: smb-office
    name: projects
    state: absent
"""

RETURN = r"""
share:
  description:
    - The share as croit reports it after the change (C(SmbGatewayShareResponse) in the croit API).
    - In check mode the share before the change. Empty when the share does not exist or was removed, and after a create
      with O(wait=false) that ran as a task.
  returned: always
  type: dict
  contains:
    id:
      description: croit's id of the share.
      returned: when the share exists
      type: int
      sample: 3
    serviceId:
      description: croit service id of the SMB cluster.
      returned: when the share exists
      type: int
      sample: 52
    share:
      description: The share's name (O(name)).
      returned: when the share exists
      type: str
      sample: projects
    path:
      description: The exported CephFS directory.
      returned: when the share exists
      type: str
      sample: /volumes/_nogroup/projects
    volume:
      description: The CephFS volume the share exports; null on generation-1 shares.
      returned: when the share exists
      type: str
      sample: cephfs
    aclMode:
      description: ACL semantics, V(WINDOWS) or V(POSIX); null on generation-1 shares.
      returned: when the share exists
      type: str
      sample: WINDOWS
    parameters:
      description: Additional C(smb.conf) parameters of a generation-2 share.
      returned: when the share exists
      type: dict
      sample: {"fruit:metadata": stream}
    vfsObjects:
      description: Additional VFS modules stacked after croit's.
      returned: when the share exists
      type: list
      elements: str
      sample: [catia, fruit, streams_xattr]
    vfsObjectsBefore:
      description: Additional VFS modules stacked ahead of croit's.
      returned: when the share exists
      type: list
      elements: str
      sample: []
    rw:
      description: Generation-1 simple shares - read/write access for croit's admin user.
      returned: when the share exists
      type: bool
      sample: true
    rwUsers:
      description: Generation-1 Active Directory shares - users and groups with read/write access.
      returned: when the share exists
      type: list
      elements: str
      sample: ["@finance-admins"]
acl:
  description:
    - The share's on-disk access list (C(ShareAclReadResult)) as croit reads it off the share root.
    - After the change when it was replaced, otherwise before it.
  returned: when O(grants) is set and the share already existed
  type: dict
  contains:
    grants:
      description: One entry per principal with C(name), C(group) and C(access) (V(READ) or V(READ_WRITE)).
      returned: always
      type: list
      elements: dict
      sample: [{name: admins, group: true, access: READ_WRITE}, {name: auditor, group: false, access: READ}]
    unrepresentable:
      description: On-disk entries croit cannot express as a grant; they are dropped when the ACL is replaced.
      returned: always
      type: list
      elements: str
      sample: []
    unresolved:
      description: Raw ids or SIDs of entries whose principal no longer resolves to a name.
      returned: always
      type: list
      elements: str
      sample: ["S-1-5-21-1004336348-1177238915-682003330-1105"]
task:
  description: The last croit background task the change ran as, for example the share creation or the ACL replacement.
  returned: when a task ran
  type: dict
  contains:
    id:
      description: croit's task id.
      returned: always
      type: int
      sample: 640
    name:
      description: What the task did.
      returned: always
      type: str
      sample: Set share ACL
    state:
      description: Final state of the task, one of C(FINISHED), C(FAILED), C(CANCELED), or C(RUNNING) with O(wait=false).
      returned: always
      type: str
      sample: FINISHED
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: "Writing ACL of /volumes/_nogroup/projects ... done"
"""

import posixpath

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.smb import (
    TYPE_SIMPLE,
    cluster_detail,
    generation,
    merge_options,
    options_request,
    options_view,
    require_cluster,
)

ACCESS = dict(read="READ", read_write="READ_WRITE")
GEN2_OPTIONS = ("volume", "acl_mode", "grants", "parameters", "vfs_objects", "vfs_objects_before")
SIMPLE_GEN1_OPTIONS = ("rw_access", "ro_access", "guest")
AD_GEN1_OPTIONS = ("rw_users", "ro_users")


def normalise_path(value):
    if value is None:
        return None
    path = posixpath.normpath("/" + value.strip().lstrip("/"))
    return "/" if path == "//" else path


def grant_key(grant):
    return (grant.get("name"), bool(grant.get("group")), (grant.get("access") or "").upper())


def grants_view(grants):
    """Grants as sorted, comparable dicts with lower-case access."""
    return [dict(name=n, group=g, access=a.lower()) for n, g, a in sorted(set(grant_key(x) for x in grants or []))]


class SmbShareModule(CroitModule):
    def __init__(self):
        super(SmbShareModule, self).__init__(
            dict(
                cluster=dict(type="str", required=True),
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                path=dict(type="str"),
                volume=dict(type="str"),
                acl_mode=dict(type="str", choices=["windows", "posix"]),
                grants=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        name=dict(type="str", required=True),
                        group=dict(type="bool", default=False),
                        access=dict(type="str", default="read_write", choices=list(ACCESS)),
                    ),
                ),
                parameters=dict(type="dict"),
                vfs_objects=dict(type="list", elements="str"),
                vfs_objects_before=dict(type="list", elements="str"),
                rw_access=dict(type="bool"),
                ro_access=dict(type="bool"),
                guest=dict(type="bool"),
                rw_users=dict(type="list", elements="str"),
                ro_users=dict(type="list", elements="str"),
            ),
        )
        self.tasks = []

    def desired_grants(self):
        if self.params["grants"] is None:
            return None
        return [dict(name=g["name"], group=g["group"], access=ACCESS[g["access"]]) for g in self.params["grants"]]

    def validate(self, config):
        p = self.params
        kind = config.get("type")
        if generation(config) >= 2:
            bad = [o for o in SIMPLE_GEN1_OPTIONS + AD_GEN1_OPTIONS if p[o] is not None]
            if bad:
                self.module.fail_json(
                    msg="%s only apply to generation-1 clusters; on generation 2 use grants" % ", ".join(bad)
                )
        else:
            bad = [o for o in GEN2_OPTIONS if p[o] is not None]
            bad += [o for o in (AD_GEN1_OPTIONS if kind == TYPE_SIMPLE else SIMPLE_GEN1_OPTIONS) if p[o] is not None]
            if bad:
                self.module.fail_json(
                    msg="%s do not apply to SMB cluster %r (%s, generation %s)"
                    % (", ".join(bad), config.get("description"), kind, generation(config))
                )

    def find_share(self, detail):
        for share in detail.get("shares") or []:
            if share.get("share") == self.params["name"]:
                return share
        return None

    def view(self, share, config, acl=None):
        if not share:
            return {}
        view = dict(path=normalise_path(share.get("path")))
        if generation(config) >= 2:
            view.update(
                volume=share.get("volume"),
                acl_mode=(share.get("aclMode") or "WINDOWS").lower(),
                parameters=dict(share.get("parameters") or {}),
                vfs_objects=list(share.get("vfsObjects") or []),
                vfs_objects_before=list(share.get("vfsObjectsBefore") or []),
            )
            if acl is not None:
                view["grants"] = grants_view(acl.get("grants"))
        elif config.get("type") == TYPE_SIMPLE:
            view.update(rw_access=bool(share.get("rw")), ro_access=bool(share.get("ro")), guest=bool(share.get("guest")))
        else:
            view.update(rw_users=sorted(share.get("rwUsers") or []), ro_users=sorted(share.get("roUsers") or []))
        return view

    def run(self):
        p = self.params
        config = require_cluster(self, p["cluster"])
        self.validate(config)
        self.service_path = path_join("services", "smb", config["serviceId"])
        detail = cluster_detail(self, config["serviceId"]) or {}
        share = self.find_share(detail)

        if p["state"] == "absent":
            if share is None:
                self.exit(changed=False, share={})
            if not self.check_mode:
                self.write("DELETE", path_join("services", "smb", config["serviceId"], "shares", share["id"]))
            self.exit(changed=True, before=self.view(share, config), after={}, share={})

        if share is None:
            return self.create(config)
        return self.update(config, share)

    def finish(self, changed, before, after, **result):
        if self.tasks:
            result["task"] = self.tasks[-1]
        self.exit(changed=changed, before=before, after=after, **result)

    def reread(self, config):
        return self.find_share(cluster_detail(self, config["serviceId"]) or {}) or {}

    def create(self, config):
        p = self.params
        if not p["path"]:
            self.module.fail_json(msg="path is required to create share %r" % p["name"])
        kind = config.get("type")
        body = dict(type=kind, share=p["name"], path=normalise_path(p["path"]))
        if kind == TYPE_SIMPLE:
            body.update(
                rw=p["rw_access"] if p["rw_access"] is not None else True,
                ro=bool(p["ro_access"]),
                guest=bool(p["guest"]),
            )
        else:
            body.update(rwUsers=list(p["rw_users"] or []), roUsers=list(p["ro_users"] or []))
        after = dict(path=body["path"])
        if generation(config) >= 2:
            grants = self.desired_grants()
            options = merge_options(
                options_view(None),
                dict(parameters=p["parameters"], vfs_objects=p["vfs_objects"], vfs_objects_before=p["vfs_objects_before"]),
            )[0]
            body.update(options_request(options))
            if p["volume"] is not None:
                body["volume"] = p["volume"]
            if p["acl_mode"] is not None:
                body["aclMode"] = p["acl_mode"].upper()
            if grants is not None:
                body["grants"] = grants
            after.update(volume=p["volume"], acl_mode=p["acl_mode"] or "windows", **options)
            if grants is not None:
                after["grants"] = grants_view(grants)
        elif kind == TYPE_SIMPLE:
            after.update(rw_access=body["rw"], ro_access=body["ro"], guest=body["guest"])
        else:
            after.update(rw_users=sorted(body["rwUsers"]), ro_users=sorted(body["roUsers"]))

        if self.check_mode:
            self.finish(True, {}, after, share={})
        task = self.handle_task(self.write("POST", self.service_path + "/shares", body=body))
        if task is not None:
            self.tasks.append(task)
        share = self.reread(config) if p["wait"] or task is None else {}
        self.finish(True, {}, after, share=share)

    def update(self, config, share):
        if generation(config) >= 2:
            return self.update_gen2(config, share)
        return self.update_gen1(config, share)

    def update_gen1(self, config, share):
        p = self.params
        before = self.view(share, config)
        after = dict(before)
        if p["path"] is not None:
            after["path"] = normalise_path(p["path"])
        if config.get("type") == TYPE_SIMPLE:
            for opt in SIMPLE_GEN1_OPTIONS:
                if p[opt] is not None:
                    after[opt] = p[opt]
        else:
            for opt in AD_GEN1_OPTIONS:
                if p[opt] is not None:
                    after[opt] = sorted(set(p[opt]))
        if after == before:
            self.finish(False, before, after, share=share)
        if self.check_mode:
            self.finish(True, before, after, share=share)
        # The PUT overwrites every column of the share, so send the merged state.
        body = dict(type=config.get("type"), share=share["share"], path=after["path"])
        if config.get("type") == TYPE_SIMPLE:
            body.update(rw=after["rw_access"], ro=after["ro_access"], guest=after["guest"])
        else:
            body.update(rwUsers=after["rw_users"], roUsers=after["ro_users"])
        self.write("PUT", path_join("services", "smb", config["serviceId"], "shares", share["id"]), body=body)
        self.finish(True, before, after, share=self.reread(config))

    def update_gen2(self, config, share):
        p = self.params
        share_path = path_join("services", "smb", config["serviceId"], "shares", share["id"])
        acl = self.get(share_path + "/acl") if p["grants"] is not None else None
        before = self.view(share, config, acl)
        after = dict(before)

        fixed = dict(path=normalise_path(p["path"]), volume=p["volume"], acl_mode=p["acl_mode"])
        for opt, wanted in fixed.items():
            if wanted is not None and wanted != before[opt]:
                self.module.fail_json(
                    msg="%s of share %r is %r and cannot be changed to %r on a generation-2 cluster; "
                    "remove the share and create it again" % (opt, share["share"], before[opt], wanted)
                )

        options, options_differ = merge_options(
            dict((k, before[k]) for k in ("parameters", "vfs_objects", "vfs_objects_before")),
            dict(parameters=p["parameters"], vfs_objects=p["vfs_objects"], vfs_objects_before=p["vfs_objects_before"]),
        )
        if options_differ:
            after.update(options)

        grants = self.desired_grants()
        grants_differ = grants is not None and grants_view(grants) != before["grants"]
        if grants_differ:
            after["grants"] = grants_view(grants)
            dropped = list((acl or {}).get("unrepresentable") or []) + list((acl or {}).get("unresolved") or [])
            if dropped:
                self.module.warn(
                    "Replacing the ACL of share %r drops %d on-disk entr%s croit cannot express as a grant: %s"
                    % (share["share"], len(dropped), "y" if len(dropped) == 1 else "ies", ", ".join(dropped))
                )

        result = dict(share=share)
        if acl is not None:
            result["acl"] = acl
        changed = options_differ or grants_differ
        if not changed or self.check_mode:
            self.finish(changed, before, after, **result)

        if options_differ:
            self.write("PUT", share_path + "/options", body=options_request(options))
        if grants_differ:
            task = self.handle_task(self.write("PUT", share_path + "/acl", body=dict(grants=grants)))
            if task is not None:
                self.tasks.append(task)
            if p["wait"] or task is None:
                result["acl"] = self.get(share_path + "/acl")
        result["share"] = self.reread(config)
        self.finish(True, before, after, **result)


def main():
    SmbShareModule().run()


if __name__ == "__main__":
    main()
