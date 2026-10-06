#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/iscsi
# croit-api: GET /services/iscsi/{serviceId}
# croit-api: PUT /services/iscsi/{serviceId}/clients/{name}
# croit-api: PATCH /services/iscsi/{serviceId}/clients/{name}
# croit-api: DELETE /services/iscsi/{serviceId}/clients/{name}
# croit-api: PUT /services/iscsi/{serviceId}/clients/{name}/disks
# croit-api: DELETE /services/iscsi/{serviceId}/clients/{name}/disks
# croit-api: PUT /services/iscsi/{serviceId}/groups/{group}/hosts/{host}
# croit-api: DELETE /services/iscsi/{serviceId}/groups/{group}/hosts/{host}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: iscsi_client
short_description: Manage iSCSI initiators of the croit iSCSI gateway
version_added: 0.1.0
description:
  - Allows an initiator (by IQN) onto the cluster's iSCSI target with a CHAP credential. It can also put
    the initiator in a host group and map disks to it.
  - Mapping a disk exports it on the target. A disk entry with O(disks[].size) creates a new RBD image
    of that size when the image does not exist yet.
  - Removing an initiator or unmapping a disk never deletes the RBD image. Use M(croit.ceph.iscsi_disk) for that.
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
  iqn:
    description:
      - IQN of the initiator, for example V(iqn.1998-01.com.vmware:esx01-12345678). This is how the module
        finds it.
    type: str
    required: true
    aliases: [name]
  state:
    description:
      - V(absent) removes the initiator from the target, together with its own disk mappings. The images are kept.
    type: str
    choices: [present, absent]
    default: present
  chap_username:
    description:
      - CHAP username, 8 to 64 characters. Required to create the initiator.
    type: str
  chap_password:
    description:
      - CHAP password, 12 to 16 characters. Required to create the initiator.
      - It is compared with the stored password when croit returns it, which it does for admin tokens. When croit
        only reports C((masked)), O(update_password) decides.
    type: str
  update_password:
    description:
      - What to do with O(chap_password) when croit does not show the stored password.
      - V(on_create) only sets it when the initiator is created.
      - V(always) sets it on every run, so the task always reports a change.
    type: str
    choices: [on_create, always]
    default: on_create
  group:
    description:
      - Host group the initiator belongs to. An empty string takes it out of its group.
      - The group must exist, see M(croit.ceph.iscsi_group). The gateway refuses to put an initiator that has disk
        mappings of its own into a group.
      - croit warns before taking an initiator out of a group, see O(ignore_warnings). The initiator keeps the
        disks the group mapped.
    type: str
  disks:
    description:
      - Disks mapped directly to the initiator. Listed disks are mapped. With O(exclusive=true), other direct
        mappings are removed.
      - Disks the initiator gets through its host group are not affected.
    type: list
    elements: dict
    suboptions:
      pool:
        description: RBD pool of the image to map to the initiator.
        type: str
        required: true
      image:
        description: RBD image name to map to the initiator.
        type: str
        required: true
      size:
        description:
          - Create the image with this size (bytes or a binary unit such as V(100G), rounded up to whole MiB)
            if it does not exist yet. Leave unset for an existing image.
          - Only used when the disk is mapped. Use M(croit.ceph.iscsi_disk) to grow it later.
        type: str
      backstore:
        description: How the gateway backs the export. croit uses V(user:rbd) (tcmu-runner) when not set.
        type: str
        choices: ["user:rbd", rbd]
  exclusive:
    description:
      - With V(true), O(disks) is the complete list of the initiator's direct mappings.
    type: bool
    default: false
  service_id:
    description:
      - croit service id of the iSCSI gateway. Only needed if croit reports more than one.
    type: int
seealso:
  - module: croit.ceph.iscsi_group
    description: Share disks between several initiators through a host group.
  - module: croit.ceph.iscsi_disk
    description: Grow, unexport or delete exported disks.
  - module: croit.ceph.iscsi_gateway
    description: Manage the iSCSI gateway and its target.
  - module: croit.ceph.iscsi_info
    description: List the initiators and their disks.
  - name: Ceph iSCSI gateway
    description: Upstream documentation of the Ceph iSCSI gateway.
    link: https://docs.ceph.com/en/latest/rbd/iscsi-overview/
  - name: croit API reference
    description: The croit REST API this module talks to.
    link: https://www.croit.io/api-docs
notes:
  - The CHAP password is never returned. RV(client.password) is masked as C(********).
  - CHAP lengths are checked before anything is sent; the username needs 8 to 64 and the password 12 to 16
    characters.
  - Disks the initiator gets through its host group are not counted as its own, so O(exclusive=true) never
    unmaps a group's disks.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Allow an ESXi host onto the target and map a new 2 TiB datastore
  croit.ceph.iscsi_client:
    iqn: iqn.1998-01.com.vmware:esx01-12345678
    chap_username: esx01-user
    chap_password: "{{ vault_esx01_chap }}"
    disks:
      - pool: iscsi
        image: datastore1
        size: 2T
  register: esx01

- name: Show the WWNs of the disks mapped to the host
  ansible.builtin.debug:
    msg: "{{ esx01.client.luns | map(attribute='wwn') | list }}"

- name: Map exactly these disks to the host
  croit.ceph.iscsi_client:
    iqn: iqn.1998-01.com.vmware:esx01-12345678
    disks:
      - pool: iscsi
        image: datastore1
    exclusive: true

- name: Rotate the CHAP password
  croit.ceph.iscsi_client:
    iqn: iqn.1998-01.com.vmware:esx01-12345678
    chap_username: esx01-user
    chap_password: "{{ vault_esx01_chap_new }}"
    update_password: always

- name: Put a host without own disks in a group
  croit.ceph.iscsi_client:
    iqn: iqn.1998-01.com.vmware:esx02-87654321
    group: esx-cluster

- name: Remove the initiator (images are kept)
  croit.ceph.iscsi_client:
    iqn: iqn.1998-01.com.vmware:esx01-12345678
    state: absent
"""

RETURN = r"""
client:
  description:
    - The initiator (C(IscsiClientResponse) in the croit API) after the change, with the CHAP password masked.
    - Empty when the initiator does not exist. Shows the state before the change in check mode.
  returned: always
  type: dict
  contains:
    name:
      description: IQN of the initiator.
      returned: when the initiator exists
      type: str
      sample: iqn.1998-01.com.vmware:esx01-12345678
    username:
      description: CHAP username.
      returned: when the initiator exists
      type: str
      sample: esx01-user
    password:
      description: CHAP password, always masked as C(********) when one is set.
      returned: when the initiator exists
      type: str
      sample: "********"
    group:
      description: Host group of the initiator, or an empty string.
      returned: when the initiator exists
      type: str
      sample: ""
    luns:
      description: Disks mapped to the initiator, each with C(pool), C(image) and C(wwn).
      returned: when the initiator exists
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

MASK = "********"
UNREADABLE = "(masked)"


def masked(client):
    if not client:
        return {}
    result = dict(client)
    if result.get("password"):
        result["password"] = MASK
    return result


class IscsiClientModule(CroitModule):
    def __init__(self):
        super(IscsiClientModule, self).__init__(
            dict(
                iqn=dict(type="str", required=True, aliases=["name"]),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                chap_username=dict(type="str"),
                chap_password=dict(type="str", no_log=True),
                update_password=dict(type="str", default="on_create", choices=["on_create", "always"], no_log=False),
                group=dict(type="str"),
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

    def validate(self):
        p = self.params
        if p["chap_username"] is not None and not 8 <= len(p["chap_username"]) <= 64:
            self.module.fail_json(msg="chap_username must be 8 to 64 characters long")
        if p["chap_password"] is not None and not 12 <= len(p["chap_password"]) <= 16:
            self.module.fail_json(msg="chap_password must be 12 to 16 characters long")

    def client_path(self, *rest):
        return path_join("services", "iscsi", self.sid, "clients", self.params["iqn"], *rest)

    def group_luns(self, config, group):
        for g in config.get("groups") or []:
            if g.get("name") == group:
                return set(disk_key(lun) for lun in g.get("luns") or [])
        return set()

    def own_luns(self, config, client):
        """Disks mapped to the initiator itself, not through its group."""
        inherited = self.group_luns(config, client.get("group")) if client.get("group") else set()
        return sorted(set(disk_key(lun) for lun in client.get("luns") or []) - inherited)

    def view(self, config, client, password_change=False):
        if not client:
            return {}
        return dict(
            chap_username=client.get("username"),
            chap_password=MASK + (" (changed)" if password_change else ""),
            group=client.get("group") or "",
            disks=self.own_luns(config, client),
        )

    def read(self):
        config = self.get(path_join("services", "iscsi", self.sid)) or {}
        client = None
        for c in config.get("clients") or []:
            if c.get("name") == self.params["iqn"]:
                client = c
        return config, client

    def check_group(self, config, group):
        if group and group not in [g.get("name") for g in config.get("groups") or []]:
            self.module.fail_json(
                msg="iSCSI host group %r does not exist. Known groups: %s"
                % (group, ", ".join(g.get("name") for g in config.get("groups") or []) or "none")
            )

    def run(self):
        p = self.params
        self.validate()
        self.sid = require_service(self, p["service_id"])["serviceId"]
        config, client = self.read()

        if p["state"] == "absent":
            if client is None:
                self.exit(changed=False, client={})
            if not self.check_mode:
                self.write("DELETE", self.client_path())
            self.exit(changed=True, before=self.view(config, client), after={}, client={})

        self.check_group(config, p["group"])
        wanted_disks = [disk_request(self, d) for d in p["disks"] or []]

        if client is None:
            return self.create(config, wanted_disks)
        return self.update(config, client, wanted_disks)

    def create(self, config, wanted_disks):
        p = self.params
        if p["chap_username"] is None or p["chap_password"] is None:
            self.module.fail_json(msg="chap_username and chap_password are required to create initiator %s" % p["iqn"])
        after = dict(
            chap_username=p["chap_username"],
            chap_password=MASK,
            group=p["group"] or "",
            disks=sorted(set("%s/%s" % (d["pool"], d["name"]) for d in wanted_disks)),
        )
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, client={})
        body = dict(username=p["chap_username"], password=p["chap_password"])
        if p["group"]:
            body["group"] = p["group"]
        self.write("PUT", self.client_path(), body=body)
        if wanted_disks:
            self.write("PUT", self.client_path("disks"), body=wanted_disks)
        config, client = self.read()
        self.exit(changed=True, before={}, after=after, client=masked(client))

    def update(self, config, client, wanted_disks):
        p = self.params
        chap = {}
        if p["chap_username"] is not None and p["chap_username"] != client.get("username"):
            chap["username"] = p["chap_username"]
        if p["chap_password"] is not None:
            stored = client.get("password")
            if stored == UNREADABLE or stored is None:
                if p["update_password"] == "always":
                    chap["password"] = p["chap_password"]
            elif stored != p["chap_password"]:
                chap["password"] = p["chap_password"]

        current_group = client.get("group") or ""
        group_change = p["group"] is not None and p["group"] != current_group

        own = set(self.own_luns(config, client))
        add = [d for d in wanted_disks if "%s/%s" % (d["pool"], d["name"]) not in own]
        remove = []
        if p["exclusive"] and p["disks"] is not None:
            wanted_keys = set("%s/%s" % (d["pool"], d["name"]) for d in wanted_disks)
            remove = sorted(own - wanted_keys)

        before = self.view(config, client)
        after = self.view(config, client, password_change="password" in chap)
        if "username" in chap:
            after["chap_username"] = chap["username"]
        if group_change:
            after["group"] = p["group"]
        after["disks"] = sorted((own | set("%s/%s" % (d["pool"], d["name"]) for d in add)) - set(remove))

        changed = bool(chap or group_change or add or remove)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, client=masked(client))

        if chap:
            self.write("PATCH", self.client_path(), body=chap)
        if group_change:
            if current_group:
                self.write("DELETE", path_join("services", "iscsi", self.sid, "groups", current_group, "hosts", p["iqn"]))
            if p["group"]:
                self.write("PUT", path_join("services", "iscsi", self.sid, "groups", p["group"], "hosts", p["iqn"]))
        for key in remove:
            pool, image = key.split("/", 1)
            self.write("DELETE", self.client_path("disks"), body=dict(pool=pool, name=image))
        if add:
            self.write("PUT", self.client_path("disks"), body=add)
        config, client = self.read()
        self.exit(changed=True, before=before, after=after, client=masked(client))


def main():
    IscsiClientModule().run()


if __name__ == "__main__":
    main()
