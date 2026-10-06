#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /api-tokens
# croit-api: POST /api-tokens
# croit-api: PATCH /api-tokens/{apiTokenId}
# croit-api: DELETE /api-tokens/{apiTokenId}
# croit-api: GET /auth/token-info

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: api_token
short_description: Manage croit API tokens
version_added: 0.1.0
description:
  - Creates, updates and deletes croit API tokens. A token is identified by O(name), which must be unique among
    the cluster's API tokens.
  - B(The secret is shown exactly once.) croit stores only a hash of it, so the module returns it in RV(token)
    only on the run that creates the token. It cannot be read back later; a lost token has to be deleted and
    created again. Set C(no_log) on the task and store RV(token) somewhere safe straight away.
  - Only the roles of an existing token can be changed, and only when they differ from the requested set.
    O(expiry) is used when the token is created. Options left unset are left alone.
  - The token the module itself authenticates with is never deleted or stripped of the admin role, so a
    playbook cannot lock itself out.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
attributes:
  check_mode:
    support: full
    details:
      - In check mode no token is created, so RV(token) is never returned.
  diff_mode:
    support: full
    details:
      - The diff shows the name, roles and expiry; never the secret.
options:
  name:
    description:
      - Name of the token, which identifies it.
      - When several tokens share the name, the module fails and asks you to remove the duplicates in croit.
    type: str
    required: true
  state:
    description:
      - V(present) creates the token or updates its roles.
      - V(absent) deletes the token, which revokes it immediately. A token that does not exist is left alone.
    type: str
    choices: [present, absent]
    default: present
  roles:
    description:
      - The complete set of roles of the token. Order and duplicates do not matter.
      - Required when the token is created. When not set, an existing token's roles are left alone.
      - Must not be empty, and V(admin) needs V(viewer) as well, as croit requires. Both are checked before
        anything is written, in check mode too.
    type: list
    elements: str
    choices: [admin, viewer, securefolder]
  expiry:
    description:
      - When the token stops being accepted, as an ISO 8601 date-time such as V(2027-01-01T00:00:00Z).
      - Only used when the token is created; croit cannot change the expiry of an existing token. When it is an
        ISO date-time that differs from the existing token's expiry, the module fails rather than recreating
        the token.
      - When not set, a new token never expires.
    type: str
notes:
  - The returned RV(token) is not masked by Ansible, so that you can use it. Always set C(no_log) on the task
    that creates a token, and on any task that uses the registered result.
  - The lockout guard compares the token with the identity croit reports for the API token in use
    (C(/auth/token-info)).
seealso:
  - module: croit.ceph.user
    description: Manage local croit users that log in with a password.
  - name: croit API reference
    description: The C(/api-tokens) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Token for the monitoring system
  croit.ceph.api_token:
    name: prometheus
    roles: [viewer]
  register: prometheus_token
  no_log: true

- name: Store the secret the moment it is created
  ansible.builtin.copy:
    content: "{{ prometheus_token.token }}"
    dest: /etc/prometheus/croit-token
    mode: "0600"
  when: prometheus_token.token is defined
  no_log: true

- name: Time-limited admin token for a CI pipeline
  croit.ceph.api_token:
    name: ci-2026
    roles: [admin, viewer]
    expiry: "2027-01-01T00:00:00Z"
  register: ci_token
  no_log: true

- name: Downgrade an existing token to read-only
  croit.ceph.api_token:
    name: ci-2026
    roles: [viewer]

- name: Revoke a token
  croit.ceph.api_token:
    name: old-ci
    state: absent
"""

RETURN = r"""
api_token:
  description:
    - The token's name, roles and expiry as croit reports them after the change (C(ApiTokenInfo) in the croit
      API). It never contains the secret.
    - In check mode, the token before the change. Empty when the token does not exist.
  returned: always
  type: dict
  contains:
    id:
      description: croit's id of the token.
      returned: when the token exists
      type: int
      sample: 12
    name:
      description: Name of the token.
      returned: when the token exists
      type: str
      sample: prometheus
    roles:
      description: Roles the token holds.
      returned: when the token exists
      type: list
      elements: str
      sample: [viewer]
    expiresBy:
      description: When the token expires, or null when it never does.
      returned: when the token exists
      type: str
      sample: "2027-01-01T00:00:00Z"
token:
  description:
    - The secret token. Only returned by the run that created the token, never in check mode, and never
      masked; set C(no_log) on the task.
    - It cannot be retrieved again.
  returned: when the token was created
  type: str
  sample: "********"
"""

import datetime

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule


def parse_iso(value):
    """A comparable UTC datetime for an ISO 8601 string, or None when it is not one."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def managed_view(token):
    if not token:
        return {}
    return dict(name=token["name"], roles=sorted(token.get("roles") or []), expiry=token.get("expiresBy"))


class ApiTokenModule(CroitModule):
    def __init__(self):
        super(ApiTokenModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                roles=dict(type="list", elements="str", choices=["admin", "viewer", "securefolder"]),
                expiry=dict(type="str"),
            ),
            wait=False,
            warnings=False,
        )

    def find_token(self, name):
        matches = [t for t in self.get_list("/api-tokens") if t.get("name") == name]
        if len(matches) > 1:
            self.module.fail_json(
                msg="%d API tokens are named %r; delete the duplicates in croit before managing it here"
                % (len(matches), name)
            )
        return matches[0] if matches else None

    def is_token_in_use(self, token):
        info = self.get("/auth/token-info") or {}
        return info.get("username") == token["name"]

    def validate_roles(self, roles):
        if roles is None:
            return None
        roles = sorted(set(roles))
        if not roles:
            self.module.fail_json(msg="roles must not be empty; croit refuses a token without roles")
        if "admin" in roles and "viewer" not in roles:
            self.module.fail_json(msg="The admin role needs the viewer role as well; add viewer to roles")
        return roles

    def run(self):
        p = self.params
        token = self.find_token(p["name"])
        if p["state"] == "absent":
            self.absent(token)
        roles = self.validate_roles(p["roles"])
        if token is None:
            self.create(roles)
        self.update(token, roles)

    def absent(self, token):
        if token is None:
            self.exit(changed=False, before={}, after={}, api_token={})
        if self.is_token_in_use(token):
            self.module.fail_json(msg="Refusing to delete API token %r: this module is authenticating with it" % token["name"])
        if not self.check_mode:
            self.write("DELETE", path_join("api-tokens", token["id"]))
        self.exit(changed=True, before=managed_view(token), after={}, api_token={})

    def create(self, roles):
        p = self.params
        if roles is None:
            self.module.fail_json(msg="roles is required to create API token %r" % p["name"])
        body = dict(name=p["name"], roles=roles)
        if p["expiry"]:
            body["expiry"] = p["expiry"]
        after = dict(name=p["name"], roles=roles, expiry=p["expiry"])
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, api_token={})
        # The answer is the secret. It is returned as-is (adding it to no_log_values would
        # mask it in the result too); the docs tell users to set no_log on the task.
        secret = self.write("POST", "/api-tokens", body=body)
        result = dict(changed=True, before={}, after=after, api_token=self.find_token(p["name"]) or {})
        if secret:
            result["token"] = secret
        self.exit(**result)

    def update(self, token, roles):
        p = self.params
        before = managed_view(token)
        after = dict(before)
        if p["expiry"]:
            wanted, current = parse_iso(p["expiry"]), parse_iso(token.get("expiresBy"))
            if wanted is not None and wanted != current:
                self.module.fail_json(
                    msg="API token %r expires %s and croit cannot change the expiry of an existing token; "
                    "delete it and create it again to get %s" % (p["name"], token.get("expiresBy") or "never", p["expiry"])
                )
        changed = roles is not None and roles != before["roles"]
        if changed:
            after["roles"] = roles
            if "admin" in before["roles"] and "admin" not in roles and self.is_token_in_use(token):
                self.module.fail_json(
                    msg="Refusing to take the admin role from API token %r: this module is authenticating with it"
                    % token["name"]
                )
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, api_token=token)
        self.write("PATCH", path_join("api-tokens", token["id"]), body=dict(roles=roles))
        self.exit(changed=True, before=before, after=after, api_token=self.find_token(p["name"]) or {})


def main():
    ApiTokenModule().run()


if __name__ == "__main__":
    main()
