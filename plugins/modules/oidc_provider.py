#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /auth/oidc
# croit-api: POST /auth/oidc
# croit-api: PUT /auth/oidc/{providerId}
# croit-api: DELETE /auth/oidc/{providerId}

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: oidc_provider
short_description: Manage OpenID Connect login providers of croit
version_added: 0.1.0
description:
  - Creates, updates and deletes the OpenID Connect (single sign-on) providers croit offers on its login page.
    A provider is identified by O(name), which must be unique among croit's providers.
  - Only the options that are set are managed; the others keep their current value. croit replaces a
    provider's whole configuration on every update, so the module sends the current values for everything
    that is not set, and only when something differs.
  - B(Any change, and deleting the provider, logs out everyone who signed in through it.)
  - croit returns the stored client secret, so O(client_secret) is compared like any other option. It is
    never shown in a diff or returned.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
    details:
      - The client secret shows as C(********), or C(******** (changed)) when it will change.
options:
  name:
    description:
      - Human-readable name of the provider, shown on the login page. It identifies the provider.
      - When several providers share the name, the module fails and asks you to rename or remove them.
    type: str
    required: true
  state:
    description:
      - V(present) creates the provider or updates it.
      - V(absent) deletes it, which logs out its users. A provider that does not exist is left alone.
    type: str
    choices: [present, absent]
    default: present
  discovery_url:
    description:
      - Discovery URL of the provider, ending in C(/.well-known/openid-configuration).
      - Required when the provider is created. croit fetches it before storing the provider, so it must be
        reachable from the croit management node.
    type: str
  client_id:
    description:
      - Client ID croit uses with the provider. Required when the provider is created.
    type: str
  client_secret:
    description:
      - Client secret croit uses with the provider.
      - Compared with the secret croit stores; set to an empty string to remove it.
    type: str
  client_auth:
    description:
      - How croit authenticates to the provider. V(none) sends no secret, V(basic) uses HTTP Basic
        authentication, V(post) sends the secret in the form body.
    type: str
    choices: [none, basic, post]
  scope:
    description:
      - Scopes requested from the provider, separated by spaces. croit uses C(openid profile) when none is set.
    type: str
  manual_roles:
    description:
      - V(true) assigns roles to each user in croit by hand.
      - V(false) derives them from the groups found through O(group_pointer) and O(role_mapping).
    type: bool
  group_pointer:
    description:
      - Claim name or JSON pointer to the list of groups in the provider's claims, for example V(groups).
    type: str
  role_mapping:
    description:
      - Map of group names in the claims to the croit role they grant, one of V(admin), V(viewer) or
        V(securefolder).
      - The complete mapping; groups that are not listed are removed. Invalid roles fail before anything is
        written.
    type: dict
  default_roles:
    description:
      - Roles every user from this provider gets. The complete set; order and duplicates do not matter.
    type: list
    elements: str
    choices: [admin, viewer, securefolder]
  issuer_url:
    description:
      - Override of the issuer URL found through discovery. An empty string removes the override.
    type: str
  authorize_url:
    description:
      - Override of the authorize endpoint found through discovery. An empty string removes the override.
    type: str
  token_url:
    description:
      - Override of the token endpoint found through discovery. An empty string removes the override.
    type: str
  userinfo_url:
    description:
      - Override of the userinfo endpoint found through discovery. An empty string removes the override.
    type: str
  jwks_url:
    description:
      - Override of the JWKS endpoint found through discovery. An empty string removes the override.
    type: str
  callback_base_uri:
    description:
      - Override of the callback base URI croit gives the provider. An empty string removes the override.
    type: str
notes:
  - Every change to a provider, and deleting it, ends the sessions of users who signed in through it.
seealso:
  - module: croit.ceph.user
    description: Manage local croit users that log in with a password.
  - module: croit.ceph.api_token
    description: Manage API tokens for automation.
  - name: croit API reference
    description: The C(/auth/oidc) endpoints this module uses.
    link: https://www.croit.io/api-docs
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Keycloak login with roles from groups
  croit.ceph.oidc_provider:
    name: Keycloak
    discovery_url: https://sso.example.com/realms/ops/.well-known/openid-configuration
    client_id: croit
    client_secret: "{{ vault_croit_oidc_secret }}"
    client_auth: basic
    manual_roles: false
    group_pointer: groups
    role_mapping:
      storage-admins: admin
      storage-viewers: viewer
    default_roles: [viewer]
  register: keycloak

- name: Show croit's id of the provider
  ansible.builtin.debug:
    msg: "Keycloak provider id {{ keycloak.oidc_provider.id }}"

- name: Request an extra scope (logs Keycloak users out)
  croit.ceph.oidc_provider:
    name: Keycloak
    scope: openid profile email

- name: Remove a provider (logs its users out)
  croit.ceph.oidc_provider:
    name: Old SSO
    state: absent
"""

RETURN = r"""
oidc_provider:
  description:
    - The provider as croit reports it after the change (C(OidcConfigResponse) in the croit API), with
      C(clientSecret) masked.
    - In check mode, the provider before the change. Empty when the provider does not exist.
  returned: always
  type: dict
  contains:
    id:
      description: croit's id of the provider.
      returned: when the provider exists
      type: int
      sample: 2
    name:
      description: Name of the provider.
      returned: when the provider exists
      type: str
      sample: Keycloak
    discoveryUrl:
      description: Discovery URL of the provider.
      returned: when the provider exists
      type: str
      sample: https://sso.example.com/realms/ops/.well-known/openid-configuration
    clientId:
      description: Client ID croit uses.
      returned: when the provider exists
      type: str
      sample: croit
    clientSecret:
      description: Always masked as C(********) when a secret is stored; null otherwise.
      returned: when the provider exists
      type: str
      sample: "********"
    clientAuth:
      description: Client authentication method, one of C(None), C(Basic) or C(Post).
      returned: when the provider exists
      type: str
      sample: Basic
    scope:
      description: Scopes requested from the provider.
      returned: when the provider exists
      type: str
      sample: openid profile
    manualRoles:
      description: Whether roles are assigned by hand rather than from groups.
      returned: when the provider exists
      type: bool
      sample: false
    groupPointer:
      description: Claim or JSON pointer to the groups list.
      returned: when the provider exists
      type: str
      sample: groups
    roleMapping:
      description: Group names in the claims mapped to croit roles.
      returned: when the provider exists
      type: dict
      sample:
        storage-admins: admin
    defaultRoles:
      description: Roles every user from the provider gets.
      returned: when the provider exists
      type: list
      elements: str
      sample: [viewer]
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

MASK = "********"
CLIENT_AUTH = dict(none="None", basic="Basic", post="Post")

# Ansible option -> croit field, for plain string/bool fields.
FIELDS = dict(
    discovery_url="discoveryUrl",
    client_id="clientId",
    client_secret="clientSecret",
    scope="scope",
    manual_roles="manualRoles",
    group_pointer="groupPointer",
    issuer_url="issuerUrl",
    authorize_url="authorizeUrl",
    token_url="tokenUrl",
    userinfo_url="userinfoUrl",
    jwks_url="jwksUrl",
    callback_base_uri="callbackBaseUri",
)
# Fields where an empty string means "not set" (croit answers null).
NULLABLE = ("clientSecret", "issuerUrl", "authorizeUrl", "tokenUrl", "userinfoUrl", "jwksUrl", "callbackBaseUri")
# Everything the create / replace request carries.
REQUEST_FIELDS = list(FIELDS.values()) + ["name", "clientAuth", "defaultRoles", "roleMapping"]


def normalise(provider):
    """croit's provider in comparable form."""
    view = dict((k, provider.get(k)) for k in REQUEST_FIELDS)
    for key in NULLABLE:
        if not view.get(key):
            view[key] = None
    view["defaultRoles"] = sorted(view.get("defaultRoles") or [])
    view["roleMapping"] = dict(view.get("roleMapping") or {})
    return view


def masked(view):
    if not view:
        return {}
    shown = dict(view)
    if shown.get("clientSecret"):
        shown["clientSecret"] = MASK
    return shown


class OidcProviderModule(CroitModule):
    def __init__(self):
        spec = dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["present", "absent"]),
            client_auth=dict(type="str", choices=list(CLIENT_AUTH)),
            role_mapping=dict(type="dict"),
            default_roles=dict(type="list", elements="str", choices=["admin", "viewer", "securefolder"]),
        )
        for opt in FIELDS:
            spec[opt] = dict(type="bool") if opt == "manual_roles" else dict(type="str")
        spec["client_secret"]["no_log"] = True
        spec["token_url"]["no_log"] = False
        super(OidcProviderModule, self).__init__(spec, warnings=False)

    def find_provider(self, name):
        matches = [p for p in self.get_list("/auth/oidc") if p.get("name") == name]
        if len(matches) > 1:
            self.module.fail_json(msg="%d OIDC providers are named %r; rename or remove the duplicates" % (len(matches), name))
        return matches[0] if matches else None

    def desired(self):
        p = self.params
        want = dict((api, p[opt]) for opt, api in FIELDS.items() if p[opt] is not None)
        for key in NULLABLE:
            if key in want and want[key] == "":
                want[key] = None
        if p["client_auth"] is not None:
            want["clientAuth"] = CLIENT_AUTH[p["client_auth"]]
        if p["default_roles"] is not None:
            want["defaultRoles"] = sorted(set(p["default_roles"]))
        if p["role_mapping"] is not None:
            roles = ("admin", "viewer", "securefolder")
            bad = sorted(k for k, v in p["role_mapping"].items() if v not in roles)
            if bad:
                self.module.fail_json(msg="role_mapping values must be one of %s; invalid for: %s" % (", ".join(roles), ", ".join(bad)))
            want["roleMapping"] = dict(p["role_mapping"])
        return want

    def run(self):
        p = self.params
        provider = self.find_provider(p["name"])
        if p["state"] == "absent":
            if provider is None:
                self.exit(changed=False, before={}, after={}, oidc_provider={})
            result = dict(changed=True, before=masked(normalise(provider)), after={}, oidc_provider={})
            if not self.check_mode:
                task = self.handle_task(self.write("DELETE", path_join("auth", "oidc", provider["id"])))
                if task is not None:
                    result["task"] = task
            self.exit(**result)

        want = self.desired()
        if provider is None:
            missing = [opt for opt in ("discovery_url", "client_id") if not p[opt]]
            if missing:
                self.module.fail_json(msg="%s required to create OIDC provider %r" % (" and ".join(missing), p["name"]))
            body = dict(want, name=p["name"])
            after = masked(body)
            if self.check_mode:
                self.exit(changed=True, before={}, after=after, oidc_provider={})
            result = dict(changed=True, before={}, after=after)
            task = self.handle_task(self.write("POST", "/auth/oidc", body=body))
            if task is not None:
                result["task"] = task
            result["oidc_provider"] = masked(self.find_provider(p["name"]))
            self.exit(**result)

        current = normalise(provider)
        merged = dict(current)
        merged.update(want)
        before, after = masked(current), masked(merged)
        if merged.get("clientSecret") != current.get("clientSecret"):
            after["clientSecret"] = MASK + " (changed)" if merged.get("clientSecret") else None
        if merged == current:
            self.exit(changed=False, before=before, after=after, oidc_provider=masked(provider))
        if self.check_mode:
            self.exit(changed=True, before=before, after=after, oidc_provider=masked(provider))
        result = dict(changed=True, before=before, after=after)
        task = self.handle_task(self.write("PUT", path_join("auth", "oidc", provider["id"]), body=merged))
        if task is not None:
            result["task"] = task
        result["oidc_provider"] = masked(self.find_provider(p["name"]))
        self.exit(**result)


def main():
    OidcProviderModule().run()


if __name__ == "__main__":
    main()
