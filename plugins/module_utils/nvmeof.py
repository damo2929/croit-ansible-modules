# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""NVMe-oF gateway lookups shared by the croit.ceph.nvmeof_* modules."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.module_utils.lookup import find_one


def find_gateway(croit_module, gateway, gateways):
    """NVMe-oF cluster by name or numeric id among ``gateways``; None if unknown."""
    text = str(gateway)
    try:
        found = find_one(gateways, "NVMe-oF cluster", "name", text)
    except ValueError as e:
        croit_module.module.fail_json(msg=str(e))
    if found is None and text.isdigit():
        found = find_one(gateways, "NVMe-oF cluster", "gatewayId", int(text))
    return found


def require_gateway(croit_module, gateway, gateways=None):
    """NVMe-oF cluster by name or numeric id; fails when unknown or ambiguous."""
    if gateways is None:
        gateways = croit_module.get_list("/gateways/nvmeof")
    found = find_gateway(croit_module, gateway, gateways)
    if found is None:
        croit_module.module.fail_json(
            msg="NVMe-oF cluster %r does not exist. Known clusters: %s"
            % (gateway, ", ".join("%s (%s)" % (g.get("name"), g.get("gatewayId")) for g in gateways) or "none")
        )
    return found


def find_service(services, ident):
    """Target service by service name, server hostname or numeric id."""
    text = str(ident)
    for key in ("name", "serverHostname"):
        matches = [s for s in services if s.get(key) == text]
        if len(matches) > 1:
            raise ValueError("%d target services match %r; use the service name or id" % (len(matches), text))
        if matches:
            return matches[0]
    if text.isdigit():
        return next((s for s in services if s.get("serviceId") == int(text)), None)
    return None
