# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.croit.ceph.plugins.module_utils.module import (
    CheckModeViolation,
    CroitModule,
    ceil_mib,
    changed_fields,
    parse_mode,
    parse_quota,
    parse_size,
)
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        (0, 0),
        (1024, 1024),
        ("1024", 1024),
        ("1K", 1024),
        ("100G", 100 * 1024 ** 3),
        ("100GiB", 100 * 1024 ** 3),
        ("100gb", 100 * 1024 ** 3),
        ("1.5T", int(1.5 * 1024 ** 4)),
        (" 2 M ", 2 * 1024 ** 2),
    ],
)
def test_parse_size(value, expected):
    assert parse_size(value) == expected


@pytest.mark.parametrize("value", ["abc", "-1", "1.5", "10X", True, -5])
def test_parse_size_invalid(value):
    with pytest.raises(ValueError):
        parse_size(value)


def test_changed_fields_ignores_unset():
    assert changed_fields(dict(a=1, b=2), dict(a=1, b=3, c=None)) == ["b"]


def test_write_in_check_mode_is_refused(monkeypatch):
    fake = FakeCroit()
    fake.reply("POST", "/x", 200, {})

    def main():
        m = CroitModule(dict())
        m.write("POST", "/x")

    with pytest.raises(CheckModeViolation):
        run_module(monkeypatch, fake, main, check_mode=True)
    assert fake.calls == []


def test_api_url_and_token_from_environment(monkeypatch):
    monkeypatch.setenv("CROIT_API_URL", "https://env.test/api")
    monkeypatch.setenv("CROIT_API_TOKEN", "env-token")
    fake = FakeCroit()

    def main():
        m = CroitModule(dict())
        m.exit(url=m.params["api_url"], token_set=m.params["api_token"] == "env-token")

    result = run_module(monkeypatch, fake, main, api_url=None, api_token=None)
    assert result["url"] == "https://env.test/api"
    assert result["token_set"]


def test_warning_fails_with_hint(monkeypatch):
    fake = FakeCroit()
    fake.reply("POST", "/x", 400, dict(code=400, message="m", ignorableWarning=dict(token="t", warningText="sure?")))

    def main():
        CroitModule(dict()).write("POST", "/x")

    result = run_module(monkeypatch, fake, main)
    assert result["failed"]
    assert "ignore_warnings=true" in result["msg"]
    assert result["warning"] == "sure?"


@pytest.mark.parametrize("value,expected", [(None, None), ("unlimited", 0), ("INF", 0), ("none", 0), (0, 0), ("10G", 10 * 1024 ** 3)])
def test_parse_quota(value, expected):
    assert parse_quota(value) == expected


@pytest.mark.parametrize("value,expected", [(None, None), ("755", 0o755), ("0750", 0o750), ("1777", 0o1777)])
def test_parse_mode(value, expected):
    assert parse_mode(value) == expected


@pytest.mark.parametrize("value", ["rwx", "8", "99999", "75"])
def test_parse_mode_invalid(value):
    with pytest.raises(ValueError):
        parse_mode(value)


def test_confirm_warnings_overrides_ignore_warnings(monkeypatch):
    fake = FakeCroit()

    def handler(call):
        if call.query.get("ignoreWarning") == "t":
            return 204, None
        return 400, dict(code=400, message="m", ignorableWarning=dict(token="t", warningText="sure?"))

    fake.route("DELETE", "/x", handler)

    def main():
        m = CroitModule(dict())
        m.write("DELETE", "/x", confirm_warnings=True)
        m.exit(changed=True)

    result = run_module(monkeypatch, fake, main, ignore_warnings=False)
    assert result["changed"] and not result.get("failed")
    assert [c.query.get("ignoreWarning") for c in fake.calls] == [None, "t"]


@pytest.mark.parametrize("value,expected", [(0, 0), (1, 1024 ** 2), (1024 ** 2, 1024 ** 2), (1024 ** 2 + 1, 2 * 1024 ** 2)])
def test_ceil_mib(value, expected):
    assert ceil_mib(value) == expected
