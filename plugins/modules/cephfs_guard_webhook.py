#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /services/cephfsguard
# croit-api: GET /services/cephfsguard/{configId}/webhooks
# croit-api: POST /services/cephfsguard/{configId}/webhooks
# croit-api: PATCH /services/cephfsguard/{configId}/webhooks/{webhookId}
# croit-api: DELETE /services/cephfsguard/{configId}/webhooks/{webhookId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: cephfs_guard_webhook
short_description: Manage cephfs-guard alerting webhooks on a croit cluster
version_added: 0.1.0
description:
  - Add, update and remove the webhooks cephfs-guard POSTs detection alerts to, for one guarded CephFS volume.
  - A webhook is identified by its O(volume) and O(url).
  - croit applies webhook changes on the next deploy of the volume's cephfs-guard instances.
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
  volume:
    description:
      - The CephFS volume whose cephfs-guard sends the alerts. cephfs-guard must be enabled for it
        (see M(croit.ceph.cephfs_guard)).
    type: str
    required: true
  url:
    description:
      - URL the alerts are POSTed to.
      - Treated as a secret, because such URLs often carry an access token; it is masked in logs, results and diffs.
    type: str
    required: true
  alert_timeout:
    description:
      - How long cephfs-guard waits for the webhook per alert, such as V(5s) or V(500ms).
        croit uses V(5s) when a webhook is added without it.
      - Not to be confused with O(timeout), the timeout of this module's own requests to croit.
    type: str
  state:
    description:
      - Whether the webhook should exist.
    type: str
    choices: [present, absent]
    default: present
"""

EXAMPLES = r"""
- name: Send cephfs-guard alerts to the on-call system
  croit.ceph.cephfs_guard_webhook:
    volume: cephfs
    url: "https://alerts.example.com/hooks/{{ vault_alert_token }}"
    alert_timeout: 10s

- name: Remove it
  croit.ceph.cephfs_guard_webhook:
    volume: cephfs
    url: "https://alerts.example.com/hooks/{{ vault_alert_token }}"
    state: absent
"""

RETURN = r"""
webhook:
  description:
    - The webhook as croit reports it after the change (C(CephfsGuardWebhookResponse)), with the URL masked.
      Empty when the webhook does not exist.
  returned: always
  type: dict
  sample:
    id: 3
    url: "********"
    alert_timeout: 10s
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

DEFAULT_TIMEOUT = "5s"
MASK = "********"


def masked(webhook):
    if not webhook:
        return {}
    result = dict(webhook)
    result["url"] = MASK
    return result


def view(webhook):
    if not webhook:
        return {}
    return dict(url=MASK, timeout=webhook.get("timeout"))


class WebhookModule(CroitModule):
    def __init__(self):
        super(WebhookModule, self).__init__(
            dict(
                volume=dict(type="str", required=True),
                url=dict(type="str", required=True, no_log=True),
                alert_timeout=dict(type="str"),
                state=dict(type="str", default="present", choices=["present", "absent"]),
            ),
            wait=False,
        )

    def config_id(self):
        volume = self.params["volume"]
        configs = [c for c in self.get_list("/services/cephfsguard") if c.get("volume") == volume]
        if not configs:
            if self.params["state"] == "absent":
                return None
            self.module.fail_json(msg="cephfs-guard is not enabled for volume %r; enable it with croit.ceph.cephfs_guard first" % volume)
        return configs[0]["id"]

    def run(self):
        p = self.params
        config_id = self.config_id()
        if config_id is None:
            self.exit(changed=False, webhook={})
        base = path_join("services", "cephfsguard", config_id, "webhooks")
        hooks = (self.get(base) or {}).get("webhooks") or []
        url = p["url"].strip()
        current = next((h for h in hooks if (h.get("url") or "").strip() == url), None)
        timeout = p["alert_timeout"].strip() if p["alert_timeout"] is not None else None

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, webhook={})
            if not self.check_mode:
                self.write("DELETE", path_join("services", "cephfsguard", config_id, "webhooks", current["id"]))
            self.exit(changed=True, before=view(current), after={}, webhook={})

        if current is None:
            body = dict(url=url)
            if timeout is not None:
                body["timeout"] = timeout
            after = dict(url=MASK, timeout=timeout or DEFAULT_TIMEOUT)
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, webhook={})
            created = self.write("POST", base, body=body)
            self.exit(changed=True, before={}, after=after, webhook=masked(created))

        before = view(current)
        if timeout is None or timeout == current.get("timeout"):
            self.exit(changed=False, before=before, after=before, webhook=masked(current))
        after = dict(before, timeout=timeout)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, webhook=masked(current))
        self.write("PATCH", path_join("services", "cephfsguard", config_id, "webhooks", current["id"]), body=dict(url=url, timeout=timeout))
        refreshed = next((h for h in (self.get(base) or {}).get("webhooks") or [] if h.get("id") == current["id"]), current)
        self.exit(changed=True, before=before, after=after, webhook=masked(refreshed))


def main():
    WebhookModule().run()


if __name__ == "__main__":
    main()
