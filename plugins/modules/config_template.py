#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /config-templates
# croit-api: PUT /config-templates/templates/{template}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: config_template
short_description: Manage croit config file templates
version_added: 0.1.0
description:
  - Sets one of croit's config file templates (the files croit renders onto the servers or the management
    node) to a custom template, or to one of croit's predefined templates.
  - croit offers a fixed set of templates; they cannot be created or deleted. To go back to croit's stock
    template, set O(predefined) to its name.
  - B(Caution.) Network and GRUB templates can make servers unreachable after their next boot, and saving the
    management node's NTP template restarts NTP. croit warns about these, see O(ignore_warnings).
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
      - The template's id, as croit lists it (C(id) in RV(template)).
    type: str
    required: true
  content:
    description:
      - The complete custom template.
      - Compared exactly, except that trailing newlines are ignored.
      - Mutually exclusive with O(predefined); one of them is required.
    type: str
  predefined:
    description:
      - Name of one of croit's predefined templates for this file (C(availableTemplates) in RV(template)).
      - Mutually exclusive with O(content); one of them is required.
    type: str
"""

EXAMPLES = r"""
- name: Custom chrony configuration for the servers
  croit.ceph.config_template:
    name: "{{ chrony_template_id }}"
    content: "{{ lookup('ansible.builtin.file', 'chrony.conf.j2') }}"

- name: Back to croit's stock template
  croit.ceph.config_template:
    name: "{{ chrony_template_id }}"
    predefined: default
"""

RETURN = r"""
template:
  description:
    - The template as croit reports it after the change (C(ConfigTemplateResponse) in the croit API).
    - Before the change in check mode.
  returned: always
  type: dict
  sample:
    id: chrony
    description: Chrony configuration on the servers
    currentTemplateName: custom
    currentTemplate: "server ntp.example.com iburst\n"
    availableTemplates:
      - name: default
        template: "..."
task:
  description: The croit background task the change ran as.
  returned: when a task ran
  type: dict
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def same_text(a, b):
    """Templates compare exactly, apart from trailing newlines."""
    return (a or "").rstrip("\n") == (b or "").rstrip("\n")


def view(template):
    return dict(predefined=template.get("currentTemplateName"), content=template.get("currentTemplate") or "")


class ConfigTemplateModule(CroitModule):
    def __init__(self):
        super(ConfigTemplateModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                content=dict(type="str"),
                predefined=dict(type="str"),
            ),
            mutually_exclusive=[("content", "predefined")],
            required_one_of=[("content", "predefined")],
        )

    def find(self):
        templates = self.get_list("/config-templates")
        for template in templates:
            if template.get("id") == self.params["name"]:
                return template
        self.module.fail_json(
            msg="croit has no config template %r. Known templates: %s"
            % (self.params["name"], ", ".join(sorted(t.get("id", "") for t in templates)))
        )

    def run(self):
        p = self.params
        current = self.find()
        before = view(current)
        offered = dict((t.get("name"), t.get("template")) for t in current.get("availableTemplates") or [])

        if p["predefined"] is not None:
            if p["predefined"] not in offered:
                self.module.fail_json(
                    msg="Template %r offers no predefined template %r. Offered: %s"
                    % (p["name"], p["predefined"], ", ".join(sorted(offered)))
                )
            changed = current.get("currentTemplateName") != p["predefined"]
            after = dict(predefined=p["predefined"], content=offered[p["predefined"]] or "")
            body = dict(predefinedTemplate=p["predefined"])
        else:
            changed = not same_text(current.get("currentTemplate"), p["content"])
            after = dict(predefined=before["predefined"] if not changed else None, content=p["content"])
            body = dict(customTemplate=p["content"])

        result = dict(template=current)
        if not changed:
            self.exit(changed=False, before=before, after=before, **result)
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, **result)

        task = self.handle_task(self.write("PUT", path_join("config-templates", "templates", p["name"]), body=body))
        if task is not None:
            result["task"] = task
        result["template"] = self.find()
        self.exit(changed=True, before=before, after=after, **result)


def main():
    ConfigTemplateModule().run()


if __name__ == "__main__":
    main()
