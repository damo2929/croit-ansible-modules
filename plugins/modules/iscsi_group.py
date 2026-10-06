#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/iscsi
# croit-api: GET /services/iscsi/{serviceId}
# croit-api: PUT /services/iscsi/{serviceId}/groups/{group}
# croit-api: DELETE /services/iscsi/{serviceId}/groups/{group}
# croit-api: PUT /services/iscsi/{serviceId}/groups/{group}/hosts
# croit-api: DELETE /services/iscsi/{serviceId}/groups/{group}/hosts
# croit-api: PUT /services/iscsi/{serviceId}/groups/{group}/disks
# croit-api: DELETE /services/iscsi/{serviceId}/groups/{group}/disks

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: iscsi_group
short_description: Manage iSCSI host groups of the croit iSCSI gateway
version_added: 0.1.0
description:
  - Creates and deletes host groups on the cluster's iSCSI target, and manages their member initiators and
    disks. A disk mapped to a group is mapped to every host in it.
  - Mapping a disk exports it on the target. A disk entry with O(disks[].size) creates a new RBD image of that
    size when the image does not exist yet.
  - Removing a group, a member or a disk never deletes an RBD image.
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
  name:
    description:
      - Name of the host group on the iSCSI target. This is how the module finds it.
    type: str
    required: true
  state:
    description:
      - V(absent) removes the group. Its hosts keep the disks the group mapped to them.
      - croit warns before removing a group or its members, see O(ignore_warnings).
    type: str
    choices: [present, absent]
    default: present
  members:
    description:
      - IQNs of the initiators in the group. Listed initiators are added; with O(exclusive=true), other members
        are removed.
      - Each initiator must already be allowed onto the target, see M(croit.ceph.iscsi_client). The gateway
        refuses an initiator that has disk mappings of its own.
    type: list
    elements: str
  disks:
    description:
      - Disks mapped to the group. Listed disks are mapped; with O(exclusive=true), other disks are unmapped.
    type: list
    elements: dict
    suboptions:
      pool:
        description: RBD pool of the image to map to the group.
        type: str
        required: true
      image:
        description: RBD image name to map to the group.
        type: str
        required: true
      size:
        description:
          - Create the image with this size (bytes or a binary unit such as V(100G), rounded up to whole MiB)
            if it does not exist yet. Leave unset for an existing image.
        type: str
      backstore:
        description: How the gateway backs the export. croit uses V(user:rbd) (tcmu-runner) when not set.
        type: str
        choices: ["user:rbd", rbd]
  exclusive:
    description:
      - With V(true), O(members) and O(disks) (whichever are set) are complete lists.
    type: bool
    default: false
  service_id:
    description:
      - croit service id of the iSCSI gateway. Only needed if croit reports more than one.
    type: int
seealso:
  - module: croit.ceph.iscsi_client
    description: Allow the member initiators onto the target first.
  - module: croit.ceph.iscsi_disk
    description: Grow, unexport or delete exported disks.
  - module: croit.ceph.iscsi_info
    description: List host groups, their members and disks.
  - module: croit.ceph.iscsi_gateway
    description: Manage the iSCSI gateway and its target.
  - name: Ceph iSCSI gateway
    description: Upstream documentation of the Ceph iSCSI gateway.
    link: https://docs.ceph.com/en/latest/rbd/iscsi-overview/
  - name: croit API reference
    description: The croit REST API this module talks to.
    link: https://www.croit.io/api-docs
notes:
  - croit warns before removing a group or one of its members. Set O(ignore_warnings=true) to confirm.
  - Removing a group, a member or a mapping never deletes an RBD image.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: ESXi cluster sharing two datastores
  croit.ceph.iscsi_group:
    name: esx-cluster
    members:
      - iqn.1998-01.com.vmware:esx01-12345678
      - iqn.1998-01.com.vmware:esx02-87654321
    disks:
      - pool: iscsi
        image: datastore1
      - pool: iscsi
        image: datastore2
        size: 4T
    exclusive: true
  register: esx_group

- name: Show the members of the group
  ansible.builtin.debug:
    msg: "{{ esx_group.group.members }}"

- name: Add a third host, leaving the others alone
  croit.ceph.iscsi_group:
    name: esx-cluster
    members:
      - iqn.1998-01.com.vmware:esx03-11223344

- name: Remove the group (hosts keep their disks)
  croit.ceph.iscsi_group:
    name: esx-cluster
    state: absent
    ignore_warnings: true
"""

RETURN = r"""
group:
  description:
    - The host group (C(IscsiGroupResponse) in the croit API) after the change.
    - Empty when the group does not exist. Shows the state before the change in check mode.
  returned: always
  type: dict
  contains:
    name:
      description: Name of the host group.
      returned: when the group exists
      type: str
      sample: esx-cluster
    members:
      description: IQNs of the initiators in the group.
      returned: when the group exists
      type: list
      elements: str
      sample: [iqn.1998-01.com.vmware:esx01-12345678]
    luns:
      description: Disks mapped to the group, each with C(pool), C(image) and C(wwn).
      returned: when the group exists
      type: list
      elements: dict
      sample:
        - pool: iscsi
          image: datastore1
          wwn: 3f0e8c7a-0c1d-4a5e-9b6f-2d3c4b5a6f70
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.iscsi import disk_key, disk_request, require_service
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def view(group):
    if not group:
        return {}
    return dict(
        members=sorted(group.get("members") or []),
        disks=sorted(disk_key(lun) for lun in group.get("luns") or []),
    )


class IscsiGroupModule(CroitModule):
    def __init__(self):
        super(IscsiGroupModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                members=dict(type="list", elements="str"),
                disks=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        pool=dict(type="str", required=True),
                        image=dict(type="str", required=True),
                        size=dict(type="str"),
                        backstore=dict(type="str", choices=["user:rbd", "rbd"]),
                    ),
                ),
                exclusive=dict(type="bool", default=False),
                service_id=dict(type="int"),
            ),
            wait=False,
        )

    def group_path(self, *rest):
        return path_join("services", "iscsi", self.sid, "groups", self.params["name"], *rest)

    def read(self):
        config = self.get(path_join("services", "iscsi", self.sid)) or {}
        for g in config.get("groups") or []:
            if g.get("name") == self.params["name"]:
                return config, g
        return config, None

    def run(self):
        p = self.params
        self.sid = require_service(self, p["service_id"])["serviceId"]
        config, group = self.read()

        if p["state"] == "absent":
            if group is None:
                self.exit(changed=False, group={})
            if not self.check_mode:
                self.write("DELETE", self.group_path())
            self.exit(changed=True, before=view(group), after={}, group={})

        if p["members"] is not None:
            known = [c.get("name") for c in config.get("clients") or []]
            unknown = sorted(set(p["members"]) - set(known))
            if unknown:
                self.module.fail_json(
                    msg="Initiator(s) %s are not allowed onto the target yet; add them with croit.ceph.iscsi_client "
                    "first. Known initiators: %s" % (", ".join(unknown), ", ".join(known) or "none")
                )
        wanted_disks = [disk_request(self, d) for d in p["disks"] or []]
        wanted_keys = set("%s/%s" % (d["pool"], d["name"]) for d in wanted_disks)

        current = view(group) if group is not None else dict(members=[], disks=[])
        current_members = set(current["members"])
        current_disks = set(current["disks"])

        add_members = sorted(set(p["members"] or []) - current_members)
        remove_members = sorted(current_members - set(p["members"])) if p["exclusive"] and p["members"] is not None else []
        add_disks = [d for d in wanted_disks if "%s/%s" % (d["pool"], d["name"]) not in current_disks]
        remove_disks = sorted(current_disks - wanted_keys) if p["exclusive"] and p["disks"] is not None else []

        before = view(group)
        after = dict(
            members=sorted((current_members | set(add_members)) - set(remove_members)),
            disks=sorted((current_disks | set("%s/%s" % (d["pool"], d["name"]) for d in add_disks)) - set(remove_disks)),
        )
        changed = group is None or bool(add_members or remove_members or add_disks or remove_disks)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, group=group or {})

        if group is None:
            self.write("PUT", self.group_path())
        if remove_members:
            self.write("DELETE", self.group_path("hosts"), body=remove_members)
        for key in remove_disks:
            pool, image = key.split("/", 1)
            self.write("DELETE", self.group_path("disks"), body=dict(pool=pool, name=image))
        if add_members:
            self.write("PUT", self.group_path("hosts"), body=add_members)
        if add_disks:
            self.write("PUT", self.group_path("disks"), body=add_disks)
        config, group = self.read()
        self.exit(changed=True, before=before, after=after, group=group or {})


def main():
    IscsiGroupModule().run()


if __name__ == "__main__":
    main()
