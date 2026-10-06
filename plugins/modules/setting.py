#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /settings/available
# croit-api: PUT /settings
# croit-api: DELETE /settings

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: setting
short_description: Manage croit settings
version_added: 0.1.0
description:
  - Sets a croit setting (croit's own behaviour, not a Ceph option), or puts it back on croit's default.
  - Some settings reconfigure or restart croit services when they change; croit runs the change as a task.
  - Use M(croit.ceph.setting_info) with O(croit.ceph.setting_info#module:available=true) to list the settings
    and their types.
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
      - Name of the setting, as croit's settings list shows it.
    type: str
    required: true
  value:
    description:
      - Value to store. Required with O(state=present).
      - Compared as croit reports it, so V(true) matches V("true") and V(30) matches V("30").
    type: raw
  state:
    description:
      - V(present) stores O(value), even when it equals croit's default.
      - V(absent) drops the stored value, which puts the setting back on croit's default.
    type: str
    choices: [present, absent]
    default: present
"""

EXAMPLES = r"""
- name: Store a croit setting
  croit.ceph.setting:
    name: "{{ setting_name }}"
    value: true

- name: Back to croit's default
  croit.ceph.setting:
    name: "{{ setting_name }}"
    state: absent
"""

RETURN = r"""
setting:
  description:
    - The setting as croit reports it after the change (C(CroitSettingResponse) in the croit API).
    - Before the change in check mode.
  returned: always
  type: dict
  sample:
    name: example setting
    type: BOOL
    value: "true"
    default: "false"
    customized: true
task:
  description: The croit background task the change ran as.
  returned: when a task ran
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def text(value):
    """Canonical text for a setting value; croit reports every value as a string."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    result = str(value).strip()
    return result.lower() if result.lower() in ("true", "false") else result


def typed(value, kind):
    """The value in the JSON type the setting holds."""
    if kind == "BOOL":
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().lower()
        if lowered in ("true", "yes", "on", "1"):
            return True
        if lowered in ("false", "no", "off", "0"):
            return False
        raise ValueError("expected a boolean, got %r" % (value,))
    if kind == "INT":
        if isinstance(value, bool):
            raise ValueError("expected an integer, got %r" % (value,))
        return int(str(value).strip())
    return value if isinstance(value, str) else str(value)


def view(setting):
    if not setting or not setting.get("customized"):
        return dict(state="absent")
    return dict(state="present", value=setting.get("value"))


class SettingModule(CroitModule):
    def __init__(self):
        super(SettingModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                value=dict(type="raw"),
                state=dict(type="str", default="present", choices=["present", "absent"]),
            ),
            required_if=[("state", "present", ["value"])],
        )

    def find(self):
        settings = self.get_list("/settings/available")
        for setting in settings:
            if setting.get("name") == self.params["name"]:
                return setting
        self.module.fail_json(
            msg="croit has no setting %r. Known settings: %s"
            % (self.params["name"], ", ".join(sorted(s.get("name", "") for s in settings)))
        )

    def run(self):
        p = self.params
        current = self.find()
        before = view(current)

        if p["state"] == "absent":
            changed = before["state"] == "present"
            after = dict(state="absent")
            method = "DELETE"
            body = dict(name=p["name"])
        else:
            try:
                value = typed(p["value"], current.get("type"))
            except ValueError as e:
                self.module.fail_json(msg="value for setting %r: %s" % (p["name"], e))
            changed = before["state"] != "present" or text(current.get("value")) != text(value)
            after = dict(state="present", value=text(value))
            method = "PUT"
            body = dict(name=p["name"], value=value)

        result = dict(setting=current)
        if not changed:
            self.exit(changed=False, before=before, after=before, **result)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, **result)

        task = self.handle_task(self.write(method, "/settings", body=body))
        if task is not None:
            result["task"] = task
        result["setting"] = self.find()
        self.exit(changed=True, before=before, after=after, **result)


def main():
    SettingModule().run()


if __name__ == "__main__":
    main()
