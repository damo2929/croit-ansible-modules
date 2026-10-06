#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /crush/rules
# croit-api: POST /crush/rules/simple
# croit-api: POST /crush/rules/ssd-primary
# croit-api: DELETE /crush/rules/{name}
# croit-api: GET /pools

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: crush_rule
short_description: Manage CRUSH rules on a croit cluster
version_added: 0.1.0
description:
  - Create and delete CRUSH rules through the croit API. A rule is identified by its O(name).
  - Two kinds of rule can be created. V(simple) takes one bucket and spreads copies over a failure domain.
    V(ssd_primary) places the first copies on one device class and the rest on another.
  - CRUSH rules cannot be changed in place. When an existing rule differs from the options that are set,
    the task fails instead of deleting and recreating the rule, because pools may be placed with it.
  - Only the options that are set are compared with an existing rule, so a task with only O(name)
    just makes sure the rule exists. O(type) is inferred from the options, so any C(ssd_*) or C(hdd_*)
    option means V(ssd_primary). Mixing options of both kinds fails the task.
  - Editing the CRUSH map itself (moving buckets, change requests) is out of scope.
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
  name:
    description:
      - Name of the CRUSH rule, for example V(replicated_ssd). Pools refer to the rule by name or id
        (see M(croit.ceph.pool)).
    type: str
    required: true
  state:
    description:
      - Whether the rule should exist.
      - V(absent) refuses to delete a rule that a pool is still placed with, and names the pools.
    type: str
    choices: [present, absent]
    default: present
  type:
    description:
      - Kind of rule. When not set, it is inferred from the other options; V(simple) is used when
        creating a rule without any C(ssd_*) or C(hdd_*) option.
      - Compared with an existing rule only when set.
    type: str
    choices: [simple, ssd_primary]
  start_bucket:
    description:
      - For O(type=simple), the bucket placement starts from. V(default) is used when creating.
    type: str
  failure_domain:
    description:
      - For O(type=simple), the bucket type copies are spread over, for example V(host) or V(rack).
        V(host) is used when creating.
    type: str
  device_class:
    description:
      - For O(type=simple), the device class to place on, for example V(ssd).
      - croit warns when a rule targets no device class, see O(ignore_warnings).
    type: str
  erasure_coding:
    description:
      - For O(type=simple), create a rule for erasure coded pools instead of replicated ones.
        A replicated rule is created when not set.
    type: bool
  ssd_start_bucket:
    description:
      - For O(type=ssd_primary), the bucket the primary copies start from. V(default) is used when creating.
    type: str
  ssd_failure_domain:
    description:
      - For O(type=ssd_primary), the failure domain the primary copies spread over. V(host) is used when creating.
    type: str
  ssd_device_class:
    description:
      - For O(type=ssd_primary), the device class of the primary copies, for example V(ssd).
    type: str
  ssd_copies:
    description:
      - For O(type=ssd_primary), how many copies go on the fast device class. The rest go on
        O(hdd_device_class).
    type: int
  hdd_start_bucket:
    description:
      - For O(type=ssd_primary), the bucket the other copies start from. V(default) is used when creating.
    type: str
  hdd_failure_domain:
    description:
      - For O(type=ssd_primary), the failure domain the other copies spread over. V(host) is used when creating.
    type: str
  hdd_device_class:
    description:
      - For O(type=ssd_primary), the device class of the other copies, for example V(hdd).
    type: str
notes:
  - Rules created outside this module, with any other layout, are reported with C(type=custom) in
    RV(layout). Their existence can be checked, but setting any placement option for them fails.
  - It is assumed that croit reports a class-pinned C(take) step as a bucket plus a device class, and
    that a simple rule has exactly one C(take) ... C(emit) group. This has not been verified against a
    live croit cluster.
seealso:
  - module: croit.ceph.crush_info
    description: Read CRUSH rules, device classes, erasure code profiles and the CRUSH tree.
  - module: croit.ceph.pool
    description: Place pools with a CRUSH rule.
  - name: croit API reference
    description: The croit REST API, including the C(/crush/rules) endpoints.
    link: https://www.croit.io/api-docs
  - name: CRUSH maps
    description: Upstream documentation of CRUSH maps and rules.
    link: https://docs.ceph.com/en/latest/rados/operations/crush-map/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Replicated rule on SSDs, one copy per host
  croit.ceph.crush_rule:
    name: replicated_ssd
    failure_domain: host
    device_class: ssd
  register: ssd_rule

- name: Place a pool with it, by the id croit assigned
  croit.ceph.pool:
    name: rbd-ssd
    crush_rule: "{{ ssd_rule.rule.id }}"

- name: Rule for erasure coded pools on HDDs, spread over racks
  croit.ceph.crush_rule:
    name: ec_hdd_rack
    erasure_coding: true
    failure_domain: rack
    device_class: hdd

- name: Primary copy on SSD, replicas on HDD
  croit.ceph.crush_rule:
    name: ssd_primary
    type: ssd_primary
    ssd_device_class: ssd
    ssd_copies: 1
    hdd_device_class: hdd

- name: Remove a rule no pool uses any more
  croit.ceph.crush_rule:
    name: old_rule
    state: absent
"""

RETURN = r"""
rule:
  description:
    - The rule as croit reports it after the change (C(CrushRuleResponse) in the croit API).
    - Empty when the rule does not exist, or before it is created in check mode.
  returned: always
  type: dict
  contains:
    id:
      description: The rule's id, which pools refer to.
      returned: when the rule exists
      type: int
      sample: 2
    name:
      description: The rule's name.
      returned: when the rule exists
      type: str
      sample: replicated_ssd
    type:
      description: Whether the rule places replicas (C(REPLICATED)) or erasure coded chunks (C(ERASURE)).
      returned: when the rule exists
      type: str
      sample: REPLICATED
    steps:
      description: The rule's steps in order, each with C(op) and, depending on it, C(bucket), C(deviceClass), C(bucketType) and C(num).
      returned: when the rule exists
      type: list
      elements: dict
      sample:
        - {op: TAKE, bucket: default, deviceClass: ssd}
        - {op: CHOOSELEAF, bucketType: host, num: 0}
        - {op: EMIT}
layout:
  description:
    - The rule's placement expressed as this module's options, derived from its steps. C(type) is
      V(custom) for layouts this module cannot create.
  returned: when the rule exists and the task did not run in check mode
  type: dict
  sample:
    type: simple
    start_bucket: default
    failure_domain: host
    device_class: ssd
    erasure_coding: false
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.crush import layout
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

SIMPLE_OPTIONS = ("start_bucket", "failure_domain", "device_class", "erasure_coding")
SSD_OPTIONS = (
    "ssd_start_bucket",
    "ssd_failure_domain",
    "ssd_device_class",
    "ssd_copies",
    "hdd_start_bucket",
    "hdd_failure_domain",
    "hdd_device_class",
)
DEFAULT_BUCKET = "default"
DEFAULT_DOMAIN = "host"


class CrushRuleModule(CroitModule):
    def __init__(self):
        spec = dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["present", "absent"]),
            type=dict(type="str", choices=["simple", "ssd_primary"]),
            start_bucket=dict(type="str"),
            failure_domain=dict(type="str"),
            device_class=dict(type="str"),
            erasure_coding=dict(type="bool"),
        )
        for opt in SSD_OPTIONS:
            spec[opt] = dict(type="int" if opt == "ssd_copies" else "str")
        super(CrushRuleModule, self).__init__(spec, wait=False)

    def rule_type(self):
        p = self.params
        if p["type"]:
            return p["type"]
        if any(p[o] is not None for o in SSD_OPTIONS):
            return "ssd_primary"
        return "simple"

    def validate(self):
        kind = self.rule_type()
        other = SSD_OPTIONS if kind == "simple" else SIMPLE_OPTIONS
        bad = [o for o in other if self.params[o] is not None]
        if bad:
            self.module.fail_json(msg="%s cannot be used with type=%s" % (", ".join(bad), kind))
        return kind

    def find_rule(self):
        for rule in self.get_list("/crush/rules"):
            if rule.get("name") == self.params["name"]:
                return rule
        return None

    def desired(self, kind):
        """Options the user set, as layout keys."""
        options = SIMPLE_OPTIONS if kind == "simple" else SSD_OPTIONS
        wanted = dict((o, self.params[o]) for o in options if self.params[o] is not None)
        if self.params["type"]:
            wanted["type"] = kind
        return wanted

    def run(self):
        p = self.params
        kind = self.validate()
        current = self.find_rule()

        if p["state"] == "absent":
            return self.absent(current)
        if current is None:
            return self.create(kind)

        view = layout(current)
        wanted = self.desired(kind)
        if view.get("type") == "custom" and wanted:
            self.module.fail_json(
                msg="CRUSH rule %r has a layout this module cannot compare (it was not created as a simple or "
                "ssd_primary rule); leave its placement options unset to only check that it exists" % p["name"],
                rule=current,
            )
        if view.get("type") != kind and wanted:
            wanted["type"] = kind
        differing = sorted(k for k, v in wanted.items() if view.get(k) != v)
        if differing:
            self.module.fail_json(
                msg="CRUSH rule %r exists with a different %s; CRUSH rules cannot be changed in place. "
                "Create a rule under a new name and move the pools to it, then delete this one."
                % (p["name"], ", ".join("%s (%r, wanted %r)" % (k, view.get(k), wanted[k]) for k in differing)),
                rule=current,
                layout=view,
            )
        self.exit(changed=False, before=view, after=view, rule=current, layout=view)

    def create(self, kind):
        p = self.params
        if kind == "simple":
            path = "/crush/rules/simple"
            body = dict(
                name=p["name"],
                startBucket=p["start_bucket"] or DEFAULT_BUCKET,
                independent=p["failure_domain"] or DEFAULT_DOMAIN,
            )
            if p["device_class"] is not None:
                body["deviceClass"] = p["device_class"]
            if p["erasure_coding"] is not None:
                body["erasureCoding"] = p["erasure_coding"]
            after = dict(
                type="simple",
                start_bucket=body["startBucket"],
                failure_domain=body["independent"],
                device_class=p["device_class"],
                erasure_coding=bool(p["erasure_coding"]),
            )
        else:
            path = "/crush/rules/ssd-primary"
            body = dict(
                name=p["name"],
                ssdStartBucket=p["ssd_start_bucket"] or DEFAULT_BUCKET,
                ssdIndependent=p["ssd_failure_domain"] or DEFAULT_DOMAIN,
                hddStartBucket=p["hdd_start_bucket"] or DEFAULT_BUCKET,
                hddIndependent=p["hdd_failure_domain"] or DEFAULT_DOMAIN,
            )
            for opt, api in (("ssd_device_class", "ssdDeviceClass"), ("hdd_device_class", "hddDeviceClass"), ("ssd_copies", "ssdCopies")):
                if p[opt] is not None:
                    body[api] = p[opt]
            after = dict(
                type="ssd_primary",
                ssd_start_bucket=body["ssdStartBucket"],
                ssd_failure_domain=body["ssdIndependent"],
                ssd_device_class=p["ssd_device_class"],
                ssd_copies=p["ssd_copies"],
                hdd_start_bucket=body["hddStartBucket"],
                hdd_failure_domain=body["hddIndependent"],
                hdd_device_class=p["hdd_device_class"],
            )
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, rule={})
        self.write("POST", path, body=body)
        rule = self.find_rule() or {}
        self.exit(changed=True, before={}, after=after, rule=rule, layout=layout(rule))

    def absent(self, current):
        if current is None:
            self.exit(changed=False, rule={})
        users = [pool.get("name") for pool in self.get_list("/pools") if pool.get("crushRule") == current.get("id")]
        if users:
            self.module.fail_json(
                msg="CRUSH rule %r is still used by pool(s) %s; move them to another rule first"
                % (current["name"], ", ".join(sorted(users))),
                rule=current,
            )
        if not self.check_mode:
            self.write("DELETE", path_join("crush", "rules", current["name"]))
        self.exit(changed=True, before=layout(current), after={}, rule={})


def main():
    CrushRuleModule().run()


if __name__ == "__main__":
    main()
