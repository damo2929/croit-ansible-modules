#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /images
# croit-api: POST /images/{image}/start-download
# croit-api: DELETE /images/{image}
# croit-api: POST /images/default

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: image
short_description: Download, remove and select croit OS images
version_added: 0.1.0
description:
  - Makes sure a croit OS image is downloaded onto the management node (O(state=present)) or that its
    files are removed again (O(state=absent)), and optionally makes it the default image for its CPU
    architecture.
  - Removing an image only frees disk space on the management node; the image stays in croit's list
    and can be downloaded again.
  - Architectures, the image registry and the Ceph build are managed with M(croit.ceph.image_config).
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
seealso:
  - module: croit.ceph.image_config
    description: Enabled architectures, the image registry and the Ceph build.
  - module: croit.ceph.server
    description: Pin a server to an image, or reboot it onto a new default.
  - name: croit API reference
    description: The croit REST API this module uses.
    link: https://www.croit.io/api-docs
options:
  id:
    description:
      - The image's id (a UUID), as listed by croit.
      - Mutually exclusive with O(latest).
    type: str
  latest:
    description:
      - Select the newest image croit offers for O(arch) instead of a fixed O(id).
      - Note that the selected image changes when croit publishes a new one.
    type: bool
  arch:
    description:
      - CPU architecture used with O(latest).
    type: str
    choices: [x86_64, arm64]
    default: x86_64
  state:
    description:
      - V(present) makes sure the image is downloaded; V(absent) removes its downloaded files.
      - croit refuses to remove a default image or one a server is configured with.
    type: str
    choices: [present, absent]
    default: present
  default:
    description:
      - V(true) makes the image the default for its architecture. Servers that follow the default boot it
        at their next reboot.
      - V(false) only checks that the image is not the default; to change the default, make another image
        the default instead.
    type: bool
  override_servers:
    description:
      - When making the image the default, also switch servers that are explicitly configured with another image.
    type: bool
    default: false
notes:
  - Making an image the default changes what servers that follow the default boot at their next reboot;
    nothing is rebooted by this module.
  - When the image is already being downloaded (for example by croit itself), the module waits for that
    download to finish with O(wait=true) and reports no change.
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Download the newest x86_64 image and make it the default
  croit.ceph.image:
    latest: true
    default: true
  register: newest

- name: Show which image is now the default
  ansible.builtin.debug:
    msg: "{{ newest.image.id }} ({{ newest.image.description }})"

- name: Keep a specific image downloaded
  croit.ceph.image:
    id: 4b1d3f6a-2c41-4f3e-9b55-0d6f0c6e9a10

- name: Free the disk space of an old image (it can be downloaded again)
  croit.ceph.image:
    id: 0e8c2b8e-7d3a-4f8e-a1c2-5a3c1d9e8f70
    state: absent
"""

RETURN = r"""
image:
  description:
    - The image as croit lists it after the change (C(ImageResponse) in the croit API).
    - Before the change in check mode.
  returned: always
  type: dict
  contains:
    id:
      description: The image's id.
      returned: always
      type: str
      sample: 4b1d3f6a-2c41-4f3e-9b55-0d6f0c6e9a10
    description:
      description: Human-readable name of the image.
      returned: always
      type: str
      sample: croit 2510.0 (squid)
    cpuArchitecture:
      description: CPU architecture the image is built for.
      returned: always
      type: str
      sample: x86_64
    cephVersionShort:
      description: The Ceph version the image carries.
      returned: always
      type: str
      sample: "19.2.3"
    downloaded:
      description: Whether the image's files are on the management node.
      returned: always
      type: bool
      sample: true
    downloading:
      description: Whether a download is in progress.
      returned: always
      type: bool
      sample: false
    isDefault:
      description: Whether the image is the default for its architecture.
      returned: always
      type: bool
      sample: true
task:
  description: The croit background task the last change ran as (C(TaskResponse) in the croit API).
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

import time

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

DEFAULT_KEY = dict(x86_64="defaultX86", arm64="defaultArm64")
LATEST_KEY = dict(x86_64="latestX86", arm64="latestArm64")
POLL_INTERVAL = 5


def image_list(reply):
    if isinstance(reply, list):
        return reply
    reply = reply or {}
    return reply.get("images") or reply.get("data") or []


class ImageModule(CroitModule):
    def __init__(self):
        super(ImageModule, self).__init__(
            dict(
                id=dict(type="str"),
                latest=dict(type="bool"),
                arch=dict(type="str", default="x86_64", choices=["x86_64", "arm64"]),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                default=dict(type="bool"),
                override_servers=dict(type="bool", default=False),
            ),
            mutually_exclusive=[("id", "latest")],
            required_one_of=[("id", "latest")],
        )

    def read(self):
        reply = self.get("/images")
        p = self.params
        if p["latest"]:
            image_id = (reply or {}).get(LATEST_KEY[p["arch"]])
            if not image_id:
                self.module.fail_json(msg="croit offers no %s image" % p["arch"])
        else:
            image_id = p["id"]
        image = next((i for i in image_list(reply) if i.get("id") == image_id), None)
        if image is None:
            self.module.fail_json(msg="croit does not list image %r; refresh the image list first" % image_id)
        default_id = (reply or {}).get(DEFAULT_KEY.get(image.get("cpuArchitecture"), "defaultX86"))
        return image, default_id

    @staticmethod
    def view(image, default_id):
        return dict(
            id=image.get("id"),
            arch=image.get("cpuArchitecture"),
            downloaded=bool(image.get("downloaded")),
            default=image.get("id") == default_id,
        )

    def wait_downloaded(self, image_id):
        deadline = time.monotonic() + self.params["wait_timeout"]
        while True:
            image, default_id = self.read_by_id(image_id)
            if image.get("downloaded"):
                return image
            if image.get("downloadError"):
                self.module.fail_json(msg="Download of image %s failed: %s" % (image_id, image["downloadError"]), image=image)
            if time.monotonic() >= deadline:
                self.module.fail_json(msg="Timed out waiting for image %s to download" % image_id, image=image)
            time.sleep(POLL_INTERVAL)

    def read_by_id(self, image_id):
        reply = self.get("/images")
        image = next((i for i in image_list(reply) if i.get("id") == image_id), None) or {}
        return image, (reply or {}).get(DEFAULT_KEY.get(image.get("cpuArchitecture"), "defaultX86"))

    def run(self):
        p = self.params
        image, default_id = self.read()
        image_id = image["id"]
        before = self.view(image, default_id)
        is_default = before["default"]

        if p["state"] == "absent" and p["default"]:
            self.module.fail_json(msg="An image cannot be the default and be removed at the same time")
        if p["default"] is False and is_default:
            self.module.fail_json(
                msg="Image %s is the default for %s; make another image the default instead" % (image_id, before["arch"])
            )

        after = dict(before)
        download = remove = make_default = False
        if p["state"] == "absent":
            remove = before["downloaded"]
            after["downloaded"] = False
        else:
            download = not before["downloaded"] and not image.get("downloading")
            after["downloaded"] = True
            if p["default"] and not is_default:
                make_default = True
                after["default"] = True

        changed = download or remove or make_default
        result = dict(image=image)
        if self.check_mode or (not changed and not image.get("downloading")):
            self.exit(changed=changed, before=before, after=after, **result)

        task = None
        if remove:
            self.write("DELETE", path_join("images", image_id))
        if download:
            task = self.handle_task(self.write("POST", path_join("images", image_id, "start-download")))
        if p["state"] == "present" and p["wait"] and (download or image.get("downloading")):
            self.wait_downloaded(image_id)
        if make_default:
            task = self.handle_task(
                self.write("POST", "/images/default", body=dict(default=image_id, overrideServers=p["override_servers"]))
            ) or task
        if task is not None:
            result["task"] = task
        result["image"] = self.read_by_id(image_id)[0]
        self.exit(changed=changed, before=before, after=after, **result)


def main():
    ImageModule().run()


if __name__ == "__main__":
    main()
