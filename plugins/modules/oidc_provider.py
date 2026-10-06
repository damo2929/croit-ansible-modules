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
  - Create, update and delete the OpenID Connect (single sign-on) providers croit offers on its login page,
    identified by name.
  - Only the options that are set are managed. croit replaces a provider's whole configuration on every
    update, so the module sends the current values for everything that is not set.
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
      - The client secret shows as C(********) in diffs.
options:
  name:
    description:
      - Human-readable name of the provider, shown on the login page. Must be unique among croit's providers.
    type: str
    required: true
  state:
    description:
      - Whether the provider should exist.
    type: str
    choices: [present, absent]
    default: present
  discovery_url:
    description:
      - Discovery URL of the provider (C(.../.well-known/openid-configuration)).
      - Required when the provider is created. croit fetches it before storing the provider.
    type: str
  client_id:
    description:
      - Client ID croit uses with the provider. Required when the provider is created.
    type: str
  client_secret:
    description:
      - Client secret croit uses with the provider. Set to an empty string to remove it.
    type: str
  client_auth:
    description:
      - How croit authenticates to the provider. V(none) sends no secret, V(basic) uses HTTP Basic
        authentication, V(post) sends the secret in the form body.
    type: str
    choices: [none, basic, post]
  scope:
    description:
      - Scopes requested from the provider, separated by spaces. croit uses C(openid profile) by default.
    type: str
  manual_roles:
    description:
      - V(true) assigns roles to each user in croit by hand; V(false) derives them from O(group_pointer)
        and O(role_mapping).
    type: bool
  group_pointer:
    description:
      - Claim name or JSON pointer to the list of groups in the provider's claims.
    type: str
  role_mapping:
    description:
      - Map of group names in the claims to the croit role they grant (V(admin), V(viewer) or V(securefolder)).
      - The complete mapping; groups that are not listed are removed.
    type: dict
  default_roles:
    description:
      - Roles every user from this provider gets. The complete set; order does not matter.
    type: list
    elements: str
    choices: [admin, viewer, securefolder]
  issuer_url:
    description:
      - Override of the issuer URL. An empty string removes the override.
    type: str
  authorize_url:
    description:
      - Override of the authorize endpoint. An empty string removes the override.
    type: str
  token_url:
    description:
      - Override of the token endpoint. An empty string removes the override.
    type: str
  userinfo_url:
    description:
      - Override of the userinfo endpoint. An empty string removes the override.
    type: str
  jwks_url:
    description:
      - Override of the JWKS endpoint. An empty string removes the override.
    type: str
  callback_base_uri:
    description:
      - Override of the callback base URI croit gives the provider. An empty string removes the override.
    type: str
"""

EXAMPLES = r"""
- name: Keycloak login
  croit.ceph.oidc_provider:
    name: Keycloak
    discovery_url: https://sso.example.com/realms/ops/.well-known/openid-configuration
    client_id: croit
    client_secret: "{{ vault_croit_oidc_secret }}"
    client_auth: basic
    group_pointer: groups
    role_mapping:
      storage-admins: admin
      storage-viewers: viewer
    default_roles: [viewer]

- name: Remove a provider (logs its users out)
  croit.ceph.oidc_provider:
    name: Old SSO
    state: absent
"""

RETURN = r"""
oidc_provider:
  description:
    - The provider as croit reports it after the change (C(OidcConfigResponse) in the croit API),
      with C(clientSecret) masked.
    - Before the change in check mode; empty when the provider does not exist.
  returned: always
  type: dict
task:
  description: The croit background task the change ran as, when there was one.
  returned: when a task ran
  type: dict
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
