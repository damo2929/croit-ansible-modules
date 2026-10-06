# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type


class ModuleDocFragment(object):

    # Connection options shared by every module.
    DOCUMENTATION = r"""
options:
  api_url:
    description:
      - Base URL of the croit API on the management node, including the C(/api) path.
      - If not set, the value of the E(CROIT_API_URL) environment variable is used.
    type: str
    required: true
  api_token:
    description:
      - croit API token, sent as a bearer token in the C(Authorization) header.
      - Create one in the croit UI or with C(POST /api-tokens). A token with the C(viewer) role is enough for
        read-only modules and check mode; changes need the C(admin) role.
      - If not set, the value of the E(CROIT_API_TOKEN) environment variable is used.
    type: str
    required: true
  validate_certs:
    description:
      - Whether to validate the TLS certificate of the croit management node.
    type: bool
    default: true
  timeout:
    description:
      - Timeout in seconds for each HTTP request.
    type: int
    default: 30
notes:
  - The modules run on the Ansible controller and talk to croit over HTTPS. Run the play against
    C(localhost), or delegate the tasks to it.
  - Use O(api_url) and O(api_token) with C(module_defaults) and the C(group/croit.ceph.all) action group
    to set them once per play.
requirements:
  - Python >= 3.9 (no third-party Python libraries are needed).
"""

    # Waiting for croit background tasks.
    WAIT = r"""
options:
  wait:
    description:
      - Wait for the croit background task a change starts, and fail if the task fails.
      - With V(false) the module returns as soon as croit accepted the change, with the task in RV(task);
        a later run reports the final state.
    type: bool
    default: true
  wait_timeout:
    description:
      - How many seconds to wait for a croit background task to end.
    type: int
    default: 600
"""

    # croit ignorable warnings.
    WARNINGS = r"""
options:
  ignore_warnings:
    description:
      - croit refuses some risky changes with a warning that must be confirmed.
      - With V(false) the module fails and shows the warning text. With V(true) the warning is confirmed
        and the change is applied.
      - Warnings are never confirmed in check mode.
    type: bool
    default: false
"""

    # Standard attributes; modules set the support level.
    ATTRIBUTES = r"""
attributes:
  check_mode:
    description: Can run in check mode and return changed status prediction without modifying target.
  diff_mode:
    description: Will return details on what has changed (or possibly needs changing in check mode), when in diff mode.
"""
