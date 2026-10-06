# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.qos import (
    qos_apply,
    qos_changes,
    qos_current,
    qos_desired,
    qos_set_limits,
)
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

ROWS = [
    dict(setting=dict(command="rbd_qos_iops_limit"), value=1000),
    dict(setting=dict(command="rbd_qos_bps_limit"), value=None),
]


def test_current_and_set_limits():
    current = qos_current(ROWS)
    assert current == dict(rbd_qos_iops_limit=1000, rbd_qos_bps_limit=None)
    assert qos_set_limits(current) == dict(rbd_qos_iops_limit=1000)


def _run(monkeypatch, fake, body):
    def main():
        m = CroitModule(dict())
        m.exit(**body(m))

    return run_module(monkeypatch, fake, main)


def test_desired_changes_exclusive(monkeypatch):
    def body(m):
        current = qos_current(ROWS)
        desired = qos_desired(m, dict(rbd_qos_bps_limit="100M"))
        return dict(
            plain=qos_changes(m, current, desired),
            exclusive=qos_changes(m, current, desired, exclusive=True),
        )

    r = _run(monkeypatch, FakeCroit(), body)
    assert r["plain"] == dict(rbd_qos_bps_limit=100 * 1024 ** 2)
    assert r["exclusive"] == dict(rbd_qos_bps_limit=100 * 1024 ** 2, rbd_qos_iops_limit=None)


def test_unknown_key_fails(monkeypatch):
    r = _run(monkeypatch, FakeCroit(), lambda m: dict(c=qos_changes(m, qos_current(ROWS), dict(bogus=1))))
    assert r["failed"]
    assert "rbd_qos_bps_limit" in r["msg"]


def test_apply_fails_on_unapplied_row(monkeypatch):
    fake = FakeCroit()
    fake.reply("POST", "/pools/p/qos", 200, [dict(command="rbd_qos_iops_limit", success=False, errorMessage="nope")])
    r = _run(monkeypatch, fake, lambda m: dict(a=qos_apply(m, "/pools/p/qos", dict(rbd_qos_iops_limit=5))))
    assert r["failed"]
    assert "nope" in r["msg"]
    assert fake.calls[0].body == [dict(command="rbd_qos_iops_limit", limit=5)]
