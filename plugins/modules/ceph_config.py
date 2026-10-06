#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /config/available
# croit-api: GET /config
# croit-api: PUT /config
# croit-api: DELETE /config

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: ceph_config
short_description: Manage Ceph configuration options on a croit cluster
version_added: 0.1.0
description:
  - Sets, pins to a default, or unsets one Ceph option in the monitor configuration database through croit.
  - An option is identified by O(name), O(section) and O(mask). The name may be spelled with underscores or
    spaces; croit stores it with spaces and the module treats both spellings alike.
  - The module compares the requested state with what croit reports and only writes when they differ, so
    re-running a task reports no change.
  - Use M(croit.ceph.ceph_config_info) to read options without changing them.
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
      - The diff shows how croit manages the option (C(state)) and its value or pinned default.
options:
  name:
    description:
      - Name of the Ceph option, for example V(osd_max_backfills) or V(osd max backfills).
      - Underscores and spaces are treated alike when finding the option; the name is sent as written.
      - When croit does not document the option, the module warns and still sets it.
    type: str
    required: true
  section:
    description:
      - Ceph section the value applies to, for example V(global), V(osd), V(mon) or V(osd.12).
    type: str
    default: global
  mask:
    description:
      - Mask narrowing the section to part of the cluster, for example V(class:ssd) or V(host:node1).
      - An empty string means no mask, so the value applies to the whole section.
    type: str
    default: ''
  value:
    description:
      - Value to set the option to.
      - Booleans, numbers and strings are compared the way croit reports them, so V(true), V("true"), V(1.0)
        and V(1) match where they mean the same.
      - For options croit reports in bytes, a binary unit such as V(4G) is converted to bytes before it is
        sent and compared.
      - Mutually exclusive with O(use_default). With O(state=present), one of O(value) and O(use_default) is
        required.
    type: raw
  use_default:
    description:
      - Pin the option to croit's default (V(croit)) or to Ceph's own default (V(ceph)) instead of setting a
        value.
      - Pinning to the Ceph default stops croit from applying its own default to the option later.
      - Mutually exclusive with O(value).
    type: str
    choices: [croit, ceph]
  state:
    description:
      - V(present) sets O(value) or pins O(use_default).
      - V(absent) unsets the option at this section and mask, so it reads like an option nobody configured.
        An option that is already unset is left alone.
    type: str
    choices: [present, absent]
    default: present
notes:
  - Some options only take effect after the daemons restart; C(canUpdateAtRuntime) in RV(config) tells you
    which.
  - Ceph may refuse a value for an option croit does not document; the module warns before sending it.
seealso:
  - module: croit.ceph.ceph_config_info
    description: Read Ceph options and their current values.
  - module: croit.ceph.setting
    description: Manage croit's own settings rather than Ceph options.
  - module: croit.ceph.cluster_tuning
    description: Recovery speed, full ratios and other cluster-wide knobs croit manages directly.
  - name: croit API reference
    description: The C(/config) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph configuration
    description: How Ceph's monitor configuration database, sections and masks work.
    link: https://docs.ceph.com/en/latest/rados/configuration/ceph-conf/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Allow more backfills per OSD
  croit.ceph.ceph_config:
    name: osd_max_backfills
    section: osd
    value: 2

- name: Give SSD OSDs a larger memory target
  croit.ceph.ceph_config:
    name: osd_memory_target
    section: osd
    mask: class:ssd
    value: 8G
  register: memory_target

- name: Report whether the change needs an OSD restart
  ansible.builtin.debug:
    msg: "Runtime update supported: {{ memory_target.config.canUpdateAtRuntime }}"

- name: Keep Ceph's default and stop croit applying its own
  croit.ceph.ceph_config:
    name: mon_max_pg_per_osd
    use_default: ceph

- name: Unset an option again
  croit.ceph.ceph_config:
    name: osd_max_backfills
    section: osd
    state: absent
"""

RETURN = r"""
config:
  description:
    - The option as croit reports it after the change (C(CephConfigResponse) in the croit API), for the
      requested section and mask.
    - In check mode, the option before the change. Empty when croit has no row for the option at this section
      and mask.
  returned: always
  type: dict
  contains:
    name:
      description: The option name, spelled with spaces as croit stores it.
      returned: when the option exists
      type: str
      sample: osd max backfills
    section:
      description: The Ceph section the value applies to.
      returned: when the option exists
      type: str
      sample: osd
    mask:
      description: The mask narrowing the section, empty for the whole section.
      returned: when the option exists
      type: str
      sample: ""
    currentValue:
      description: What the option is set to, or Ceph's default where nothing sets it.
      returned: when the option exists
      type: raw
      sample: 2
    defaultValue:
      description: What Ceph uses when nothing sets the option.
      returned: when the option exists
      type: raw
      sample: 1
    customized:
      description: Whether an operator set the value, as opposed to croit's or Ceph's default.
      returned: when the option exists
      type: bool
      sample: true
    useCroitDefault:
      description: Whether the option is pinned to croit's default.
      returned: when the option exists
      type: bool
      sample: false
    useCephDefault:
      description: Whether the option is pinned to Ceph's default.
      returned: when the option exists
      type: bool
      sample: false
    canUpdateAtRuntime:
      description: Whether Ceph applies a change without restarting the daemon; null when unknown.
      returned: when the option exists
      type: bool
      sample: true
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

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule, parse_size


def normalise_name(name):
    """croit stores option names with spaces; ceph accepts underscores too."""
    return " ".join(name.replace("_", " ").split()).lower()


def normalise_value(value):
    """Canonical text for comparing values croit reports with values users write."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    if text.lower() in ("true", "false"):
        return text.lower()
    try:
        number = float(text)
        if number == int(number):
            return str(int(number))
    except (ValueError, OverflowError):
        # Not a number, or inf/nan: compare as text.
        return text
    return repr(number)


def row_state(row):
    """How croit manages an option row: 'croit', 'ceph', 'value' or 'unset'."""
    if not row:
        return "unset"
    if row.get("useCroitDefault"):
        return "croit"
    if row.get("useCephDefault"):
        return "ceph"
    if row.get("customized"):
        return "value"
    return "unset"


def view(row):
    """Managed view of an option row, for diffs."""
    state = row_state(row)
    result = dict(state=state)
    if state == "value":
        result["value"] = row.get("currentValue")
    elif state in ("croit", "ceph"):
        result["use_default"] = state
    return result


class CephConfigModule(CroitModule):
    def __init__(self):
        super(CephConfigModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                section=dict(type="str", default="global"),
                mask=dict(type="str", default=""),
                value=dict(type="raw"),
                use_default=dict(type="str", choices=["croit", "ceph"]),
                state=dict(type="str", default="present", choices=["present", "absent"]),
            ),
            mutually_exclusive=[("value", "use_default")],
            required_if=[("state", "present", ("value", "use_default"), True)],
        )

    def rows_for_name(self):
        """Every row croit has for this option name, from the documented list and the configured list."""
        wanted = normalise_name(self.params["name"])
        rows = [r for r in self.get_list("/config/available") if normalise_name(r.get("name", "")) == wanted]
        if not rows:
            # An option ceph does not document can still be configured.
            rows = [r for r in self.get_list("/config") if normalise_name(r.get("name", "")) == wanted]
        return rows

    def find_row(self, rows):
        section = self.params["section"]
        mask = self.params["mask"] or ""
        for row in rows:
            if (row.get("section") or "global") == section and (row.get("mask") or "") == mask:
                return row
        return None

    def desired_value(self, rows):
        value = self.params["value"]
        units = set(r.get("unit") for r in rows)
        if "BYTES" in units and isinstance(value, str):
            try:
                return parse_size(value)
            except ValueError:
                return value
        return value

    def target(self):
        return dict(name=self.params["name"], section=self.params["section"], mask=self.params["mask"] or "")

    def run(self):
        p = self.params
        rows = self.rows_for_name()
        if not rows and p["state"] == "present":
            self.module.warn("croit does not know the Ceph option %r; ceph may refuse it" % p["name"])
        current = self.find_row(rows)
        before = view(current)

        body = self.target()
        if p["state"] == "absent":
            changed = before["state"] != "unset"
            after = dict(state="unset")
            method = "DELETE"
        elif p["use_default"]:
            changed = before["state"] != p["use_default"]
            after = dict(state=p["use_default"], use_default=p["use_default"])
            body["useCroitDefault" if p["use_default"] == "croit" else "useCephDefault"] = True
            method = "PUT"
        else:
            value = self.desired_value(rows)
            changed = before["state"] != "value" or normalise_value(current.get("currentValue")) != normalise_value(value)
            after = dict(state="value", value=value)
            body["value"] = value
            method = "PUT"

        result = dict(config=current or {})
        if not changed:
            self.exit(changed=False, before=before, after=before, **result)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, **result)

        task = self.handle_task(self.write(method, "/config", body=body))
        if task is not None:
            result["task"] = task
        result["config"] = self.find_row(self.rows_for_name()) or {}
        self.exit(changed=True, before=before, after=after, **result)


def main():
    CephConfigModule().run()


if __name__ == "__main__":
    main()
