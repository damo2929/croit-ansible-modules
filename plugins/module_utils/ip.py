# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""IP address parsing and comparison, using Python's ``ipaddress`` module.

This is the same code the ``ansible.utils.ipv6form`` filter runs for
``compress`` (``ipaddress.ip_address(value).compressed``). Modules cannot
import filter plugins, because AnsiballZ only bundles ``module_utils``, so
the modules call the standard library directly. Every parse error is raised
as ``ValueError``.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import ipaddress

from ansible.module_utils.common.text.converters import to_text


def ip_address(value):
    """An IPv4Address or IPv6Address for an address without prefix length."""
    return ipaddress.ip_address(to_text(value).strip())


def ip_interface(value):
    """An IPv4Interface or IPv6Interface that keeps the host bits, for ``address`` or ``address/prefix``.

    Without a prefix length the address is a single host (/32 or /128).
    """
    return ipaddress.ip_interface(to_text(value).strip())


def ip_network(value):
    """The network (host bits cleared) of ``address`` or ``address/prefix``."""
    return ipaddress.ip_network(to_text(value).strip(), strict=False)


def normalise_ip(value):
    """An IPv4/IPv6 address or address/prefix in canonical (compressed) notation.

    ``2001:DB8:0:0::1/64`` and ``2001:db8::1/64`` compare equal once normalised.
    Empty values become ``""``; anything unparsable is returned stripped but unchanged.
    """
    text = to_text(value or "").strip()
    try:
        if "/" in text:
            return str(ip_interface(text))
        return ip_address(text).compressed
    except ValueError:
        return text


def normalise_network(value):
    """A subnet in canonical CIDR notation (host bits cleared); unparsable values are returned unchanged."""
    text = to_text(value or "").strip()
    try:
        return str(ip_network(text))
    except ValueError:
        return text
