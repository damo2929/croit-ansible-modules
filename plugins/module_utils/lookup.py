# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""Natural-key lookups shared by modules: playbooks name things, croit numbers them."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re


def find_one(items, what, key, value):
    """The single item whose ``key`` equals ``value``; None if none. Fails on duplicates via ValueError."""
    matches = [item for item in items if item.get(key) == value]
    if len(matches) > 1:
        raise ValueError("%d %ss have %s %r; use the numeric id instead" % (len(matches), what, key, value))
    return matches[0] if matches else None


def list_servers(croit_module):
    return croit_module.get_list("/servers")


def find_server(croit_module, server, servers=None):
    """Resolve a server given by hostname or numeric id (int or digit string).

    Returns the ServerResponse dict, or None when no server matches. A
    hostname takes precedence over an id, so a server named "12" still works.
    """
    if server is None:
        return None
    if servers is None:
        servers = list_servers(croit_module)
    text = str(server)
    try:
        found = find_one(servers, "server", "hostname", text)
    except ValueError as e:
        croit_module.module.fail_json(msg=str(e))
    if found is None and text.isdigit():
        found = find_one(servers, "server", "id", int(text))
    return found


def require_server(croit_module, server, servers=None):
    """Like find_server(), but fails the module when the server does not exist."""
    if servers is None:
        servers = list_servers(croit_module)
    found = find_server(croit_module, server, servers)
    if found is None:
        croit_module.module.fail_json(
            msg="Server %r is not known to croit. Known servers: %s"
            % (server, ", ".join("%s (%s)" % (s.get("hostname"), s.get("id")) for s in servers) or "none")
        )
    return found


def require_disk(croit_module, disks, value, what="disk"):
    """Resolve a disk among one server's disks by device path, serial, WWN or numeric id.

    Fails the module when no disk or several disks match.
    """
    text = str(value).strip()
    candidates = []
    if text.startswith("/dev/"):
        candidates = [d for d in disks if text in (d.get("path"), d.get("pathRaw"))]
    if not candidates:
        candidates = [d for d in disks if text == d.get("serial") or text in (d.get("serials") or {}).values()]
    if not candidates:
        lowered = text.lower()
        candidates = [
            d
            for d in disks
            if lowered == (d.get("wwn") or "").lower()
            or lowered in [str(w).lower() for w in (d.get("wwns") or {}).values()]
        ]
    if not candidates and text.isdigit():
        candidates = [d for d in disks if d.get("id") == int(text)]
    if len(candidates) > 1:
        croit_module.module.fail_json(msg="%s %r matches %d disks; use croit's numeric disk id" % (what, value, len(candidates)))
    if not candidates:
        croit_module.module.fail_json(
            msg="%s %r was not found. Disks on this server: %s"
            % (
                what,
                value,
                ", ".join("%s (id %s, serial %s)" % (d.get("pathFormatted") or d.get("path"), d.get("id"), d.get("serial")) for d in disks)
                or "none",
            )
        )
    return candidates[0]


def normalise_mac(value):
    """MAC address reduced to lower-case hex digits, so any separator or case compares equal."""
    return re.sub(r"[^0-9a-f]", "", (value or "").lower())


def find_nic(croit_module, nics, ident):
    """Interface by croit name, Linux name or MAC address; None if there is none."""
    want = str(ident)
    matches = [n for n in nics if want in (n.get("name"), n.get("linuxName"))]
    if not matches and len(normalise_mac(want)) == 12:
        matches = [n for n in nics if normalise_mac(n.get("mac")) == normalise_mac(want)]
    if len(matches) > 1:
        croit_module.module.fail_json(
            msg="%d interfaces match %r: %s; use the MAC address"
            % (len(matches), want, ", ".join("%s (%s)" % (n.get("name"), n.get("mac")) for n in matches))
        )
    return matches[0] if matches else None


def resolve_interface(croit_module, server, nic, vlan_tag=None, servers=None, nics=None):
    """Resolve server + interface (+ optional VLAN tag) to croit records.

    ``nic`` is a croit name, Linux name, MAC address or numeric interface id.
    ``nics`` is the server's interface list when the caller already has it
    (it is fetched otherwise). Returns ``(server, nic, vlan_id)``, where
    ``vlan_id`` is croit's VLAN record id (not the tag), or None.
    """
    server_row = require_server(croit_module, server, servers)
    if nics is None:
        nics = croit_module.get_list("/servers/%s/nics" % server_row["id"])
    found = find_nic(croit_module, nics, nic)
    if found is None and str(nic).isdigit():
        found = next((n for n in nics if n.get("id") == int(nic)), None)
    if found is None:
        croit_module.module.fail_json(
            msg="Server %s has no interface %r. Interfaces: %s"
            % (server_row.get("hostname"), nic, ", ".join(sorted(str(n.get("name")) for n in nics)))
        )
    vlan_id = None
    if vlan_tag is not None:
        vlan = next((v for v in found.get("vlans") or [] if v.get("vlan") == vlan_tag), None)
        if vlan is None:
            croit_module.module.fail_json(
                msg="Interface %s on %s has no VLAN %s" % (found.get("name"), server_row.get("hostname"), vlan_tag)
            )
        vlan_id = vlan["id"]
    return server_row, found, vlan_id
