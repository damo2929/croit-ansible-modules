#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /modules
# croit-api: GET /modules/{name}
# croit-api: PATCH /modules/{name}
# croit-api: POST /modules/{name}/enable
# croit-api: POST /modules/{name}/disable

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: mgr_module
short_description: Enable, disable and configure Ceph manager modules on a croit cluster
version_added: 0.1.0
description:
  - Enables or disables one Ceph manager module and sets its options through the croit API.
  - Only the options listed in O(options) are managed; every other option keeps its value.
  - The balancer and the dashboard go through croit's own handling when enabled. Enabling the balancer
    turns it on in upmap mode and raises the cluster's minimum client release to luminous when needed;
    croit asks first when older clients are connected, see O(ignore_warnings). Enabling the dashboard
    imports croit's users into it.
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
  name:
    description:
      - Name of the manager module as ceph knows it, for example V(pg_autoscaler), V(prometheus) or V(balancer).
    type: str
    required: true
  enabled:
    description:
      - Whether the module should be enabled. Left alone when not set.
      - Modules ceph runs unconditionally (C(alwaysOn)) cannot be disabled; the balancer is the exception,
        because croit switches it on and off through its own endpoints.
    type: bool
  options:
    description:
      - Module options to set, by option name without the module prefix, for example C(server_port).
      - A value of V(null) clears the option, so ceph's default applies again.
      - Values are compared as the text ceph stores; booleans are compared case-insensitively.
      - Unknown option names fail the task and list the options the module has.
    type: dict
"""

EXAMPLES = r"""
- name: Enable the prometheus exporter on port 9283
  croit.ceph.mgr_module:
    name: prometheus
    enabled: true
    options:
      server_port: 9283

- name: Turn on the balancer (upmap)
  croit.ceph.mgr_module:
    name: balancer
    enabled: true
    ignore_warnings: true

- name: Put an option back on ceph's default
  croit.ceph.mgr_module:
    name: pg_autoscaler
    options:
      sleep_interval: null
"""

RETURN = r"""
module:
  description: The module as croit reports it after the change (C(CephModuleResponse) in the croit API).
  returned: always
  type: dict
  sample:
    name: prometheus
    enabled: true
    alwaysOn: false
    canRun: true
options:
  description:
    - The values of the options listed in O(options) after the change, keyed by option name.
  returned: when O(options) is set
  type: dict
  sample:
    server_port: "9283"
task:
  description: The croit background task enabling or disabling the module ran as, when croit answered one.
  returned: when a task ran
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

# Modules croit switches through its own handling even though ceph runs them always.
TOGGLEABLE_ALWAYS_ON = ("balancer",)


def as_text(value):
    """Option value as the text ceph stores; None stays None (cleared)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def same_value(current, wanted, option_type):
    if current is None or wanted is None:
        return current == wanted
    if option_type == "bool" or current.lower() in ("true", "false"):
        return current.lower() == wanted.lower()
    return current == wanted


class MgrModule(CroitModule):
    def __init__(self):
        super(MgrModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                enabled=dict(type="bool"),
                options=dict(type="dict"),
            ),
        )

    def find_module(self):
        name = self.params["name"]
        modules = self.get_list("/modules")
        for module in modules:
            if module.get("name") == name:
                return module
        self.module.fail_json(
            msg="Ceph has no manager module %r. Known modules: %s" % (name, ", ".join(sorted(m.get("name") for m in modules)))
        )

    def run(self):
        p = self.params
        name = p["name"]
        module = self.find_module()
        path = path_join("modules", name)

        before = {}
        after = {}
        result = dict(module=module)

        toggle = None
        if p["enabled"] is not None:
            before["enabled"] = bool(module.get("enabled"))
            after["enabled"] = p["enabled"]
            if before["enabled"] != p["enabled"]:
                if not p["enabled"] and module.get("alwaysOn") and name not in TOGGLEABLE_ALWAYS_ON:
                    self.module.fail_json(msg="Ceph always runs manager module %r; it cannot be disabled" % name, module=module)
                toggle = "enable" if p["enabled"] else "disable"

        changes = {}
        if p["options"]:
            rows = self.get_list(path)
            current = dict((row.get("name"), row) for row in rows)
            unknown = sorted(k for k in p["options"] if k not in current)
            if unknown:
                self.module.fail_json(
                    msg="Manager module %r has no option(s) %s. Its options: %s"
                    % (name, ", ".join(unknown), ", ".join(sorted(current)))
                )
            before["options"] = {}
            after["options"] = {}
            for key, value in p["options"].items():
                row = current[key]
                wanted = as_text(value)
                before["options"][key] = row.get("value")
                after["options"][key] = wanted
                if not same_value(row.get("value"), wanted, row.get("type")):
                    changes[key] = value
            if not changes:
                after["options"] = dict(before["options"])
            result["options"] = dict(before["options"])

        changed = bool(changes or toggle)
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, **result)

        if changes:
            self.write("PATCH", path, body=changes)
        if toggle:
            task = self.handle_task(self.write("POST", path_join("modules", name, toggle)))
            if task is not None:
                result["task"] = task

        result["module"] = self.find_module()
        if p["options"]:
            rows = dict((row.get("name"), row.get("value")) for row in self.get_list(path))
            result["options"] = dict((k, rows.get(k)) for k in p["options"])
        self.exit(changed=True, before=before, after=after, **result)


def main():
    MgrModule().run()


if __name__ == "__main__":
    main()
