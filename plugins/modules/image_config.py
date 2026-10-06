#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /images/archs
# croit-api: PUT /images/archs
# croit-api: GET /images/registry
# croit-api: PUT /images/registry
# croit-api: GET /images/config
# croit-api: PUT /images/config

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: image_config
short_description: Manage croit OS image settings
version_added: 0.1.0
description:
  - Manages the cluster-wide settings for croit OS images, namely which CPU architectures croit offers images
    for, the registry it reads them from, and which Ceph build (variant) they carry.
  - Only the options that are set are managed.
  - Individual images are downloaded, removed and made the default with M(croit.ceph.image).
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
notes:
  - Switching O(variant) to V(frontier) cannot be reversed.
  - O(registry.password) is never returned by croit; only C(passwordSet) shows whether one is stored.
seealso:
  - module: croit.ceph.image
    description: Download, remove and select individual images.
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
options:
  archs:
    description:
      - Which CPU architectures croit downloads and offers images for. At least one must stay enabled.
      - Disabling an architecture that nodes still report is confirmed by croit with a warning, see O(ignore_warnings).
    type: dict
    suboptions:
      x86_64:
        description: Whether croit downloads and offers x86_64 images. Not set means leave alone.
        type: bool
      arm64:
        description: Whether croit downloads and offers arm64 images. Not set means leave alone.
        type: bool
  registry:
    description:
      - The container registry croit lists OS images from. Set O(registry.repository) to an empty string to go back
        to croit's own catalog.
    type: dict
    suboptions:
      registry:
        description: Registry host. An empty string is Docker Hub.
        type: str
      repository:
        description: Repository the OS images are published in. An empty string reads croit's own catalog.
        type: str
      username:
        description: User croit logs in as. An empty string is an anonymous read, and also clears the password.
        type: str
      password:
        description:
          - Password croit logs in with. croit never returns it, so it cannot be compared; see O(registry.update_password).
        type: str
      update_password:
        description:
          - V(on_create) only sends O(registry.password) when croit has no password stored.
          - V(always) sends it on every run, which always reports a change.
        type: str
        choices: [on_create, always]
        default: on_create
      plaintext:
        description: Talk to the registry over plain HTTP.
        type: bool
  variant:
    description:
      - Ceph build the cluster's images carry. croit's own builds need a license.
      - Switching to V(frontier) cannot be reversed, because its data format is incompatible with the other
        builds. croit confirms it with a warning, see O(ignore_warnings).
    type: str
    choices: [core, enhanced, frontier]
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Offer only x86_64 images
  croit.ceph.image_config:
    archs:
      x86_64: true
      arm64: false

- name: Read images from a private mirror
  croit.ceph.image_config:
    registry:
      registry: registry.example.com
      repository: croit/os-images
      username: croit-pull
      password: "{{ vault_registry_password }}"
  register: mirror

- name: Show whether croit has a registry password stored
  ansible.builtin.debug:
    msg: "password set: {{ mirror.registry.passwordSet }}"

- name: Use croit's enhanced Ceph build
  croit.ceph.image_config:
    variant: enhanced
"""

RETURN = r"""
archs:
  description: Enabled architectures after the change (C(ArchConfig) in the croit API).
  returned: when O(archs) is set
  type: dict
  contains:
    x86_64:
      description: Whether x86_64 images are offered.
      returned: always
      type: bool
      sample: true
    arm64:
      description: Whether arm64 images are offered.
      returned: always
      type: bool
      sample: false
registry:
  description: Registry settings after the change (C(RegistryStatus) in the croit API). The password is never returned.
  returned: when O(registry) is set
  type: dict
  contains:
    registry:
      description: Registry host; empty for Docker Hub.
      returned: always
      type: str
      sample: registry.example.com
    repository:
      description: Repository the OS images are read from; empty for croit's own catalog.
      returned: always
      type: str
      sample: croit/os-images
    username:
      description: User croit logs in as; empty for anonymous reads.
      returned: always
      type: str
      sample: croit-pull
    passwordSet:
      description: Whether croit has a password stored.
      returned: always
      type: bool
      sample: true
    plaintext:
      description: Whether croit talks to the registry over plain HTTP.
      returned: always
      type: bool
      sample: false
config:
  description: Ceph build settings after the change (C(ImageConfigResponse) in the croit API).
  returned: when O(variant) is set
  type: dict
  contains:
    variant:
      description: The Ceph build the images carry.
      returned: always
      type: str
      sample: enhanced
    hasEnhancedImages:
      description: Whether images of croit's enhanced build are available.
      returned: always
      type: bool
      sample: true
    frontierEnabled:
      description: Whether the frontier build is enabled.
      returned: always
      type: bool
      sample: false
task:
  description: The croit background task a variant switch ran as (C(TaskResponse) in the croit API).
  returned: when a task ran
  type: dict
  contains:
    id:
      description: Task id, usable with M(croit.ceph.task) and M(croit.ceph.task_info).
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as croit's task list shows it.
      returned: always
      type: str
      sample: Update server
    state:
      description: V(WAITING), V(RUNNING), V(FINISHED), V(FAILED) or V(CANCELED).
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
      sample: "done"
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

REGISTRY_FIELDS = ("registry", "repository", "username", "plaintext")


class ImageConfigModule(CroitModule):
    def __init__(self):
        super(ImageConfigModule, self).__init__(
            dict(
                archs=dict(type="dict", options=dict(x86_64=dict(type="bool"), arm64=dict(type="bool"))),
                registry=dict(
                    type="dict",
                    options=dict(
                        registry=dict(type="str"),
                        repository=dict(type="str"),
                        username=dict(type="str"),
                        password=dict(type="str", no_log=True),
                        update_password=dict(type="str", default="on_create", choices=["on_create", "always"]),
                        plaintext=dict(type="bool"),
                    ),
                ),
                variant=dict(type="str", choices=["core", "enhanced", "frontier"]),
            ),
            required_one_of=[("archs", "registry", "variant")],
        )

    def run(self):
        p = self.params
        before, after, result, writes = {}, {}, {}, []

        if p["archs"] is not None:
            current = self.get("/images/archs") or {}
            wanted = dict(current)
            wanted.update((k, v) for k, v in p["archs"].items() if v is not None)
            if not any(wanted.get(k) for k in ("x86_64", "arm64")):
                self.module.fail_json(msg="At least one architecture must stay enabled")
            before["archs"], after["archs"] = dict(current), wanted
            result["archs"] = current
            if wanted != current:
                writes.append(("PUT", "/images/archs", dict(x86_64=bool(wanted.get("x86_64")), arm64=bool(wanted.get("arm64")))))

        if p["registry"] is not None:
            current = self.get("/images/registry") or {}
            reg = p["registry"]
            view = dict((k, current.get(k)) for k in REGISTRY_FIELDS)
            view["password_set"] = bool(current.get("passwordSet"))
            wanted = dict(view)
            wanted.update((k, reg[k]) for k in REGISTRY_FIELDS if reg[k] is not None)
            send_password = reg["password"] is not None and (
                reg["update_password"] == "always" or not current.get("passwordSet")
            )
            if wanted.get("username") == "":
                wanted["password_set"] = False
            elif send_password:
                wanted["password_set"] = True
            before["registry"] = view
            after["registry"] = dict(wanted)
            if send_password:
                after["registry"]["password"] = "******** (changed)"
            result["registry"] = current
            if wanted != view or send_password:
                body = dict((k, wanted[k]) for k in REGISTRY_FIELDS if wanted.get(k) is not None)
                if send_password:
                    body["password"] = reg["password"]
                writes.append(("PUT", "/images/registry", body))

        if p["variant"] is not None:
            current = self.get("/images/config") or {}
            before["variant"], after["variant"] = current.get("variant"), p["variant"]
            result["config"] = current
            if current.get("variant") != p["variant"]:
                writes.append(("PUT", "/images/config", dict(variant=p["variant"])))

        changed = bool(writes)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, **result)

        for method, path, body in writes:
            task = self.handle_task(self.write(method, path, body=body))
            if task is not None:
                result["task"] = task
        if p["archs"] is not None:
            result["archs"] = self.get("/images/archs")
        if p["registry"] is not None:
            result["registry"] = self.get("/images/registry")
        if p["variant"] is not None:
            result["config"] = self.get("/images/config")
        self.exit(changed=True, before=before, after=after, **result)


def main():
    ImageConfigModule().run()


if __name__ == "__main__":
    main()
