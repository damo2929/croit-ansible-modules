# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""Helpers shared by the croit.ceph.smb_* modules.

croit SMB clusters have no name of their own: the modules identify a cluster
by its description (the ``name`` option), or by croit's numeric service id.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import ipaddress

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join

TYPE_SIMPLE = "simple"
TYPE_AD = "active-directory"
# Ansible option value -> croit SambaServiceApiType.
TYPES = dict(simple=TYPE_SIMPLE, active_directory=TYPE_AD)


def list_clusters(croit_module):
    """Every SMB cluster as croit lists it (SmbGatewayConfigResponse)."""
    return croit_module.get_list("/gateways/smb")


def find_cluster(croit_module, ident, clusters=None):
    """Cluster by description or numeric service id; None when there is none.

    A description takes precedence over an id, so a cluster described as
    "12" still works. Several clusters with the same description fail.
    """
    if clusters is None:
        clusters = list_clusters(croit_module)
    text = str(ident)
    matches = [c for c in clusters if (c.get("description") or "") == text]
    if len(matches) > 1:
        croit_module.module.fail_json(
            msg="%d SMB clusters are described as %r; use the numeric service id instead" % (len(matches), text)
        )
    if not matches and text.isdigit():
        matches = [c for c in clusters if c.get("serviceId") == int(text)]
    return matches[0] if matches else None


def require_cluster(croit_module, ident, clusters=None):
    """Like find_cluster(), but fails the module when the cluster does not exist."""
    if clusters is None:
        clusters = list_clusters(croit_module)
    found = find_cluster(croit_module, ident, clusters)
    if found is None:
        croit_module.module.fail_json(
            msg="SMB cluster %r is not known to croit. Known clusters: %s"
            % (ident, ", ".join("%s (%s)" % (c.get("description"), c.get("serviceId")) for c in clusters) or "none")
        )
    return found


def cluster_detail(croit_module, service_id):
    """The cluster's stored configuration with servers and shares (SmbGatewayServiceResponse)."""
    return croit_module.get(path_join("services", "smb", service_id))


def generation(config):
    """croit's template generation of a cluster: 1 is legacy, 2+ has managed local users."""
    return config.get("configGeneration") or 1


def require_managed_accounts(croit_module, config, what):
    """Managed local users and groups exist only on generation-2 clusters without Active Directory."""
    if config.get("type") != TYPE_SIMPLE or generation(config) < 2:
        croit_module.module.fail_json(
            msg="SMB cluster %r has no managed local %s: they exist only on generation-2 clusters without "
            "Active Directory (this one is %s, generation %s)"
            % (config.get("description"), what, config.get("type"), generation(config))
        )


def normalise_ip(value):
    """An IP or IP/prefix in canonical notation; anything unparsable is returned unchanged."""
    text = str(value).strip()
    try:
        if "/" in text:
            return str(ipaddress.ip_interface(text))
        return str(ipaddress.ip_address(text))
    except ValueError:
        return text


def options_view(options):
    """SmbShareOptions as Ansible sub-options, with missing members as empty values."""
    options = options or {}
    return dict(
        parameters=dict(options.get("parameters") or {}),
        vfs_objects=list(options.get("vfsObjects") or []),
        vfs_objects_before=list(options.get("vfsObjectsBefore") or []),
    )


def options_request(view):
    """Ansible options view -> SmbShareOptions request body."""
    return dict(
        parameters=view["parameters"],
        vfsObjects=view["vfs_objects"],
        vfsObjectsBefore=view["vfs_objects_before"],
    )


def merge_options(current_view, desired):
    """Merge the set sub-options of ``desired`` into ``current_view``; return (merged, differs).

    Parameters are compared as a dict (values as strings); the VFS module
    lists keep their order, which matters to Samba.
    """
    merged = dict(current_view)
    if desired.get("parameters") is not None:
        merged["parameters"] = dict((k, str(v)) for k, v in desired["parameters"].items())
    for key in ("vfs_objects", "vfs_objects_before"):
        if desired.get(key) is not None:
            merged[key] = list(desired[key])
    return merged, merged != current_view


OPTIONS_SPEC = dict(
    parameters=dict(type="dict"),
    vfs_objects=dict(type="list", elements="str"),
    vfs_objects_before=dict(type="list", elements="str"),
)
