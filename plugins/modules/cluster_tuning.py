#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /maintenance/recovery-speed
# croit-api: PUT /maintenance/recovery-speed
# croit-api: GET /maintenance/osd-full-ratios
# croit-api: PATCH /maintenance/osd-full-ratios
# croit-api: GET /maintenance/min-compat-client
# croit-api: PUT /maintenance/min-compat-client
# croit-api: GET /maintenance/scheduling-timezone
# croit-api: PATCH /maintenance/scheduling-timezone

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: cluster_tuning
short_description: Manage cluster-wide tuning on a croit cluster
version_added: 0.1.0
description:
  - Manages croit's cluster-wide knobs, each only when its option is set. The knobs are recovery speed, the OSD
    full ratios, the minimum client release and the timezone croit reads schedules in.
  - Options left out are neither read nor changed, and at least one option must be set.
  - Each knob is compared with what croit reports and only the knobs that differ are written, so re-running a
    task reports no change.
  - These knobs always exist, so the module has no C(state) option; set an option to change a knob.
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
    details:
      - The diff shows only the knobs whose option is set.
options:
  recovery_speed:
    description:
      - How hard the cluster works at recovery, on croit's scale from V(1) (gentlest) to V(10) (no throttle).
      - Each step down doubles how long OSDs sleep between recovery operations.
      - Values outside V(1) to V(10) fail before anything is changed.
    type: int
  full_ratios:
    description:
      - OSD fullness thresholds, as fractions of one OSD's capacity. Only the sub-options that are set are
        managed; the others keep their current value.
      - Ceph stores two decimal places, so values are compared rounded to two decimals.
      - The result must keep C(0 < nearfull < backfillfull < full <= 0.98). This is checked against the merged
        thresholds before anything is changed, in check mode too.
    type: dict
    suboptions:
      nearfull:
        description: Fraction of an OSD's capacity at which Ceph raises a near-full warning, for example V(0.85).
        type: float
      backfillfull:
        description: Fraction of an OSD's capacity at which Ceph stops backfilling onto that OSD, for example V(0.9).
        type: float
      full:
        description: Fraction of an OSD's capacity at which the cluster stops accepting writes, for example V(0.95).
        type: float
  min_compat_client:
    description:
      - Oldest Ceph release a client may run. Ceph refuses connections from older clients.
      - It cannot be set beyond the release the cluster runs, and raising it disconnects any older client that is
        still connected.
    type: str
    choices: [luminous, mimic, nautilus, octopus, pacific, quincy, reef, squid, tentacle]
  scheduling_timezone:
    description:
      - Timezone every croit cron schedule (snapshots, auto-update) is read in, for example V(Europe/Berlin).
      - Must be one of the timezones croit offers; an unknown one fails before anything is changed.
      - Changing it moves every existing schedule to the same wall-clock time in the new zone. croit warns
        about this, see O(ignore_warnings).
    type: str
notes:
  - Raising O(min_compat_client) disconnects older clients, for example old kernel CephFS or RBD mounts.
seealso:
  - module: croit.ceph.osd_flag
    description: Set cluster-wide OSD flags such as C(noout) around maintenance.
  - module: croit.ceph.ceph_config
    description: Tune individual Ceph options.
  - module: croit.ceph.snapshot_schedule
    description: The schedules O(scheduling_timezone) applies to.
  - name: croit API reference
    description: The C(/maintenance) endpoints this module uses.
    link: https://www.croit.io/api-docs
  - name: Ceph storage capacity
    description: What the nearfull, backfillfull and full ratios mean.
    link: https://docs.ceph.com/en/latest/rados/configuration/mon-config-ref/#storage-capacity
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).
- name: Throttle recovery during business hours
  croit.ceph.cluster_tuning:
    recovery_speed: 3

- name: Warn earlier about full OSDs and require modern clients
  croit.ceph.cluster_tuning:
    full_ratios:
      nearfull: 0.8
    min_compat_client: reef
  register: tuning

- name: Show the full ratios now in force
  ansible.builtin.debug:
    msg: "{{ tuning.tuning.full_ratios }}"

- name: Read schedules in Berlin time
  croit.ceph.cluster_tuning:
    scheduling_timezone: Europe/Berlin
    ignore_warnings: true
"""

RETURN = r"""
tuning:
  description:
    - The managed knobs as croit reports them after the change. In check mode, the knobs before the change.
    - Only the knobs whose option is set are returned.
  returned: always
  type: dict
  contains:
    recovery_speed:
      description: Recovery speed on croit's scale from 1 to 10.
      returned: when O(recovery_speed) is set
      type: int
      sample: 3
    full_ratios:
      description: All three fullness thresholds, rounded to two decimals.
      returned: when O(full_ratios) is set
      type: dict
      sample:
        nearfull: 0.8
        backfillfull: 0.9
        full: 0.95
    min_compat_client:
      description: The oldest client release the cluster accepts, in lower case; null when none is required.
      returned: when O(min_compat_client) is set
      type: str
      sample: reef
    scheduling_timezone:
      description: The timezone croit reads schedules in.
      returned: when O(scheduling_timezone) is set
      type: str
      sample: Europe/Berlin
"""

from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule

RATIOS = ("nearfull", "backfillfull", "full")
MAX_FULL = 0.98


def round2(value):
    return None if value is None else round(float(value), 2)


class ClusterTuningModule(CroitModule):
    def __init__(self):
        super(ClusterTuningModule, self).__init__(
            dict(
                recovery_speed=dict(type="int"),
                full_ratios=dict(
                    type="dict",
                    options=dict((r, dict(type="float")) for r in RATIOS),
                ),
                min_compat_client=dict(
                    type="str",
                    choices=["luminous", "mimic", "nautilus", "octopus", "pacific", "quincy", "reef", "squid", "tentacle"],
                ),
                scheduling_timezone=dict(type="str"),
            ),
            wait=False,
            required_one_of=[("recovery_speed", "full_ratios", "min_compat_client", "scheduling_timezone")],
        )

    # Reading --------------------------------------------------------------

    def read(self):
        """Current values of the knobs whose option is set, plus the timezone options."""
        p = self.params
        current = {}
        extra = {}
        if p["recovery_speed"] is not None:
            current["recovery_speed"] = (self.get("/maintenance/recovery-speed") or {}).get("speed")
        if p["full_ratios"] is not None:
            ratios = self.get("/maintenance/osd-full-ratios") or {}
            current["full_ratios"] = dict((r, round2(ratios.get(r))) for r in RATIOS)
        if p["min_compat_client"] is not None:
            release = self.get("/maintenance/min-compat-client")
            current["min_compat_client"] = release.lower() if isinstance(release, str) and release else None
        if p["scheduling_timezone"] is not None:
            tz = self.get("/maintenance/scheduling-timezone") or {}
            current["scheduling_timezone"] = tz.get("timezone")
            extra["timezones"] = tz.get("options") or []
        return current, extra

    # Validation -----------------------------------------------------------

    def validate(self, current, extra):
        p = self.params
        speed = p["recovery_speed"]
        if speed is not None and not 1 <= speed <= 10:
            self.module.fail_json(msg="recovery_speed must be between 1 and 10, got %s" % speed)
        if p["full_ratios"] is not None:
            merged = dict(current["full_ratios"])
            for r in RATIOS:
                if p["full_ratios"][r] is not None:
                    merged[r] = round2(p["full_ratios"][r])
            values = [merged[r] for r in RATIOS]
            if None not in values and not 0 < values[0] < values[1] < values[2] <= MAX_FULL:
                self.module.fail_json(
                    msg="full_ratios must keep 0 < nearfull < backfillfull < full <= %s; the result would be "
                    "nearfull=%s backfillfull=%s full=%s" % (MAX_FULL, values[0], values[1], values[2])
                )
        tz = p["scheduling_timezone"]
        if tz is not None and extra.get("timezones") and tz not in extra["timezones"]:
            self.module.fail_json(msg="croit does not offer the timezone %r" % tz)

    # Main -----------------------------------------------------------------

    def run(self):
        p = self.params
        current, extra = self.read()
        self.validate(current, extra)

        after = dict(current)
        writes = []
        if p["recovery_speed"] is not None and current["recovery_speed"] != p["recovery_speed"]:
            after["recovery_speed"] = p["recovery_speed"]
            writes.append(("PUT", "/maintenance/recovery-speed", dict(speed=p["recovery_speed"])))
        if p["full_ratios"] is not None:
            changes = dict(
                (r, round2(p["full_ratios"][r]))
                for r in RATIOS
                if p["full_ratios"][r] is not None and round2(p["full_ratios"][r]) != current["full_ratios"][r]
            )
            if changes:
                after["full_ratios"] = dict(current["full_ratios"], **changes)
                writes.append(("PATCH", "/maintenance/osd-full-ratios", changes))
        if p["min_compat_client"] is not None and current["min_compat_client"] != p["min_compat_client"]:
            after["min_compat_client"] = p["min_compat_client"]
            writes.append(("PUT", "/maintenance/min-compat-client", dict(release=p["min_compat_client"])))
        if p["scheduling_timezone"] is not None and current["scheduling_timezone"] != p["scheduling_timezone"]:
            after["scheduling_timezone"] = p["scheduling_timezone"]
            writes.append(("PATCH", "/maintenance/scheduling-timezone", dict(timezone=p["scheduling_timezone"])))

        if not writes:
            self.exit(changed=False, before=current, after=current, tuning=current)
        if self.check_mode:
            self.exit(changed=True, before=current, after=after, tuning=current)

        for method, path, body in writes:
            self.write(method, path, body=body)
        self.exit(changed=True, before=current, after=after, tuning=self.read()[0])


def main():
    ClusterTuningModule().run()


if __name__ == "__main__":
    main()
