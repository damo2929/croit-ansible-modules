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
    node) either to custom content or to one of croit's predefined templates for that file.
  - A template is identified by its id, O(name). croit offers a fixed set of templates; they cannot be created
    or deleted. To go back to croit's stock template, set O(predefined) to one of the names croit offers.
  - The module compares the requested template with what croit reports and only writes when they differ.
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
    details:
      - The diff shows the predefined template name and the full template content.
options:
  name:
    description:
      - The template's id, as croit lists it (C(id) in RV(template)).
      - An unknown id fails the task and lists the template ids croit offers.
    type: str
    required: true
  content:
    description:
      - The complete custom template text.
      - Compared exactly, except that trailing newlines are ignored.
      - Mutually exclusive with O(predefined); exactly one of them is required.
    type: str
  predefined:
    description:
      - Name of one of croit's predefined templates for this file, as listed in C(availableTemplates) in
        RV(template).
      - A name the template does not offer fails the task and lists the names it does offer.
      - Mutually exclusive with O(content); exactly one of them is required.
    type: str
notes:
  - A template change only reaches a server when croit next renders the file there, which for boot-time
    files such as network and GRUB templates is the server's next boot.
seealso:
  - module: croit.ceph.hook_script
    description: Run scripts on the servers at boot and other events, instead of templating files.
  - module: croit.ceph.ceph_config
    description: Manage Ceph options in the monitor configuration database.
  - name: croit API reference
    description: The C(/config-templates) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Custom chrony configuration for the servers
  croit.ceph.config_template:
    name: "{{ chrony_template_id }}"
    content: "{{ lookup('ansible.builtin.file', 'chrony.conf') }}"
  register: chrony

- name: Show which stock templates croit offers for this file
  ansible.builtin.debug:
    msg: "{{ chrony.template.availableTemplates | map(attribute='name') | list }}"

- name: Back to croit's first stock template
  croit.ceph.config_template:
    name: "{{ chrony_template_id }}"
    predefined: "{{ chrony.template.availableTemplates[0].name }}"
"""

RETURN = r"""
template:
  description:
    - The template as croit reports it after the change (C(ConfigTemplateResponse) in the croit API).
    - In check mode, the template before the change.
  returned: always
  type: dict
  contains:
    id:
      description: The template's id, which O(name) refers to.
      returned: always
      type: str
      sample: chrony
    description:
      description: What file the template renders.
      returned: always
      type: str
      sample: Chrony configuration on the servers
    currentTemplateName:
      description: Name of the predefined template in use, or a name that matches none of them for custom content.
      returned: always
      type: str
      sample: custom
    currentTemplate:
      description: The template text in use.
      returned: always
      type: str
      sample: "server ntp.example.com iburst\n"
    availableTemplates:
      description: The predefined templates croit offers for this file, each with C(name) and C(template) text.
      returned: always
      type: list
      elements: dict
      sample:
        - name: chrony-default
          template: "pool pool.ntp.org iburst\n"
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
