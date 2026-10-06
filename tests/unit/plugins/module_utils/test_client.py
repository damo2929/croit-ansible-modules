# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from urllib.error import URLError

import pytest

from ansible_collections.croit.ceph.plugins.module_utils.client import (
    CroitClient,
    CroitError,
    CroitWarning,
    path_join,
    unwrap_list,
)
from ansible_collections.croit.ceph.tests.unit.fake_croit import API_URL, FakeCroit, Text


def client(fake):
    return CroitClient(API_URL + "/", "tok", opener=fake)


def test_bearer_token_and_json_headers():
    fake = FakeCroit()
    fake.reply("POST", "/things", 200, dict(ok=True))
    status, data = client(fake).request("POST", "/things", body=dict(a=1))
    assert (status, data) == (200, dict(ok=True))
    call = fake.calls[0]
    assert call.headers["Authorization"] == "Bearer tok"
    assert call.headers["Content-Type"] == "application/json"
    assert call.body == dict(a=1)


def test_no_body_sends_no_content_type():
    fake = FakeCroit()
    fake.reply("GET", "/things", 200, [])
    client(fake).get("/things")
    assert "Content-Type" not in fake.calls[0].headers


def test_path_join_quotes_segments():
    assert path_join("pools", "a b/c", 3) == "/pools/a%20b%2Fc/3"


def test_query_encoding():
    fake = FakeCroit()
    fake.reply("GET", "/tasks/status", 200, [])
    client(fake).get("/tasks/status", query=dict(taskIds=[1, 2], skip=None, flag=True))
    assert fake.calls[0].query == dict(taskIds=["1", "2"], flag="true")


@pytest.mark.parametrize(
    "data,expected",
    [(None, []), ([1], [1]), (dict(data=[2], total=1, after=0), [2])],
)
def test_unwrap_list(data, expected):
    assert unwrap_list(data) == expected


def test_unwrap_list_rejects_other_shapes():
    with pytest.raises(CroitError):
        unwrap_list(dict(foo=1))


def test_error_message_and_details():
    fake = FakeCroit()
    fake.reply("GET", "/x", 500, dict(code=500, message="boom", details="trace"))
    with pytest.raises(CroitError) as e:
        client(fake).get("/x")
    assert e.value.status == 500
    assert "boom" in e.value.message
    assert e.value.details == "trace"


@pytest.mark.parametrize("status,hint", [(401, "rejected"), (403, "admin role")])
def test_auth_errors_have_hints(status, hint):
    fake = FakeCroit()
    fake.reply("GET", "/x", status, dict(code=status, message="nope"))
    with pytest.raises(CroitError) as e:
        client(fake).get("/x")
    assert hint in e.value.message


def test_get_or_none_on_404():
    fake = FakeCroit()
    assert client(fake).get_or_none("/missing") is None


def _warning_route(fake, tokens):
    """Answer a warning for each token not yet confirmed, then succeed."""
    pending = list(tokens)

    def handler(call):
        if pending:
            token = pending.pop(0)
            return 400, dict(
                code=400,
                message="careful",
                ignorableWarning=dict(token=token, warningText="really %s?" % token, affirmativeLabel="Yes"),
            )
        return 204, None

    fake.route("PATCH", "/pools/p", handler)


def test_warning_raised_when_not_ignored():
    fake = FakeCroit()
    _warning_route(fake, ["t1"])
    with pytest.raises(CroitWarning) as e:
        client(fake).request("PATCH", "/pools/p", body={})
    assert e.value.token == "t1"
    assert e.value.warning_text == "really t1?"
    assert len(fake.calls) == 1


def test_chained_warnings_confirmed_when_ignored():
    fake = FakeCroit()
    _warning_route(fake, ["t1", "t2"])
    status = client(fake).request("PATCH", "/pools/p", body={}, ignore_warnings=True)[0]
    assert status == 204
    assert [c.query.get("ignoreWarning") for c in fake.calls] == [None, "t1", "t2"]


def test_plain_400_is_an_error_not_a_warning():
    fake = FakeCroit()
    fake.reply("POST", "/x", 400, dict(code=400, message="bad input"))
    with pytest.raises(CroitError) as e:
        client(fake).request("POST", "/x", ignore_warnings=True)
    assert not isinstance(e.value, CroitWarning)
    assert len(fake.calls) == 1


def test_unreachable():
    def opener(*args, **kwargs):
        raise URLError("connection refused")

    with pytest.raises(CroitError) as e:
        CroitClient(API_URL, "tok", opener=opener).get("/x")
    assert "Could not reach croit" in e.value.message


def test_transport_error_does_not_leak_query_secrets():
    def opener(*args, **kwargs):
        raise OSError("timed out")

    with pytest.raises(CroitError) as e:
        CroitClient(API_URL, "tok", opener=opener).request("PUT", "/s3/users/u/keys/AK", query=dict(secretKey="s3cr3t"))
    assert "s3cr3t" not in e.value.message
    assert "/s3/users/u/keys/AK" in e.value.message


def test_text_plain_is_not_json_decoded():
    fake = FakeCroit()
    fake.route("GET", "/events/scripts/1", lambda call: (200, Text("42")))
    fake.reply("GET", "/json", 200, 42)
    assert client(fake).get("/events/scripts/1") == "42"
    assert client(fake).get("/json") == 42
