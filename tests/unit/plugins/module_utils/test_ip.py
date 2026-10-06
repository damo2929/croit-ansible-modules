# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.croit.ceph.plugins.module_utils.ip import (
    ip_address,
    ip_interface,
    ip_network,
    normalise_ip,
    normalise_network,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2001:DB8:0:0::1/64", "2001:db8::1/64"),
        ("2001:0db8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
        (" 192.0.2.10/24 ", "192.0.2.10/24"),
        ("", ""),
        (None, ""),
        ("not-an-ip", "not-an-ip"),
        ("10.1", "10.1"),  # inet_aton shorthand is not an address
        ("192.0.2.1/33", "192.0.2.1/33"),
    ],
)
def test_normalise_ip(value, expected):
    assert normalise_ip(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2001:db8:300:ff::25/56", "2001:db8:300::/56"),
        ("2001:db8:300:ff::25", "2001:db8:300:ff::25/128"),
        ("192.0.2.77/24", "192.0.2.0/24"),
        ("bogus", "bogus"),
    ],
)
def test_normalise_network(value, expected):
    assert normalise_network(value) == expected


def test_interface_keeps_host_bits():
    iface = ip_interface("2001:db8:100::11/64")
    assert str(iface.ip) == "2001:db8:100::11"
    assert iface.network.prefixlen == 64
    assert str(iface.network) == "2001:db8:100::/64"
    assert ip_address("2001:db8:100::1") in ip_network("2001:db8:100::11/64")
    assert ip_address("2001:db8:101::1") not in ip_network("2001:db8:100::/64")


@pytest.mark.parametrize("value", ["10.1", "300.0.0.1", "2001:db8::/abc", "2001:db8::/129", "", None])
def test_parse_errors_are_value_errors(value):
    with pytest.raises(ValueError):
        ip_interface(value)


def test_same_code_as_ansible_utils_ipv6form():
    # ansible.utils.ipv6form(value, 'compress') is ipaddress.ip_address(value).compressed
    assert normalise_ip("2001:0DB8:0000:0000:0000:0000:0000:0001") == "2001:db8::1"
