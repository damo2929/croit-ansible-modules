#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /users
# croit-api: POST /users
# croit-api: PATCH /users/{userId}
# croit-api: DELETE /users/{userId}
# croit-api: PUT /users/{userId}/password
# croit-api: GET /auth/token-info

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: user
short_description: Manage local croit users
version_added: 0.1.0
description:
  - Creates, updates and deletes local croit accounts, the ones that log in with a password. A user is
    identified by O(username).
  - Roles are compared as a set and only written when they differ. Options left unset, such as O(roles) on an
    existing user, are left alone.
  - LDAP and OIDC users are managed by their directory or identity provider; this module refuses to touch them.
  - The account the API token in use belongs to is never deleted or stripped of the admin role, so a playbook
    cannot lock its own operator out.
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
      - The password never appears in a diff; a password that will be set shows as C(********).
options:
  username:
    description:
      - Login name of the user, which identifies the account.
    type: str
    required: true
    aliases: [name]
  state:
    description:
      - V(present) creates the user or updates its roles and password.
      - V(absent) deletes the user. A user that does not exist is left alone.
    type: str
    choices: [present, absent]
    default: present
  roles:
    description:
      - The complete set of roles of the user. Order and duplicates do not matter.
      - Required when the user is created. When not set, an existing user's roles are left alone.
      - Must not be empty, and V(admin) needs V(viewer) as well, as croit requires. Both are checked before
        anything is written, in check mode too.
    type: list
    elements: str
    choices: [admin, viewer, securefolder]
  password:
    description:
      - Password of the user. croit stores only a hash, so it cannot be compared; O(update_password) decides when
        it is sent.
      - A user created without a password cannot log in until one is set; the module warns about this.
      - Setting a password ends every session the user holds.
    type: str
  update_password:
    description:
      - V(on_create) sets O(password) only when the user is created.
      - V(always) sets it on every run, which always reports a change.
    type: str
    choices: [always, on_create]
    default: on_create
notes:
  - croit itself refuses to delete the last local admin account or to take the admin role away from it.
  - The lockout guard compares the user with the identity croit reports for the API token in use
    (C(/auth/token-info)).
seealso:
  - module: croit.ceph.api_token
    description: Manage the API tokens automation should use instead of user passwords.
  - module: croit.ceph.oidc_provider
    description: Let users log in through an OpenID Connect identity provider.
  - name: croit API reference
    description: The C(/users) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Read-only operator for monitoring
  croit.ceph.user:
    username: monitoring
    roles: [viewer]
    password: "{{ vault_monitoring_password }}"
  register: monitoring_user

- name: Show the account id croit assigned
  ansible.builtin.debug:
    msg: "monitoring has id {{ monitoring_user.user.id }}"

- name: Make alice an administrator
  croit.ceph.user:
    username: alice
    roles: [admin, viewer]

- name: Rotate a password
  croit.ceph.user:
    username: alice
    password: "{{ vault_alice_password }}"
    update_password: always

- name: Remove a user
  croit.ceph.user:
    username: bob
    state: absent
"""

RETURN = r"""
user:
  description:
    - The user as croit reports it after the change (C(Account) in the croit API). It never contains the
      password.
    - In check mode, the user before the change. Empty when the user does not exist.
  returned: always
  type: dict
  contains:
    id:
      description: croit's id of the account.
      returned: when the user exists
      type: int
      sample: 4
    username:
      description: Login name.
      returned: when the user exists
      type: str
      sample: monitoring
    roles:
      description: Every role the account holds.
      returned: when the user exists
      type: list
      elements: str
      sample: [viewer]
    authScheme:
      description: How the account authenticates; C(password) for the accounts this module manages.
      returned: when the user exists
      type: str
      sample: password
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

MASK = "********"


def managed_view(user):
    if not user:
        return {}
    return dict(username=user["username"], roles=sorted(user.get("roles") or []))


class UserModule(CroitModule):
    def __init__(self):
        super(UserModule, self).__init__(
            dict(
                username=dict(type="str", required=True, aliases=["name"]),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                roles=dict(type="list", elements="str", choices=["admin", "viewer", "securefolder"]),
                password=dict(type="str", no_log=True),
                update_password=dict(type="str", default="on_create", choices=["always", "on_create"], no_log=False),
            ),
            wait=False,
            warnings=False,
        )

    def find_user(self, username):
        for account in self.get_list("/users"):
            if account.get("username") == username:
                return account
        return None

    def current_identity(self):
        """Username the API token in use authenticates as."""
        info = self.get("/auth/token-info") or {}
        return info.get("username")

    def validate_roles(self, roles):
        if roles is None:
            return None
        roles = sorted(set(roles))
        if not roles:
            self.module.fail_json(msg="roles must not be empty; croit refuses an account without roles")
        if "admin" in roles and "viewer" not in roles:
            self.module.fail_json(msg="The admin role needs the viewer role as well; add viewer to roles")
        return roles

    def run(self):
        p = self.params
        user = self.find_user(p["username"])
        if user is not None and user.get("authScheme") != "password":
            self.module.fail_json(
                msg="User %r is a %s account; only local (password) accounts can be managed with this module"
                % (p["username"], user.get("authScheme"))
            )
        if p["state"] == "absent":
            self.absent(user)
        roles = self.validate_roles(p["roles"])
        if user is None:
            self.create(roles)
        self.update(user, roles)

    def absent(self, user):
        if user is None:
            self.exit(changed=False, before={}, after={}, user={})
        if self.current_identity() == user["username"]:
            self.module.fail_json(msg="Refusing to delete user %r: the API token in use belongs to it" % user["username"])
        if not self.check_mode:
            self.write("DELETE", path_join("users", user["id"]))
        self.exit(changed=True, before=managed_view(user), after={}, user={})

    def create(self, roles):
        p = self.params
        if roles is None:
            self.module.fail_json(msg="roles is required to create user %r" % p["username"])
        after = dict(username=p["username"], roles=roles)
        if p["password"] is not None:
            after["password"] = MASK
        else:
            self.module.warn("User %r is created without a password and cannot log in until one is set" % p["username"])
        if self.check_mode:
            self.exit(changed=True, before={}, after=after, user={})
        created = self.write("POST", "/users", body=dict(username=p["username"], roles=roles))
        user_id = (created or {}).get("id")
        if user_id is None:
            user_id = (self.find_user(p["username"]) or {}).get("id")
        if p["password"] is not None:
            self.write("PUT", path_join("users", user_id, "password"), body=dict(password=p["password"]))
        self.exit(changed=True, before={}, after=after, user=self.find_user(p["username"]) or {})

    def update(self, user, roles):
        p = self.params
        before = managed_view(user)
        after = dict(before)
        role_change = roles is not None and roles != before["roles"]
        if role_change:
            after["roles"] = roles
            if "admin" in before["roles"] and "admin" not in roles and self.current_identity() == user["username"]:
                self.module.fail_json(
                    msg="Refusing to take the admin role from user %r: the API token in use belongs to it"
                    % user["username"]
                )
        set_password = p["password"] is not None and p["update_password"] == "always"
        if set_password:
            after["password"] = MASK
        changed = role_change or set_password
        if not changed or self.check_mode:
            self.exit(changed=changed, before=before, after=after, user=user)
        if role_change:
            self.write("PATCH", path_join("users", user["id"]), body=dict(roles=roles))
        if set_password:
            self.write("PUT", path_join("users", user["id"], "password"), body=dict(password=p["password"]))
        self.exit(changed=True, before=before, after=after, user=self.find_user(p["username"]) or {})


def main():
    UserModule().run()


if __name__ == "__main__":
    main()
