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
  - A setting is identified by O(name). The value is converted to the setting's type (C(BOOL), C(INT) or
    C(STRING)) before it is sent, and a value that does not fit fails before anything is written.
  - The module compares the requested value with what croit reports and only writes when they differ.
  - Some settings reconfigure or restart croit services when they change; croit runs the change as a task.
  - Use M(croit.ceph.setting_info) with O(croit.ceph.setting_info#module:available=true) to list the settings,
    their types and their defaults.
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
    details:
      - The diff shows whether a value is stored (C(state)) and the stored value.
options:
  name:
    description:
      - Name of the setting, exactly as croit's settings list shows it.
      - An unknown name fails the task and lists the settings croit offers.
    type: str
    required: true
  value:
    description:
      - Value to store. Required with O(state=present).
      - Converted to the setting's type before sending; for a C(BOOL) setting V(yes), V(on) and V(1) also mean
        V(true).
      - Compared as croit reports it, so V(true) matches V("true") and V(30) matches V("30").
    type: raw
  state:
    description:
      - V(present) stores O(value). Storing a value equal to croit's default still counts as a change, because
        croit then keeps a row for the setting.
      - V(absent) drops the stored value, which puts the setting back on croit's default.
    type: str
    choices: [present, absent]
    default: present
notes:
  - Changing a setting can restart croit services; plan such changes like any other maintenance.
seealso:
  - module: croit.ceph.setting_info
    description: List croit settings, their types, defaults and current values.
  - module: croit.ceph.ceph_config
    description: Manage Ceph options rather than croit settings.
  - name: croit API reference
    description: The C(/settings) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
# croit does not publish a fixed list of setting names; look them up first.
- name: List every setting croit offers
  croit.ceph.setting_info:
    available: true
  register: all_settings

- name: Show their names and types
  ansible.builtin.debug:
    msg: "{{ all_settings.settings | map(attribute='name') | list }}"

- name: Store a boolean setting
  croit.ceph.setting:
    name: "{{ setting_name }}"
    value: true
  register: stored

- name: Show what croit now reports
  ansible.builtin.debug:
    msg: "{{ stored.setting.name }} = {{ stored.setting.value }} (default {{ stored.setting.default }})"

- name: Put the setting back on croit's default
  croit.ceph.setting:
    name: "{{ setting_name }}"
    state: absent
"""

RETURN = r"""
setting:
  description:
    - The setting as croit reports it after the change (C(CroitSettingResponse) in the croit API).
    - In check mode, the setting before the change.
  returned: always
  type: dict
  contains:
    name:
      description: What the setting is called, as croit's settings list shows it.
      returned: always
      type: str
      sample: example setting
    type:
      description: What the value holds, one of C(STRING), C(INT) or C(BOOL).
      returned: always
      type: str
      sample: BOOL
    level:
      description: How prominently croit offers the setting, one of C(SIMPLE), C(ADVANCED) or C(DEBUG).
      returned: always
      type: str
      sample: SIMPLE
    value:
      description: What the setting is worth on this cluster, as a string; its default where nothing is stored.
      returned: always
      type: str
      sample: "true"
    default:
      description: What the setting is worth when nothing is stored, as a string.
      returned: always
      type: str
      sample: "false"
    customized:
      description: Whether this cluster stores a value for the setting.
      returned: always
      type: bool
      sample: true
    description:
      description: What the setting does, and what changing it costs.
      returned: always
      type: str
      sample: Enables the example behaviour.
task:
  description:
    - The croit background task the change ran as (C(ManagedThreadTask) in the croit API).
    - With O(wait=true) this is the finished task. With O(wait=false) it can still be running; follow it with
      M(croit.ceph.task).
  returned: when the change ran as a croit task
  type: dict
  contains:
    id:
      description: The task's id, which M(croit.ceph.task) and M(croit.ceph.task_info) accept.
      returned: always
      type: int
      sample: 412
    name:
      description: What the task does, as the croit task list shows it.
      returned: always
      type: str
      sample: Set ceph config
    state:
      description: The task's state, one of C(WAITING), C(RUNNING), C(FINISHED), C(FAILED) or C(CANCELED).
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
      sample: ""
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
