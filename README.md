# croit.ceph — Ansible Collection for croit

> **Status: pre-alpha (0.1.0, unreleased).** All planned phases (0–4, 82 modules) are implemented and unit-tested, but they haven't been run against a live croit cluster yet. The architecture is in [DESIGN.md](DESIGN.md) and the roadmap is in [PLAN.md](PLAN.md).

This is an Ansible collection for managing [croit](https://www.croit.io/) Ceph clusters through the croit REST API ([API docs](https://www.croit.io/api-docs)). Pools, RBD images, CephFS, S3 users and buckets, Ceph config, servers, services and gateways become declarative, idempotent Ansible tasks.

## Highlights

- **Idempotent.** Every module reads the current state, compares it with what you asked for, and only writes the differences. A second run reports `changed=false`.
- **Check and diff mode on every module.** `--check` only ever reads from croit, and `--diff` shows before and after.
- **Async aware.** Long-running croit tasks are waited on (`wait`, `wait_timeout`), and a failed task fails the Ansible task with croit's output.
- **Safe by default.** croit's "ignorable warnings" are never confirmed unless you set `ignore_warnings: true`.
- **Runs on EL9 out of the box.** Python ≥ 3.9 and ansible-core ≥ 2.14, with no pip dependencies.

## Requirements

| Component | Version |
|---|---|
| ansible-core | ≥ 2.14 (EL9 AppStream) |
| Python (controller) | ≥ 3.9 |
| croit | _TBD_ (see PLAN.md) |
| Python libraries | none |

## Installation

_Not yet published._ Once it is released on [Ansible Galaxy](https://galaxy.ansible.com/ui/repo/published/croit/ceph/):

```bash
ansible-galaxy collection install croit.ceph
```

Until then, install it from a checkout:

```bash
ansible-galaxy collection build && ansible-galaxy collection install croit-ceph-*.tar.gz
```

## Authentication

The collection authenticates with a **croit API token** only. Create one in the croit UI, or `POST /api-tokens`.

- A token with the **viewer** role is enough for `*_info` modules and `--check` runs.
- Making changes needs a token with the **admin** role.

You can pass the connection settings as module options, or set them as environment variables:

| Option | Environment variable |
|---|---|
| `api_url` | `CROIT_API_URL` (e.g. `https://croit-mgmt/api`) |
| `api_token` | `CROIT_API_TOKEN` |
| `validate_certs` | — (default `true`) |

Keep the token in Ansible Vault.

## Usage

The modules run on the controller and talk to the croit management node over HTTPS.

```yaml
- hosts: localhost
  gather_facts: false
  module_defaults:
    group/croit.ceph.all:
      api_url: https://croit-mgmt/api
      api_token: "{{ vault_croit_token }}"
  tasks:
    - name: RBD pool
      croit.ceph.pool:
        name: rbd-ssd
        application: rbd
        size: 3
        min_size: 2

    - name: VM disk
      croit.ceph.rbd:
        pool: rbd-ssd
        name: vm-disk-01
        size: 100G
```

## Modules

The planned modules are listed in [PLAN.md](PLAN.md). This table will be updated as modules are implemented.

| Module | Description | Check mode | Diff | Status |
|---|---|---|---|---|
| **Cluster and tasks** | | | | |
| `croit.ceph.cluster_info` | croit backend status, version, cluster status, Ceph releases, licence | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.task_info` | List running croit background tasks, or read tasks by id | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.task` | Wait for, cancel or answer a croit background task | full | none | 0.1.0, unit-tested |
| `croit.ceph.api` | Raw request to any croit endpoint (**last resort**, writes are not idempotent) | GET only | none | 0.1.0, unit-tested |
| **Pools and RBD** | | | | |
| `croit.ceph.pool` | Ceph pools: replicated or erasure coded, quotas, compression, CRUSH rule by name | full | full | 0.1.0, unit-tested |
| `croit.ceph.pool_info` | Read pools, optionally with details and compression | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.pool_qos` | RBD QoS limits of a pool (`exclusive` to remove unlisted limits) | full | full | 0.1.0, unit-tested |
| `croit.ceph.rbd` | RBD images: create, grow, features, EC data pool, clone from a snapshot, flatten, per-image QoS | full | full | 0.1.0, unit-tested |
| `croit.ceph.rbd_info` | Read RBD images by pool, namespace or name | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.rbd_namespace` | RBD namespaces in a pool | full | full | 0.1.0, unit-tested |
| `croit.ceph.rbd_snapshot` | RBD snapshots and their protection | full | full | 0.1.0, unit-tested |
| **Ceph keys and snapshots** | | | | |
| `croit.ceph.ceph_key` | cephx users: caps (complete set), comment; keyring only on request | full | full | 0.1.0, unit-tested |
| `croit.ceph.ceph_key_info` | List cephx users; secrets only with `show_secrets` | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.snapshot_schedule` | Scheduled CephFS and RBD snapshots (cron, retention, paths) | full | full | 0.1.0, unit-tested |
| **CephFS** | | | | |
| `croit.ceph.cephfs_volume` | CephFS volumes (`max_mds`, standby-replay) | full | full | 0.1.0, unit-tested |
| `croit.ceph.cephfs_subvolume_group` | Subvolume groups: size, uid/gid/mode, pool layout | full | full | 0.1.0, unit-tested |
| `croit.ceph.cephfs_subvolume` | Subvolumes: size, uid/gid/mode, pool layout, namespace isolation | full | full | 0.1.0, unit-tested |
| `croit.ceph.cephfs_quota` | Byte/file quota and data layout of a CephFS directory | full | full | 0.1.0, unit-tested |
| **S3** | | | | |
| `croit.ceph.s3_user` | RGW users: name, email, placement, suspension, user and bucket quotas | full | full | 0.1.0, unit-tested |
| `croit.ceph.s3_user_info` | Read RGW users (never their keys), optionally with buckets | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.s3_subuser` | Subusers and their permissions | full | full | 0.1.0, unit-tested |
| `croit.ceph.s3_user_key` | One S3 key pair of a user or subuser; `exclusive` for rotation | full | full | 0.1.0, unit-tested |
| `croit.ceph.s3_bucket` | Buckets: owner, versioning, ACL, quota, policy | full | full | 0.1.0, unit-tested |
| `croit.ceph.s3_bucket_info` | Read buckets, optionally with ACL, versioning, CORS and policy | full | n/a | 0.1.0, unit-tested |
| **Cluster configuration and access** | | | | |
| `croit.ceph.ceph_config` | Set, pin to a default, or unset one Ceph option (section and mask aware) | full | full | 0.1.0, unit-tested |
| `croit.ceph.ceph_config_info` | Ceph options changed from default, or all documented options | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.setting` | A croit setting (typed), or reset it to default | full | full | 0.1.0, unit-tested |
| `croit.ceph.setting_info` | croit settings, stored or all | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.config_template` | A config file template: custom content or a predefined template | full | full | 0.1.0, unit-tested |
| `croit.ceph.cluster_tuning` | Recovery speed, full ratios, min compat client, scheduling timezone | full | full | 0.1.0, unit-tested |
| `croit.ceph.user` | Local croit users; roles as a set; `update_password`; lockout-protected | full | full | 0.1.0, unit-tested |
| `croit.ceph.api_token` | croit API tokens; the secret is returned **once**, on creation (use `no_log`) | full | full | 0.1.0, unit-tested |
| `croit.ceph.oidc_provider` | OIDC login providers | full | full | 0.1.0, unit-tested |
| `croit.ceph.server_ssh_keys` | SSH keys allowed on managed servers (`exclusive` for an exact list) | full | full | 0.1.0, unit-tested |
| `croit.ceph.network` | croit networks by CIDR: type, gateway, MTU, DHCP pool | full | full | 0.1.0, unit-tested |
| `croit.ceph.network_info` | Read networks | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.hook_script` | Hook scripts: content, hook points, target servers | full | full | 0.1.0, unit-tested |
| `croit.ceph.config_backup` | Cloud and S3 config backups; `run_now` action | full | full | 0.1.0, unit-tested |
| `croit.ceph.crush_rule` | Simple and SSD-primary CRUSH rules (no in-place edits; in-use rules protected) | full | full | 0.1.0, unit-tested |
| `croit.ceph.crush_info` | CRUSH rules, device classes, EC profiles, optionally the tree | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.mgr_module` | Enable/disable Ceph mgr modules (incl. balancer) and set their options | full | full | 0.1.0, unit-tested |
| `croit.ceph.osd_flag` | Cluster-wide OSD flags such as `noout` | full | full | 0.1.0, unit-tested |
| **Servers, disks and services** | | | | |
| `croit.ceph.server` | Server hostname, IP, image, notes, hugepages; reboot/shutdown/redetect actions (`confirm_action`) | full | full | 0.1.0, unit-tested |
| `croit.ceph.server_info` | Read servers, optionally with NICs | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.server_nic` | Interface IPs, notes, MAC (management-IP guard) | full | full | 0.1.0, unit-tested |
| `croit.ceph.server_bond` | Bonds: members, LACP/active-passive, primary | full | full | 0.1.0, unit-tested |
| `croit.ceph.server_vlan` | VLAN interfaces and their IPs | full | full | 0.1.0, unit-tested |
| `croit.ceph.disk_info` | Read disks, filter by server, role, device class | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.osd` | Create OSDs (`confirm_wipe`), replace, in/out, running | full | full | 0.1.0, unit-tested |
| `croit.ceph.service` | MON/MDS/rbd-mirror services: present/absent/started/stopped/restarted/rolling_restarted | full | full | 0.1.0, unit-tested |
| `croit.ceph.service_info` | Read services | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.ha_group` | HA groups: VIPs, members, HA Proxy, failover tuning | full | full | 0.1.0, unit-tested |
| `croit.ceph.image` | Download/remove OS images, set the default per architecture | full | full | 0.1.0, unit-tested |
| `croit.ceph.image_config` | Enabled architectures, image registry, Ceph build variant | full | full | 0.1.0, unit-tested |
| `croit.ceph.ipmi` | BMC registration, `power: on/off`, identify/power-cycle/BIOS actions (`confirm_action`) | full | full | 0.1.0, unit-tested |
| `croit.ceph.rbd_mirror` | Pool mirroring mode, site name, peers, schedules, per-image mirroring | full | full | 0.1.0, unit-tested |
| **Gateways** | | | | |
| `croit.ceph.rgw_bootstrap` | One-time S3 (RGW) bootstrap: realm, zonegroup, zone, first gateways | full | full | 0.1.0, unit-tested |
| `croit.ceph.rgw_service` | RGW gateways per server; ports, DNS name, zone; `exclusive` | full | full | 0.1.0, unit-tested |
| `croit.ceph.s3_placement` | Placement rules and storage classes; default placement | full | full | 0.1.0, unit-tested |
| `croit.ceph.s3_multisite` | Multisite role (standalone/primary/secondary; `confirm_action`), read-only flag, endpoints | full | full | 0.1.0, unit-tested |
| `croit.ceph.nfs_cluster` | NFS gateway clusters: servers, implementation (`confirm_action`), HA VIPs | full | full | 0.1.0, unit-tested |
| `croit.ceph.nfs_export` | NFS exports: path, access list, NFSv3/v4 | full | full | 0.1.0, unit-tested |
| `croit.ceph.nfs_info` | Read NFS clusters, exports, servers | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.cephfs_guard` | cephfs-guard ransomware protection per volume: detection, detectors, actions, instances | full | full | 0.1.0, unit-tested |
| `croit.ceph.cephfs_guard_webhook` | cephfs-guard alerting webhooks (URL treated as a secret) | full | full | 0.1.0, unit-tested |
| `croit.ceph.cephfs_guard_info` | Read cephfs-guard configs, instances, webhooks, incidents | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.smb_cluster` | SMB clusters (simple or AD): members, VIPs, parameters; DNS name and gen-2 migration (`confirm_action`) | full | full | 0.1.0, unit-tested |
| `croit.ceph.smb_share` | SMB shares: gen-2 ACL grants and options, gen-1 access lists | full | full | 0.1.0, unit-tested |
| `croit.ceph.smb_user` | Managed local SMB users: groups, `update_password` | full | full | 0.1.0, unit-tested |
| `croit.ceph.smb_group` | Managed local SMB groups | full | full | 0.1.0, unit-tested |
| `croit.ceph.smb_info` | Read SMB clusters, shares, users, groups, ACLs | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.iscsi_gateway` | The iSCSI gateway: portals, target IQN | full | full | 0.1.0, unit-tested |
| `croit.ceph.iscsi_disk` | Exported disks: grow, unexport; `delete_image` + `confirm_delete` to delete the RBD image | full | full | 0.1.0, unit-tested |
| `croit.ceph.iscsi_client` | Initiators: CHAP, group, mapped disks (`exclusive`) | full | full | 0.1.0, unit-tested |
| `croit.ceph.iscsi_group` | Host groups: members, disks (`exclusive`) | full | full | 0.1.0, unit-tested |
| `croit.ceph.iscsi_info` | Read the iSCSI gateway (CHAP masked unless `show_secrets`) | full | n/a | 0.1.0, unit-tested |
| `croit.ceph.nvmeof_gateway` | NVMe-oF clusters: target services, transports, ceph-cluster configs; `reconfigure` action | full | full | 0.1.0, unit-tested |
| `croit.ceph.nvmeof_subsystem` | Subsystems: ANA states, attached disks and hosts (`exclusive`) | full | full | 0.1.0, unit-tested |
| `croit.ceph.nvmeof_disk` | RBD images exported as NVMe-oF namespaces; grow; `delete_image` | full | full | 0.1.0, unit-tested |
| `croit.ceph.nvmeof_host` | Allowed host NQNs and DH-HMAC-CHAP keys | full | full | 0.1.0, unit-tested |
| `croit.ceph.nvmeof_listener` | Listeners (service, NIC, fabric, port, secure) | full | full | 0.1.0, unit-tested |
| `croit.ceph.nvmeof_info` | Read the NVMe-oF configuration (keys masked unless `show_secrets`) | full | n/a | 0.1.0, unit-tested |

All modules are unit-tested against a fake croit API built from the spec. None has been run against a live croit cluster yet.

Each module's full documentation is available with `ansible-doc croit.ceph.<module>`.

## Development

- Contributor and agent rules: [AGENTS.md](AGENTS.md)
- Design and contracts: [DESIGN.md](DESIGN.md)
- Check out the repo as `.../ansible_collections/croit/ceph`; `ansible-test` needs that path.
- Unit tests: `ansible-test units --venv --python 3.9` (or any Python version from 3.9 up).
- Sanity: `ansible-test sanity --venv --python 3.9`
- Lint: `ansible-lint --profile production`
- Integration (lab cluster only):
  1. Copy `tests/integration/integration_config.yml.template` to `integration_config.yml` and fill it in.
  2. Run `ansible-test integration --allow-unsupported`.
- API drift: `python tools/check_spec_drift.py [--refresh]`
- Galaxy check: `ansible-galaxy collection build && python -m galaxy_importer.main croit-ceph-*.tar.gz`

## Releases

The collection follows SemVer. Releases are published to Ansible Galaxy from tagged CI builds, and each one is listed in [CHANGELOG.rst](CHANGELOG.rst).

## License

GPL-3.0-or-later (see [COPYING](COPYING)), except `plugins/module_utils/`, which is BSD-2-Clause (see [LICENSES/BSD-2-Clause.txt](LICENSES/BSD-2-Clause.txt)). Each file carries an SPDX header.
