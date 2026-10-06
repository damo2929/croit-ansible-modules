# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""HTTP client for the croit REST API.

Only the Python standard library and ansible-core are used, so the collection
runs on a stock EL9 install (Python 3.9, ansible-core 2.14).
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode

from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.urls import open_url

# A request may chain several ignorable warnings; each one is confirmed with
# its own token. Bound the loop so a misbehaving server cannot spin forever.
MAX_WARNING_CONFIRMATIONS = 10

USER_AGENT = "croit.ceph-ansible-collection"


class CroitError(Exception):
    """An error answered by croit, or a failure to reach it."""

    def __init__(self, message, status=None, details=None, body=None):
        super(CroitError, self).__init__(message)
        self.message = message
        self.status = status
        self.details = details
        self.body = body

    def to_fail_kwargs(self):
        kwargs = dict(msg=self.message)
        if self.status is not None:
            kwargs["status"] = self.status
        if self.details:
            kwargs["details"] = self.details
        return kwargs


class CroitWarning(CroitError):
    """croit refused with an ignorable warning that has not been confirmed."""

    def __init__(self, warning_text, token, status=400, body=None):
        super(CroitWarning, self).__init__(
            "croit refused the change with a warning: %s" % warning_text,
            status=status,
            body=body,
        )
        self.warning_text = warning_text
        self.token = token


def path_join(*segments):
    """Build an API path from raw segments, URL-quoting each one.

    path_join('pools', 'my pool', 'details') -> '/pools/my%20pool/details'
    """
    return "/" + "/".join(quote(to_text(s), safe="") for s in segments)


def unwrap_list(data):
    """Return the item list from a croit list response.

    List endpoints answer a raw JSON array, or a pagination wrapper
    (``{"data": [...], "total": n, "after": n}``) when paginated.
    """
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    raise CroitError("Unexpected list response from croit: %r" % (data,))


def _content_type(resp):
    headers = getattr(resp, "headers", None)
    if headers is None:
        return ""
    try:
        return (headers.get("Content-Type") or "").lower()
    except AttributeError:
        return ""


def _parse_body(raw, content_type=""):
    if not raw:
        return None
    text = to_text(raw, errors="surrogate_or_strict")
    # Plain-text endpoints (e.g. a hook script's contents) are never JSON-decoded,
    # even when the text happens to be valid JSON.
    if content_type.startswith("text/"):
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


def _warning_from(body):
    if not isinstance(body, dict):
        return None
    warning = body.get("ignorableWarning")
    if isinstance(warning, dict) and warning.get("token"):
        return warning
    return None


class CroitClient:
    """Thin, stateless wrapper around the croit API using a bearer API token."""

    def __init__(self, api_url, api_token, validate_certs=True, timeout=30, opener=None):
        self.api_url = api_url.rstrip("/")
        self.api_token = api_token
        self.validate_certs = validate_certs
        self.timeout = timeout
        # Injected in unit tests; defaults to ansible's open_url.
        self._open = opener or open_url

    def _url(self, path, query):
        if not path.startswith("/"):
            path = "/" + path
        url = self.api_url + path
        if query:
            pairs = []
            for key, value in query.items():
                if value is None:
                    continue
                if isinstance(value, (list, tuple)):
                    pairs.extend((key, to_text(v)) for v in value)
                elif isinstance(value, bool):
                    pairs.append((key, "true" if value else "false"))
                elif isinstance(value, dict):
                    pairs.append((key, json.dumps(value, separators=(",", ":"))))
                else:
                    pairs.append((key, to_text(value)))
            if pairs:
                url += ("&" if "?" in url else "?") + urlencode(pairs)
        return url

    def _send(self, method, url, body):
        headers = {
            "Authorization": "Bearer %s" % self.api_token,
            "Accept": "application/json",
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body)
        try:
            resp = self._open(
                url,
                method=method,
                data=data,
                headers=headers,
                validate_certs=self.validate_certs,
                timeout=self.timeout,
                http_agent=USER_AGENT,
                follow_redirects="safe",
            )
            return resp.getcode(), _parse_body(resp.read(), _content_type(resp))
        except HTTPError as e:
            try:
                raw = e.read()
            except Exception:
                raw = None
            return e.code, _parse_body(raw)
        # Error messages never include the query string: some endpoints take
        # secrets as query parameters (e.g. S3 secret keys).
        except URLError as e:
            raise CroitError("Could not reach croit at %s: %s" % (self.api_url, to_text(e.reason)))
        except Exception as e:  # socket timeouts, SSL errors, ...
            raise CroitError("Request to croit failed (%s %s): %s" % (method, url.split("?", 1)[0], to_text(e)))

    def request(self, method, path, body=None, query=None, ignore_warnings=False):
        """Send one request and return ``(status, data)``.

        Raises CroitWarning when croit answers an ignorable warning that the
        caller did not allow to be confirmed, and CroitError for any other
        non-2xx answer.
        """
        method = method.upper()
        query = dict(query or {})
        for _attempt in range(MAX_WARNING_CONFIRMATIONS + 1):
            url = self._url(path, query)
            status, data = self._send(method, url, body)
            if 200 <= status < 300:
                return status, data

            warning = _warning_from(data) if status == 400 else None
            if warning is not None:
                if not ignore_warnings:
                    raise CroitWarning(
                        warning.get("warningText") or (data.get("message") if isinstance(data, dict) else ""),
                        warning["token"],
                        status=status,
                        body=data,
                    )
                query["ignoreWarning"] = warning["token"]
                continue

            raise self._error(method, path, status, data)

        raise CroitError(
            "croit kept answering warnings for %s %s after %d confirmations" % (method, path, MAX_WARNING_CONFIRMATIONS)
        )

    @staticmethod
    def _error(method, path, status, data):
        message = None
        details = None
        if isinstance(data, dict):
            message = data.get("message")
            details = data.get("details")
        elif isinstance(data, str) and data:
            message = data
        if status == 401:
            hint = "the API token was rejected; check api_token / CROIT_API_TOKEN"
        elif status == 403:
            hint = "the API token lacks the required role; changes need a token with the admin role"
        else:
            hint = None
        text = "croit answered HTTP %s for %s %s" % (status, method, path)
        if message:
            text += ": %s" % message
        if hint:
            text += " (%s)" % hint
        return CroitError(text, status=status, details=details, body=data)

    # Convenience wrappers -------------------------------------------------

    def get(self, path, query=None):
        return self.request("GET", path, query=query)[1]

    def get_list(self, path, query=None):
        return unwrap_list(self.get(path, query=query))

    def get_or_none(self, path, query=None):
        """GET a single resource, returning None on 404."""
        try:
            return self.get(path, query=query)
        except CroitError as e:
            if e.status == 404:
                return None
            raise
