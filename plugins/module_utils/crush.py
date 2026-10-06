# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# Simplified BSD License (see LICENSES/BSD-2-Clause.txt or https://opensource.org/licenses/BSD-2-Clause)
# SPDX-License-Identifier: BSD-2-Clause

"""CRUSH rule parsing shared by croit.ceph.crush_rule and croit.ceph.crush_info."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

CHOOSE_OPS = ("CHOOSE", "CHOOSE_INDEP", "CHOOSELEAF", "CHOOSELEAF_INDEP")


def take_groups(rule):
    """Split a rule's steps into take ... emit groups."""
    groups = []
    current = None
    for step in rule.get("steps") or []:
        op = step.get("op")
        if op == "TAKE":
            bucket = step.get("bucket")
            device_class = step.get("deviceClass")
            # ceph names a class-pinned take "<bucket>~<class>"
            if bucket and "~" in bucket and not device_class:
                bucket, device_class = bucket.split("~", 1)
            current = dict(start_bucket=bucket, device_class=device_class, failure_domain=None, num=None)
            groups.append(current)
        elif op in CHOOSE_OPS and current is not None:
            current["failure_domain"] = step.get("bucketType")
            current["num"] = step.get("num")
        elif op == "EMIT":
            current = None
    return groups


def layout(rule):
    """The rule as module options; type is 'custom' for layouts this module cannot create."""
    if not rule:
        return {}
    groups = take_groups(rule)
    if len(groups) == 1:
        g = groups[0]
        return dict(
            type="simple",
            start_bucket=g["start_bucket"],
            failure_domain=g["failure_domain"],
            device_class=g["device_class"],
            erasure_coding=rule.get("type") == "ERASURE",
        )
    if len(groups) == 2 and rule.get("type") != "ERASURE":
        ssd, hdd = groups
        return dict(
            type="ssd_primary",
            ssd_start_bucket=ssd["start_bucket"],
            ssd_failure_domain=ssd["failure_domain"],
            ssd_device_class=ssd["device_class"],
            ssd_copies=ssd["num"],
            hdd_start_bucket=hdd["start_bucket"],
            hdd_failure_domain=hdd["failure_domain"],
            hdd_device_class=hdd["device_class"],
        )
    return dict(type="custom")
