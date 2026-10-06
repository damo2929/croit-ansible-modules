#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /events/hook-scripts
# croit-api: POST /events/hook-scripts
# croit-api: PATCH /events/hook-scripts/{scriptId}
# croit-api: GET /events/scripts/{scriptId}
# croit-api: DELETE /events/scripts/{scriptId}
# croit-api: GET /events/hooks/hook-points
# croit-api: GET /servers

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: hook_script
short_description: Manage croit hook scripts
version_added: 0.1.0
description:
  - Create, update and delete the scripts croit runs when an event happens on the cluster, identified by
    their name.
  - The script text is compared exactly. The points a script runs at are compared as a set.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  name:
    description:
      - The script's file name, unique across the cluster.
    type: str
    required: true
  state:
    description:
      - Whether the script should exist. Deleting a script also detaches it from every point.
    type: str
    choices: [present, absent]
    default: present
  content:
    description:
      - The script itself. Required to create a script.
      - Use the M(ansible.builtin.file) lookup or C(lookup('ansible.builtin.template', ...)) to load it from a file.
    type: str
  hooks:
    description:
      - The complete list of points the script runs at. An empty list detaches it from every point.
      - When not set, the points are left alone.
    type: list
    elements: dict
    suboptions:
      event:
        description:
          - The hook point, for example V(PostDaemonStart) or V(OnHealthDegrade). The module checks it
            against the points this croit release offers.
        type: str
        required: true
      servers:
        description:
          - Servers, by hostname or id, the script runs on for points that fire on cluster nodes.
          - When not set, it runs on every server. Not valid for points that fire on the management node.
        type: list
        elements: str
"""

EXAMPLES = r"""
- name: Tune disks after every daemon start, on two nodes
  croit.ceph.hook_script:
    name: tune-disks.sh
    content: "{{ lookup('ansible.builtin.file', 'files/tune-disks.sh') }}"
    hooks:
      - event: PostDaemonStart
        servers: [storage-01, storage-02]

- name: Notify on health changes (management node)
  croit.ceph.hook_script:
    name: notify.sh
    content: |
      #!/bin/sh
      logger "ceph health changed: $*"
    hooks:
      - event: OnHealthDegrade
      - event: OnHealthRecover

- name: Remove a script
  croit.ceph.hook_script:
    name: old.sh
    state: absent
"""

RETURN = r"""
script:
  description:
    - The script as croit lists it after the change (C(ScriptInfo) in the croit API), without its text.
    - Before the change in check mode; empty when the script does not exist.
  returned: always
  type: dict
  sample:
    id: 7
    name: notify.sh
    hooks:
      - event: OnHealthDegrade
        allServers: false
        serverIds: null
"""

import json

from ansible.module_utils.common.text.converters import to_text

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import require_server
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def as_text(content):
    """Script text from GET /events/scripts/{id}.

    That endpoint answers text/plain, which the client parses as JSON when it
    happens to be valid JSON (a script consisting only of a number, say), so
    turn such values back into the text they came from.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content)


class HookScriptModule(CroitModule):
    def __init__(self):
        super(HookScriptModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                content=dict(type="str"),
                hooks=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        event=dict(type="str", required=True),
                        servers=dict(type="list", elements="str"),
                    ),
                ),
            ),
            wait=False,
            warnings=False,
        )
        self._servers = None
        self._points = None

    # Lookups --------------------------------------------------------------

    def find(self, name):
        for script in self.get_list("/events/hook-scripts"):
            if script.get("name") == name:
                return script
        return None

    def servers(self):
        if self._servers is None:
            self._servers = self.get_list("/servers")
        return self._servers

    def points(self):
        if self._points is None:
            self._points = dict((p["name"], p) for p in self.get_list("/events/hooks/hook-points"))
        return self._points

    def hostnames(self, ids):
        by_id = dict((s.get("id"), s.get("hostname")) for s in self.servers())
        return sorted(to_text(by_id.get(i, i)) for i in ids or [])

    # Hooks ----------------------------------------------------------------

    def desired_hooks(self):
        """Requested hooks as API dicts, validated against croit's hook points."""
        if self.params["hooks"] is None:
            return None
        points = self.points()
        result = []
        seen = set()
        for hook in self.params["hooks"]:
            event = hook["event"]
            point = points.get(event)
            if point is None:
                self.module.fail_json(
                    msg="Unknown hook point %r. croit offers: %s" % (event, ", ".join(sorted(points)))
                )
            if event in seen:
                self.module.fail_json(msg="Hook point %r is listed more than once" % event)
            seen.add(event)
            servers = hook.get("servers")
            if not point.get("canChooseServer"):
                if servers is not None:
                    self.module.fail_json(
                        msg="Hook point %r fires on the management node; it takes no servers" % event
                    )
                result.append(dict(event=event, allServers=False, serverIds=None))
            elif servers is None:
                result.append(dict(event=event, allServers=True, serverIds=None))
            else:
                ids = sorted(set(require_server(self, s, self.servers())["id"] for s in servers))
                result.append(dict(event=event, allServers=False, serverIds=ids))
        return result

    def hook_key(self, hook):
        """Canonical, order-insensitive form of one SimpleHookInfo.

        Server selection is ignored for points that fire on the management
        node, whatever croit stores for them.
        """
        point = self.points().get(hook["event"])
        if point is not None and not point.get("canChooseServer"):
            return (hook["event"], "none", ())
        if hook.get("allServers"):
            return (hook["event"], "all", ())
        ids = tuple(sorted(hook.get("serverIds") or []))
        return (hook["event"], "some", ids)

    def hooks_view(self, hooks):
        """Readable hooks for diffs: event -> 'all' or sorted hostnames, or 'management node'."""
        view = {}
        for hook in hooks or []:
            event, kind, ids = self.hook_key(hook)
            if kind == "all":
                view[event] = "all servers"
            elif kind == "none":
                view[event] = "management node"
            else:
                view[event] = self.hostnames(ids)
        return view

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        current = self.find(p["name"])

        if p["state"] == "absent":
            if current is None:
                self.exit(changed=False, script={})
            if not self.check_mode:
                self.write("DELETE", path_join("events", "scripts", current["id"]))
            self.exit(changed=True, before=dict(name=current["name"]), after={}, script={})

        hooks = self.desired_hooks()

        if current is None:
            if p["content"] is None:
                self.module.fail_json(msg="content is required to create hook script %r" % p["name"])
            after = dict(name=p["name"], content=p["content"], hooks=self.hooks_view(hooks or []))
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, script={})
            self.write("POST", "/events/hook-scripts", body=dict(name=p["name"], contents=p["content"], hooks=hooks or []))
            self.exit(changed=True, before={}, after=after, script=self.find(p["name"]) or {})

        before = dict(name=current["name"], hooks=self.hooks_view(current.get("hooks")))
        after = dict(before)
        changes = {}
        if p["content"] is not None:
            current_content = as_text(self.get(path_join("events", "scripts", current["id"])))
            before["content"] = current_content
            after["content"] = p["content"]
            if current_content != p["content"]:
                changes["contents"] = p["content"]
        if hooks is not None:
            if set(map(self.hook_key, hooks)) != set(map(self.hook_key, current.get("hooks") or [])):
                changes["hooks"] = hooks
                after["hooks"] = self.hooks_view(hooks)

        if not changes:
            self.exit(changed=False, before=before, after=after, script=current)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, script=current)
        self.write("PATCH", path_join("events", "hook-scripts", current["id"]), body=changes)
        self.exit(changed=True, before=before, after=after, script=self.find(p["name"]) or {})


def main():
    HookScriptModule().run()


if __name__ == "__main__":
    main()
