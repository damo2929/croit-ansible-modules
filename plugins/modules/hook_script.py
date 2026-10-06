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
  - Creates, updates and deletes the scripts croit runs when an event happens on the cluster. A script is
    identified by its O(name).
  - The script text is compared exactly and only read when O(content) is set. The points a script runs at are
    compared as a set, so their order does not matter. Options left unset are left alone.
  - Hook points and server names are checked against croit before anything is written, in check mode too.
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
    details:
      - The diff shows the script text (when O(content) is set) and, per hook point, the servers it runs on.
options:
  name:
    description:
      - The script's file name, unique across the cluster, for example V(tune-disks.sh). It identifies the
        script; renaming is not supported.
    type: str
    required: true
  state:
    description:
      - V(present) creates the script or updates its text and hook points.
      - V(absent) deletes it, which also detaches it from every point. A script that does not exist is left
        alone.
    type: str
    choices: [present, absent]
    default: present
  content:
    description:
      - The script itself, compared exactly. Required to create a script; when not set, an existing script's
        text is left alone.
      - Load it from a file with C(lookup('ansible.builtin.file', ...)) or C(lookup('ansible.builtin.template', ...)).
    type: str
  hooks:
    description:
      - The complete list of points the script runs at. An empty list detaches it from every point.
      - When not set, the points are left alone. Each point may be listed only once.
    type: list
    elements: dict
    suboptions:
      event:
        description:
          - The hook point, for example V(PostDaemonStart), V(OnHealthDegrade) or V(PostBackupFailed). The
            module checks it against the points this croit release offers and lists them on a mismatch.
        type: str
        required: true
      servers:
        description:
          - Servers, by hostname or id, the script runs on, for points that fire on cluster nodes.
          - When not set, it runs on every server. Not valid for points that fire on the management node, which
            fail the task when given servers.
        type: list
        elements: str
notes:
  - Hook scripts run as C(root) on the servers or on the management node; review them like any other code
    that runs with full privileges.
seealso:
  - module: croit.ceph.config_template
    description: Template config files instead of scripting changes.
  - module: croit.ceph.server_info
    description: Find the hostnames and ids O(hooks[].servers) accepts.
  - name: croit API reference
    description: The C(/events) endpoints this module uses, including the list of hook points.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Tune disks after every daemon start, on two nodes
  croit.ceph.hook_script:
    name: tune-disks.sh
    content: "{{ lookup('ansible.builtin.file', 'files/tune-disks.sh') }}"
    hooks:
      - event: PostDaemonStart
        servers: [storage-01, storage-02]
  register: tune_disks

- name: Show croit's id of the script
  ansible.builtin.debug:
    msg: "tune-disks.sh has id {{ tune_disks.script.id }}"

- name: Notify on health changes (runs on the management node)
  croit.ceph.hook_script:
    name: notify.sh
    content: |
      #!/bin/sh
      logger "ceph health changed: $*"
    hooks:
      - event: OnHealthDegrade
      - event: OnHealthRecover

- name: Run the disk tuning on every server instead
  croit.ceph.hook_script:
    name: tune-disks.sh
    hooks:
      - event: PostDaemonStart

- name: Remove a script
  croit.ceph.hook_script:
    name: old.sh
    state: absent
"""

RETURN = r"""
script:
  description:
    - The script as croit lists it after the change (C(ScriptInfo) in the croit API), without its text.
    - In check mode, the script before the change. Empty when the script does not exist.
  returned: always
  type: dict
  contains:
    id:
      description: croit's id of the script.
      returned: when the script exists
      type: int
      sample: 7
    name:
      description: The script's file name.
      returned: when the script exists
      type: str
      sample: notify.sh
    hooks:
      description:
        - The points the script runs at, each with C(event), C(allServers) and C(serverIds).
        - Points that fire on the management node have C(allServers=false) and no server ids.
      returned: when the script exists
      type: list
      elements: dict
      sample:
        - event: OnHealthDegrade
          allServers: false
          serverIds: null
        - event: PostDaemonStart
          allServers: false
          serverIds: [3, 4]
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
