#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /status
# croit-api: GET /status/croit-version
# croit-api: GET /cluster/status
# croit-api: GET /cluster/releases
# croit-api: GET /license

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: cluster_info
short_description: Read croit and Ceph cluster status
version_added: 0.1.0
description:
  - Gathers the state of the croit backend and the Ceph cluster it manages, for example to check the
    cluster is healthy before maintenance or to record the croit version.
  - O(gather) chooses which parts are read; each part is one croit API call. This module never changes
    anything.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
attributes:
  check_mode:
    support: full
  diff_mode:
    support: N/A
options:
  gather:
    description:
      - Which information to gather.
      - V(backend) is the croit backend status (C(/status)).
      - V(version) is the croit version string, for example C(v2508.1.squid).
      - V(status) is what croit and Ceph report about the cluster (C(/cluster/status)).
      - V(releases) is the Ceph releases the daemons run (C(/cluster/releases)).
      - V(license) is the croit licence and its usage (C(/license)).
    type: list
    elements: str
    choices: [backend, version, status, releases, license]
    default: [backend, version, status, releases, license]
seealso:
  - module: croit.ceph.task_info
    description: See which croit background tasks are running.
  - module: croit.ceph.osd_flag
    description: Set flags such as C(noout) around maintenance.
  - name: croit API reference
    description: The status, cluster and licence endpoints this module reads.
    link: https://www.croit.io/api-docs
  - name: Ceph health checks
    description: What the health checks reported in RV(status) mean.
    link: https://docs.ceph.com/en/latest/rados/operations/health-checks/
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Gather everything
  croit.ceph.cluster_info:
  register: cluster

- name: Check the cluster before maintenance
  croit.ceph.cluster_info:
    gather: [status, version]
  register: cluster

- name: Refuse to continue unless Ceph is healthy
  ansible.builtin.assert:
    that: cluster.status.cephStatus.health.status == 'HEALTH_OK'
    fail_msg: "Ceph reports {{ cluster.status.cephStatus.health.status }}"

- name: Show the croit version
  ansible.builtin.debug:
    msg: "{{ cluster.version }}"
"""

RETURN = r"""
backend:
  description: croit backend status (C(BackendStatus) in the croit API).
  returned: when V(backend) is gathered
  type: dict
  contains:
    status:
      description: Whether the croit backend itself works, one of V(UP), V(DB_ERROR) or V(INTERNAL_ERROR).
      returned: always
      type: str
      sample: UP
    cephConfigured:
      description: Whether Ceph is configured and its status can be queried.
      returned: always
      type: bool
      sample: true
    doSetup:
      description: Whether the cluster still has to be set up.
      returned: always
      type: bool
      sample: false
    currentVersion:
      description: The croit version this backend runs.
      returned: always
      type: str
      sample: v2508.1.squid
    licenseActive:
      description: Whether the cluster's licence is valid and active.
      returned: always
      type: bool
      sample: true
    error:
      description: What is critically wrong with croit, as one line, or V(null).
      returned: always
      type: str
      sample: null
version:
  description: The croit version string. A version croit cannot parse is reported as C(v0.0).
  returned: when V(version) is gathered
  type: str
  sample: v2508.1.squid
status:
  description:
    - Cluster status (C(ClusterStatus) in the croit API).
    - When Ceph is unreachable, C(cephStatus) is V(null) and C(fallbackClusterStatus) describes the cluster
      from croit's own records.
  returned: when V(status) is gathered
  type: dict
  contains:
    timestamp:
      description: When croit created this status report.
      returned: always
      type: str
      sample: "2026-10-06T12:00:00Z"
    cephStatus:
      description: Ceph's own status, including C(health.status) such as C(HEALTH_OK), C(fsid), C(osdMap) and C(pgMap); V(null) when Ceph is unreachable.
      returned: always
      type: dict
      sample:
        fsid: 2a3b4c5d-1111-2222-3333-444455556666
        health:
          status: HEALTH_OK
          checks: {}
    servers:
      description: How many servers croit knows, and how many are online and healthy.
      returned: always
      type: dict
      sample:
        total: 5
        online: 5
        healthy: 5
    s3Configured:
      description: Whether the cluster has an object gateway.
      returned: always
      type: bool
      sample: true
    licenseActive:
      description: Whether the croit licence is active.
      returned: always
      type: bool
      sample: true
releases:
  description: Ceph releases per daemon kind (C(CephReleases) in the croit API), each a list of release and daemon count.
  returned: when V(releases) is gathered
  type: dict
  sample:
    mon:
      - release: squid
        count: 3
    osd:
      - release: squid
        count: 24
    overall:
      - release: squid
        count: 32
license:
  description: The croit licence and what the cluster uses of it (C(LicenseReply) in the croit API).
  returned: when V(license) is gathered
  type: dict
  contains:
    active:
      description: Whether the licence is active.
      returned: always
      type: bool
      sample: true
    registered:
      description: Whether the cluster is registered with the croit portal.
      returned: always
      type: bool
      sample: true
    message:
      description: Details about the licence, such as why it is invalid.
      returned: always
      type: str
      sample: License is valid
    usageFormatted:
      description: Current usage against the licence limits, as text.
      returned: always
      type: str
      sample: 412 TiB of 500 TiB
    license:
      description: The licence itself, including C(validUntil) and C(licenseRestrictions).
      returned: always
      type: dict
      sample:
        licenseId: L-0001
        validUntil: 1798761600
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

SOURCES = dict(
    backend="/status",
    version="/status/croit-version",
    status="/cluster/status",
    releases="/cluster/releases",
    license="/license",
)


def main():
    choices = list(SOURCES)
    m = CroitModule(
        dict(gather=dict(type="list", elements="str", choices=choices, default=choices)),
        wait=False,
        warnings=False,
    )
    result = dict((key, m.get(SOURCES[key])) for key in m.params["gather"])
    m.exit(changed=False, **result)


if __name__ == "__main__":
    main()
