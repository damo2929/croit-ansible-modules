# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""Base class and helpers shared by every croit.ceph module.

Enforces the idempotency / check mode contract from DESIGN.md section 3:
in check mode only GET requests can reach croit.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

from ansible.module_utils.basic import AnsibleModule, env_fallback

from ansible_collections.croit.ceph.plugins.module_utils.client import (
    CroitClient,
    CroitError,
    CroitWarning,
)
from ansible_collections.croit.ceph.plugins.module_utils.tasks import (
    check_task,
    is_task,
    wait_for_task,
)

CONNECTION_ARGS = dict(
    api_url=dict(type="str", required=True, fallback=(env_fallback, ["CROIT_API_URL"])),
    api_token=dict(type="str", required=True, no_log=True, fallback=(env_fallback, ["CROIT_API_TOKEN"])),
    validate_certs=dict(type="bool", default=True),
    timeout=dict(type="int", default=30),
)

WAIT_ARGS = dict(
    wait=dict(type="bool", default=True),
    wait_timeout=dict(type="int", default=600),
)

WARNING_ARGS = dict(
    ignore_warnings=dict(type="bool", default=False),
)


class CheckModeViolation(Exception):
    """A module tried to write while in check mode. Always a bug."""


class CroitModule:
    """AnsibleModule wrapper with croit connection handling.

    :param wait: add the ``wait``/``wait_timeout`` options.
    :param warnings: add the ``ignore_warnings`` option.
    """

    def __init__(self, argument_spec, wait=True, warnings=True, **kwargs):
        spec = dict(CONNECTION_ARGS)
        if wait:
            spec.update(WAIT_ARGS)
        if warnings:
            spec.update(WARNING_ARGS)
        spec.update(argument_spec)
        kwargs.setdefault("supports_check_mode", True)
        self.module = AnsibleModule(argument_spec=spec, **kwargs)
        self.params = self.module.params
        self.check_mode = self.module.check_mode
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = CroitClient(
                self.params["api_url"],
                self.params["api_token"],
                validate_certs=self.params["validate_certs"],
                timeout=self.params["timeout"],
            )
        return self._client

    # Requests -------------------------------------------------------------

    def get(self, path, query=None):
        try:
            return self.client.get(path, query=query)
        except CroitError as e:
            self.fail_from(e)

    def get_list(self, path, query=None):
        try:
            return self.client.get_list(path, query=query)
        except CroitError as e:
            self.fail_from(e)

    def get_or_none(self, path, query=None):
        try:
            return self.client.get_or_none(path, query=query)
        except CroitError as e:
            self.fail_from(e)

    def write(self, method, path, body=None, query=None, confirm_warnings=False):
        """Send a non-GET request. Never reachable in check mode.

        ``confirm_warnings`` confirms croit's ignorable warnings regardless of
        ``ignore_warnings``. Only use it for actions the user already confirmed
        explicitly, such as ``confirm_delete=true``.
        """
        if self.check_mode:
            raise CheckModeViolation("%s %s attempted in check mode" % (method, path))
        try:
            return self.client.request(
                method,
                path,
                body=body,
                query=query,
                ignore_warnings=confirm_warnings or self.params.get("ignore_warnings", False),
            )[1]
        except CroitWarning as e:
            self.module.fail_json(
                msg="%s. Re-run with ignore_warnings=true to confirm it." % e.message,
                warning=e.warning_text,
                status=e.status,
            )
        except CroitError as e:
            self.fail_from(e)

    # Tasks ----------------------------------------------------------------

    def handle_task(self, data):
        """Wait for (and judge) a task answered by a write, if any.

        Returns the final task, the unfinished task when wait=false, or None
        when the answer was not a task.
        """
        if not is_task(data):
            return None
        if not self.params.get("wait", True):
            return data
        try:
            return check_task(wait_for_task(self.client, data, self.params["wait_timeout"]))
        except CroitError as e:
            self.fail_from(e)

    # Results --------------------------------------------------------------

    def fail_from(self, error):
        self.module.fail_json(**error.to_fail_kwargs())

    def exit(self, changed=False, before=None, after=None, **result):
        if self.module._diff and (before is not None or after is not None):
            result["diff"] = dict(before=before or {}, after=after or {})
        self.module.exit_json(changed=changed, **result)


# Comparison helpers --------------------------------------------------------

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGTPE]?)(i?B?)?\s*$", re.IGNORECASE)
_SIZE_POWERS = dict(K=1, M=2, G=3, T=4, P=5, E=6)


def parse_size(value):
    """Convert a human size to bytes using binary units, as ceph does.

    Accepts ints, ``"1024"``, ``"100G"``, ``"100GiB"``, ``"1.5T"``. Returns
    None for None.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("invalid size: %r" % (value,))
    if isinstance(value, int):
        if value < 0:
            raise ValueError("size must not be negative: %r" % (value,))
        return value
    match = _SIZE_RE.match(str(value))
    if not match:
        raise ValueError("invalid size %r; use bytes or a number with K, M, G, T, P or E" % (value,))
    number, unit = match.group(1), match.group(2).upper()
    result = float(number) * (1024 ** _SIZE_POWERS.get(unit, 0))
    if result != int(result):
        raise ValueError("size %r is not a whole number of bytes" % (value,))
    return int(result)


def changed_fields(current, desired):
    """Keys of ``desired`` (ignoring None values) whose value differs from ``current``."""
    return [key for key, value in desired.items() if value is not None and current.get(key) != value]


def subset(data, keys):
    return dict((k, data.get(k)) for k in keys)


# Words that mean "no quota / no limit" in quota options.
UNLIMITED_WORDS = ("unlimited", "inf", "infinite", "none")
_MODE_RE = re.compile(r"^0?[0-7]{3,4}$")


def parse_quota(value):
    """Quota option -> bytes, with 0 meaning no quota. None means not managed."""
    if value is None:
        return None
    if str(value).strip().lower() in UNLIMITED_WORDS:
        return 0
    return parse_size(value)


def parse_mode(value):
    """Octal permission string such as '755' or '0750' -> int. None means not managed."""
    if value is None:
        return None
    if not _MODE_RE.match(str(value)):
        raise ValueError("mode %r is not an octal permission such as '755'" % (value,))
    return int(str(value), 8)


MIB = 1024 * 1024


def ceil_mib(size):
    """Round a byte count up to a whole number of MiB (RBD sizes are MiB-aligned)."""
    return (int(size) + MIB - 1) // MIB * MIB
