# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""RBD QoS limit helpers shared by croit.ceph.pool_qos and croit.ceph.rbd.

croit answers QoS as rows (``{"setting": {"command": <rbd config key>}, "value": n}``)
and takes changes as ``[{"command": key, "limit": n}]``, where a null limit removes it.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.module_utils.module import parse_size


def qos_current(rows):
    """Map rbd config key -> limit set at this level (None where unset)."""
    return dict((row["setting"]["command"], row.get("value")) for row in rows or [])


def qos_desired(croit_module, limits):
    """Parse the user's limits; values may be ints or binary sizes, None removes."""
    desired = {}
    for key, value in (limits or {}).items():
        if value is None:
            desired[key] = None
            continue
        try:
            desired[key] = parse_size(value)
        except ValueError as e:
            croit_module.module.fail_json(msg="QoS limit %s: %s" % (key, e))
    return desired


def qos_changes(croit_module, current, desired, exclusive=False, known=True):
    """Limits to send: key -> new value, where None removes the limit.

    With ``known``, keys croit does not offer fail the module. With
    ``exclusive``, set limits that are not in ``desired`` are removed.
    """
    if known:
        unknown = sorted(k for k in desired if k not in current)
        if unknown:
            croit_module.module.fail_json(
                msg="Unknown QoS setting(s) %s. croit offers: %s" % (", ".join(unknown), ", ".join(sorted(current)))
            )
    changes = dict((k, v) for k, v in desired.items() if current.get(k) != v)
    if exclusive:
        for key, value in current.items():
            if key not in desired and value is not None:
                changes[key] = None
    return changes


def qos_set_limits(current):
    """Only the limits that are set, for diffs."""
    return dict((k, v) for k, v in current.items() if v is not None)


def qos_apply(croit_module, path, changes, query=None):
    """POST the changes and fail if croit reports any row as not applied."""
    body = [dict(command=k, limit=v) for k, v in sorted(changes.items())]
    applied = croit_module.write("POST", path, body=body, query=query) or []
    failed = [row for row in applied if not row.get("success")]
    if failed:
        croit_module.module.fail_json(
            msg="croit could not apply QoS limit(s): %s"
            % "; ".join("%s: %s" % (row.get("command"), row.get("errorMessage")) for row in failed),
            applied=applied,
        )
    return applied
