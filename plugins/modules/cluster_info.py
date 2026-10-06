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
  - Gathers the state of the croit backend and the Ceph cluster it manages.
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
      - V(releases) is the Ceph releases the daemons run.
      - V(license) is the croit licence and its usage.
    type: list
    elements: str
    choices: [backend, version, status, releases, license]
    default: [backend, version, status, releases, license]
"""

EXAMPLES = r"""
- name: Check the cluster before maintenance
  croit.ceph.cluster_info:
    gather: [status, version]
  register: cluster

- name: Show the croit version
  ansible.builtin.debug:
    msg: "{{ cluster.version }}"
"""

RETURN = r"""
backend:
  description: croit backend status (C(BackendStatus) in the croit API).
  returned: when V(backend) is gathered
  type: dict
version:
  description: The croit version string.
  returned: when V(version) is gathered
  type: str
  sample: v2508.1.squid
status:
  description: Cluster status (C(ClusterStatus) in the croit API).
  returned: when V(status) is gathered
  type: dict
releases:
  description: Ceph releases per daemon kind (C(CephReleases) in the croit API).
  returned: when V(releases) is gathered
  type: raw
license:
  description: The croit licence and what the cluster uses of it (C(LicenseReply) in the croit API).
  returned: when V(license) is gathered
  type: dict
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
