# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""A small in-memory stand-in for the croit API, plus module test helpers."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import contextlib
import copy
import io
import json
import re
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit

from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes

API_URL = "https://croit.test/api"


class Response:
    def __init__(self, status, body, content_type="application/json"):
        self.status = status
        self.body = body
        self.headers = {"Content-Type": content_type}

    def getcode(self):
        return self.status

    def read(self):
        if self.body is None:
            return b""
        if not self.headers["Content-Type"].startswith("application/json"):
            return to_bytes(self.body)
        return to_bytes(json.dumps(self.body))


class Text(object):
    """Wrap a handler's body to answer it as text/plain instead of JSON."""

    def __init__(self, text):
        self.text = text


class Call:
    def __init__(self, method, path, query, body, headers):
        self.method = method
        self.path = path
        self.query = query
        self.body = body
        self.headers = headers

    def __repr__(self):
        return "%s %s" % (self.method, self.path)


class FakeCroit:
    """Routes requests to handlers registered per (method, path pattern).

    Patterns are regexes matched against the decoded path, e.g. r"/pools/(?P<name>[^/]+)".
    A handler gets (call, **groups) and returns (status, body).
    """

    def __init__(self):
        self.routes = []
        self.calls = []
        self.tasks = {}
        self._next_task = 100

    def route(self, method, pattern, handler):
        self.routes.append((method, re.compile("^%s$" % pattern), handler))

    def reply(self, method, pattern, status, body=None):
        self.route(method, pattern, lambda call, **kw: (status, copy.deepcopy(body)))

    def __call__(self, url, method="GET", data=None, headers=None, **kwargs):
        parts = urlsplit(url)
        assert parts.path.startswith("/api"), url
        path = unquote(parts.path[len("/api"):])
        query = dict((k, v if len(v) > 1 else v[0]) for k, v in parse_qs(parts.query).items())
        body = json.loads(data) if data else None
        call = Call(method, path, query, body, headers or {})
        self.calls.append(call)
        for r_method, pattern, handler in self.routes:
            match = pattern.match(path)
            if r_method == method and match:
                status, payload = handler(call, **match.groupdict())
                break
        else:
            status, payload = 404, dict(code=404, message="no fake route for %s %s" % (method, path))
        if 200 <= status < 300:
            if isinstance(payload, Text):
                return Response(status, payload.text, content_type="text/plain; charset=utf-8")
            return Response(status, payload)
        raise HTTPError(url, status, "error", {}, io.BytesIO(to_bytes(json.dumps(payload))))

    # Tasks ----------------------------------------------------------------

    def new_task(self, name, obj=None, state="FINISHED", output="done"):
        self._next_task += 1
        task = dict(
            id=self._next_task,
            name=name,
            object=obj,
            state=state,
            done=state in ("FINISHED", "FAILED", "CANCELED"),
            statusCode={"FINISHED": 0, "FAILED": 1, "CANCELED": -256}.get(state, -1),
            startedAt="2026-10-06T12:00:00Z",
            startedBy="ansible",
            result=None,
            output=output,
            cancelled=state == "CANCELED",
            question=None,
        )
        self.tasks[task["id"]] = task
        return task

    def serve_tasks(self, finish_on_poll=False):
        """Serve GET /tasks/{id}; optionally finish running tasks when polled."""

        def get_task(call, task_id):
            task = self.tasks.get(int(task_id))
            if task is None:
                return 404, dict(code=404, message="Not Found")
            if finish_on_poll and not task["done"] and not task.get("question"):
                task.update(state="FINISHED", done=True, statusCode=0)
            return 200, copy.deepcopy(task)

        self.route("GET", r"/tasks/(?P<task_id>\d+)", get_task)

    # Assertions -----------------------------------------------------------

    def writes(self):
        return [c for c in self.calls if c.method != "GET"]


class AnsibleExitJson(Exception):
    def __init__(self, result):
        super(AnsibleExitJson, self).__init__(result)
        self.result = result


class AnsibleFailJson(Exception):
    def __init__(self, result):
        super(AnsibleFailJson, self).__init__(result)
        self.result = result


def _exit_json(self, **kwargs):
    kwargs.setdefault("changed", False)
    raise AnsibleExitJson(kwargs)


def _fail_json(self, **kwargs):
    kwargs["failed"] = True
    raise AnsibleFailJson(kwargs)


@contextlib.contextmanager
def module_args(args):
    """Set module arguments, across ansible-core 2.14 .. current."""
    try:
        from ansible.module_utils.testing import patch_module_args  # ansible-core >= 2.19
    except ImportError:
        patch_module_args = None
    if patch_module_args is not None:
        with patch_module_args(args):
            yield
    else:
        old = basic._ANSIBLE_ARGS
        basic._ANSIBLE_ARGS = to_bytes(json.dumps(dict(ANSIBLE_MODULE_ARGS=args)))
        try:
            yield
        finally:
            basic._ANSIBLE_ARGS = old


def run_module(monkeypatch, fake, main, check_mode=False, diff=True, **params):
    """Run a module's main() against ``fake`` and return its result dict.

    Failures come back as a result with ``failed=True``.
    """
    args = dict(api_url=API_URL, api_token="secret-token")
    args.update(params)
    # None means "not passed", so env fallbacks can be tested.
    args = dict((k, v) for k, v in args.items() if not (k in ("api_url", "api_token") and v is None))
    args["_ansible_check_mode"] = check_mode
    args["_ansible_diff"] = diff
    monkeypatch.setattr(basic.AnsibleModule, "exit_json", _exit_json)
    monkeypatch.setattr(basic.AnsibleModule, "fail_json", _fail_json)
    monkeypatch.setattr("ansible_collections.croit.ceph.plugins.module_utils.client.open_url", fake)
    monkeypatch.setattr("ansible_collections.croit.ceph.plugins.module_utils.tasks.time.sleep", lambda s: None)
    fake.calls = []
    with module_args(args):
        try:
            main()
        except AnsibleExitJson as e:
            return e.result
        except AnsibleFailJson as e:
            return e.result
    raise AssertionError("module did not call exit_json or fail_json")
