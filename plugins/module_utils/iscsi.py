# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""iSCSI gateway helpers shared by the croit.ceph.iscsi_* modules."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.module_utils.module import MIB, ceil_mib, parse_size


def find_service(croit_module, service_id):
    """The iSCSI gateway service row, or None. Fails when it is ambiguous."""
    services = croit_module.get_list("/gateways/iscsi")
    if service_id is not None:
        found = [s for s in services if s.get("serviceId") == service_id]
        if not found:
            croit_module.module.fail_json(
                msg="No iSCSI gateway with service_id %s. Known: %s"
                % (service_id, ", ".join(str(s.get("serviceId")) for s in services) or "none")
            )
        return found[0]
    if len(services) > 1:
        croit_module.module.fail_json(
            msg="croit reports %d iSCSI gateways (%s); set service_id"
            % (len(services), ", ".join(str(s.get("serviceId")) for s in services))
        )
    return services[0] if services else None


def require_service(croit_module, service_id):
    """The iSCSI gateway service row; fails when there is none or it is ambiguous."""
    services = croit_module.get_list("/gateways/iscsi")
    if service_id is not None:
        services = [s for s in services if s.get("serviceId") == service_id]
    if not services:
        croit_module.module.fail_json(
            msg="The cluster has no iSCSI gateway%s; create it with croit.ceph.iscsi_gateway"
            % ("" if service_id is None else " with service_id %s" % service_id)
        )
    if len(services) > 1:
        croit_module.module.fail_json(msg="croit reports several iSCSI gateways; set service_id")
    return services[0]


def disk_key(entry):
    return "%s/%s" % (entry.get("pool"), entry.get("image"))


def disk_request(croit_module, entry):
    """A disks[] option entry -> IscsiAddDiskToClientRequest."""
    body = dict(pool=entry["pool"], name=entry["image"])
    if entry.get("size") is not None:
        try:
            size = parse_size(entry["size"])
        except ValueError as e:
            croit_module.module.fail_json(msg="disks[%s].size: %s" % (disk_key(entry), e))
        if not size:
            croit_module.module.fail_json(msg="disks[%s].size must be greater than 0" % disk_key(entry))
        body["size"] = ceil_mib(size) // MIB
    if entry.get("backstore") is not None:
        body["backstore"] = entry["backstore"]
    return body
