# croit.ceph — Ansible Collection for croit

[![CI](https://github.com/damo2929/croit-ansible-modules/actions/workflows/ci.yml/badge.svg)](https://github.com/damo2929/croit-ansible-modules/actions/workflows/ci.yml)
[![License: GPL v3+](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](COPYING)

Manage [croit](https://www.croit.io/) Ceph clusters with Ansible. The collection drives the [croit REST API](https://www.croit.io/api-docs), turning pools, RBD images, CephFS, S3, Ceph configuration, servers, OSDs, services and the NFS / SMB / iSCSI / NVMe-oF gateways into declarative, idempotent tasks.

> **Status: pre-alpha (0.1.0, unreleased).** All 82 modules are implemented, and they are unit-tested against fake croit APIs built from the published spec. They have **not yet been run against a live croit cluster**, so test on a lab cluster first. The architecture is in [DESIGN.md](DESIGN.md) and the roadmap is in [PLAN.md](PLAN.md).

## Contents

- [Description](#description)
- [Requirements](#requirements)
- [Installation](#installation)
- [Authentication](#authentication)
- [Use cases and examples](#use-cases-and-examples)
- [Idempotency, check mode and safety](#idempotency-check-mode-and-safety)
- [Included content](#included-content)
- [Documentation](#documentation)
- [Testing](#testing)
- [Contributing](#contributing)
- [Support](#support)
- [Release notes and roadmap](#release-notes-and-roadmap)
- [Related information](#related-information)
- [License](#license)

## Description

`croit.ceph` gives Ceph operators who run [croit](https://www.croit.io/) one Ansible interface for both day-1 and day-2 work:

- **Storage objects:**
  - pools and their QoS;
  - RBD images, namespaces, snapshots and mirroring;
  - CephFS volumes, subvolumes and quotas;
  - S3 users, keys, buckets, placement and multisite.
- **Cluster configuration:**
  - Ceph options and croit settings;
  - CRUSH rules, mgr modules and OSD flags;
  - networks, hook scripts and backups;
  - croit users, API tokens and OIDC.
- **Hardware lifecycle:**
  - servers, NICs, bonds and VLANs;
  - disks and OSDs;
  - Ceph services, HA groups, OS images and IPMI.
- **Gateways:** RGW, NFS, cephfs-guard, SMB (simple and Active Directory), iSCSI and NVMe-oF.

What the modules have in common:

- **Idempotent.** Every module reads the current state, compares it with what you asked for, and only writes the differences. A second run reports `changed=false`.
- **Check and diff mode.** `--check` only ever *reads* from croit; a write in check mode is a bug that the modules refuse at runtime. `--diff` shows the managed fields before and after.
- **Partial specification.** Options you leave out are left alone. Lists are only replaced in full where you ask for it (`exclusive: true`).
- **Safe by default.** Anything that destroys data, takes nodes down or makes a one-way change needs an explicit `confirm_*` flag, even in check mode. croit's own "are you sure?" warnings are never confirmed unless you set `ignore_warnings: true`.
- **Async aware.** Long-running croit tasks are waited for (`wait`, `wait_timeout`), and a failed task fails the Ansible task with croit's output.
- **Natural keys.** You name things the way you think of them (pool names, hostnames, NIC names, CIDRs, IQNs, NQNs); the modules look up croit's numeric ids for you.

## Requirements

| Component | Version |
|---|---|
| ansible-core | ≥ 2.14 (the version EL9 AppStream ships; tested up to 2.20) |
| Python on the controller | ≥ 3.9 (EL9's system Python) |
| Python libraries | none: the collection only uses the standard library and ansible-core |
| croit | a croit management node reachable over HTTPS from the controller; the minimum supported croit release is still to be decided (see [PLAN.md](PLAN.md)) |

On EL9 (RHEL, Rocky, Alma), `dnf install ansible-core` is all you need; no `pip` is involved.

## Installation

The collection is **not yet on Ansible Galaxy**. Once it is published:

```bash
ansible-galaxy collection install croit.ceph
```

Or pin it in a `requirements.yml`:

```yaml
---
collections:
  - name: croit.ceph
    version: ">=0.1.0"
```

```bash
ansible-galaxy collection install -r requirements.yml
```

Until then, install it straight from git:

```bash
ansible-galaxy collection install git+https://github.com/damo2929/croit-ansible-modules.git,main
```

Or build it from a checkout:

```bash
git clone https://github.com/damo2929/croit-ansible-modules.git
cd croit-ansible-modules
ansible-galaxy collection build
ansible-galaxy collection install croit-ceph-*.tar.gz
```

## Authentication

The collection authenticates with a **croit API token** only, sent as `Authorization: Bearer <token>`. Create one in the croit UI under API tokens, or with `croit.ceph.api_token` from an existing admin token.

| Token role | Enough for |
|---|---|
| `viewer` | every `*_info` module, and `--check` runs of any module |
| `admin` + `viewer` | making changes |

Connection options, which can also come from environment variables:

| Option | Environment variable | Default |
|---|---|---|
| `api_url` | `CROIT_API_URL` (e.g. `https://croit-mgmt/api`) | required |
| `api_token` | `CROIT_API_TOKEN` | required |
| `validate_certs` | none | `true` |
| `timeout` | none | `30` seconds per request |

The modules run **on the Ansible controller** and talk to croit over HTTPS. Run plays against `localhost`, and set the connection once per play with the `croit.ceph.all` action group:

```yaml
- name: Manage croit
  hosts: localhost
  gather_facts: false
  module_defaults:
    group/croit.ceph.all:
      api_url: https://croit-mgmt/api
      api_token: "{{ vault_croit_token }}"   # keep the token in Ansible Vault
  tasks:
    - name: Show the croit version
      croit.ceph.cluster_info:
        gather: [version]
      register: cluster

    - name: Print it
      ansible.builtin.debug:
        msg: "croit {{ cluster.version }}"
```

All examples below assume this `module_defaults` block.

## Use cases and examples

### 1. Check cluster health before changing anything

```yaml
- name: Read the cluster status
  croit.ceph.cluster_info:
    gather: [status, version]
  register: cluster

- name: Refuse to continue unless Ceph is healthy
  ansible.builtin.assert:
    that:
      - (cluster.status.cephStatus | default({}, true)).health.status | default('') == 'HEALTH_OK'
    fail_msg: "Ceph is not HEALTH_OK; fix the cluster first"
```

### 2. Block storage for a virtualisation platform

```yaml
- name: Replicated pool for VM disks
  croit.ceph.pool:
    name: rbd-vms
    application: rbd
    size: 3
    min_size: 2
    crush_rule: replicated_rule
    quota_max_bytes: 20T
    description: VM disks for the hypervisor cluster

- name: Namespace per tenant
  croit.ceph.rbd_namespace:
    pool: rbd-vms
    name: tenant-a

- name: A VM disk
  croit.ceph.rbd:
    pool: rbd-vms
    namespace: tenant-a
    name: web-01-root
    size: 100G
    features: [layering, exclusive_lock, object_map, fast_diff, deep_flatten]

- name: Hourly snapshots of that disk, keep 24
  croit.ceph.snapshot_schedule:
    type: rbd
    snapshot_prefix: hourly
    cron: "0 * * * *"
    max_snapshots: 24
    rbd_paths:
      - pool: rbd-vms
        namespace: tenant-a
        image: web-01-root

- name: Ceph client key for the hypervisors
  croit.ceph.ceph_key:
    name: client.hypervisors
    caps:
      mon: profile rbd
      osd: profile rbd pool=rbd-vms
      mgr: profile rbd pool=rbd-vms
    comment: Proxmox / libvirt hosts
    return_keyring: true
  register: hv_key
  no_log: true          # the keyring is a secret

- name: Install the keyring on the hypervisors
  ansible.builtin.copy:
    content: "{{ hv_key.keyring.contents }}"
    dest: /etc/ceph/ceph.client.hypervisors.keyring
    mode: "0600"
  delegate_to: "{{ item }}"
  loop: "{{ groups['hypervisors'] }}"
  no_log: true
```

Growing a disk later is a one-line change. `size` only ever grows; shrinking is refused:

```yaml
- name: Grow the disk
  croit.ceph.rbd:
    pool: rbd-vms
    namespace: tenant-a
    name: web-01-root
    size: 200G
```

### 3. A CephFS share for a team

```yaml
- name: Subvolume with a 2 TiB quota
  croit.ceph.cephfs_subvolume:
    volume: cephfs
    group: teams
    name: data-science
    size: 2T
    mode: "0770"
    uid: 3000
    gid: 3000

- name: Limit the number of files in a scratch directory
  croit.ceph.cephfs_quota:
    volume: cephfs
    path: /scratch
    max_bytes: 500G
    max_files: 1000000

- name: Export it over NFS to the office network
  croit.ceph.nfs_export:
    cluster: nfs-office
    nfs_path: /data-science
    path: /volumes/teams/data-science
    access:
      - subnet: 10.20.0.0/16
        rw: true
```

### 4. Onboard an S3 tenant

```yaml
- name: S3 user with quotas
  croit.ceph.s3_user:
    uid: acme
    display_name: ACME Corp
    email: storage@acme.example
    user_quota:
      enabled: true
      max_size: 10T
    bucket_quota:
      enabled: true
      max_objects: 5000000

- name: Access key (secret comes from Vault)
  croit.ceph.s3_user_key:
    uid: acme
    access_key: ACMEACCESSKEY0001
    secret_key: "{{ vault_acme_s3_secret }}"
  no_log: true

- name: Versioned bucket with a read-only policy for a partner
  croit.ceph.s3_bucket:
    name: acme-backups
    owner: acme
    versioning: enabled
    quota:
      enabled: true
      max_size: 5T
    policy:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Principal: {AWS: ["arn:aws:iam:::user/partner"]}
          Action: ["s3:GetObject", "s3:ListBucket"]
          Resource: ["arn:aws:s3:::acme-backups", "arn:aws:s3:::acme-backups/*"]
```

### 5. Rotate an S3 key without downtime

```yaml
- name: Add the new key first
  croit.ceph.s3_user_key:
    uid: acme
    access_key: ACMEACCESSKEY0002
    secret_key: "{{ vault_acme_s3_secret_v2 }}"
  no_log: true

# ... roll the new key out to the applications ...

- name: Then make it the only key
  croit.ceph.s3_user_key:
    uid: acme
    access_key: ACMEACCESSKEY0002
    secret_key: "{{ vault_acme_s3_secret_v2 }}"
    exclusive: true       # removes every other key of this user
  no_log: true
```

### 6. Ceph configuration as code

```yaml
- name: OSD memory target
  croit.ceph.ceph_config:
    name: osd_memory_target
    section: osd
    value: 8G

- name: Different value for one host
  croit.ceph.ceph_config:
    name: osd_memory_target
    section: osd
    mask: host:storage-07
    value: 4G

- name: Put an option back on Ceph's default
  croit.ceph.ceph_config:
    name: osd_max_backfills
    state: absent

- name: Turn on the balancer
  croit.ceph.mgr_module:
    name: balancer
    enabled: true
```

### 7. Rolling maintenance of a storage node

```yaml
- name: Keep data where it is while nodes reboot
  croit.ceph.osd_flag:
    flags: [noout]
    state: present

- name: Reboot the node
  croit.ceph.server:
    server: storage-03
    action: reboot
    confirm_action: true    # takes a storage node down; required

- name: Wait for Ceph to recover
  croit.ceph.cluster_info:
    gather: [status]
  register: cluster
  until: (cluster.status.cephStatus | default({}, true)).health.status | default('') == 'HEALTH_OK'
  retries: 60
  delay: 30

- name: Back to normal
  croit.ceph.osd_flag:
    flags: [noout]
    state: absent
```

### 8. Long-running work: start now, wait later

```yaml
- name: Create a large EC pool without blocking the play
  croit.ceph.pool:
    name: archive
    application: rgw
    erasure_coding: true
    data_chunks: 8
    parity_chunks: 3
    device_class: hdd
    wait: false
  register: created

# ... other tasks ...

- name: Wait for croit to finish
  croit.ceph.task:
    task_id: "{{ created.task.id }}"
    wait_timeout: 3600
  when: created.task is defined
```

### 9. Access management

```yaml
- name: Read-only croit account for the monitoring team
  croit.ceph.user:
    username: monitoring
    password: "{{ vault_monitoring_password }}"
    roles: [viewer]
    update_password: on_create

- name: API token for a CI pipeline
  croit.ceph.api_token:
    name: ci-pipeline
    roles: [admin, viewer]
  register: ci_token
  no_log: true            # the secret is returned once, on creation

- name: Store it
  ansible.builtin.copy:
    content: "{{ ci_token.token }}"
    dest: /etc/ci/croit-token
    mode: "0600"
  when: ci_token.token is defined
  no_log: true
```

### Dry runs

Every example above can be previewed safely:

```bash
ansible-playbook site.yml --check --diff
```

In check mode the modules only read from croit. They report exactly what a real run would change, and show the before and after values of the managed fields.

## Idempotency, check mode and safety

| Flag | Needed for | Modules |
|---|---|---|
| `confirm_delete` | deleting anything that destroys data or disconnects every client | `pool`, `rbd`, `rbd_snapshot`, `cephfs_volume`, `cephfs_subvolume_group`, `cephfs_subvolume`, `s3_bucket`, `s3_placement`, `server`, `server_nic`, `server_bond`, `server_vlan`, `service` (MON/MDS), `nfs_cluster`, `smb_cluster`, `iscsi_gateway`, `iscsi_disk`, `nvmeof_gateway`, `nvmeof_subsystem`, `nvmeof_disk` |
| `confirm_wipe` | creating or replacing an OSD (erases the disk) | `osd` |
| `confirm_action` | node reboot or shutdown, IPMI power off / cycle / BIOS, one-way or disruptive cluster changes | `server`, `ipmi`, `s3_multisite`, `nfs_cluster`, `smb_cluster` |
| `allow_management_ip_change` | changes that would cut a node off from croit | `server_nic`, `server_bond`, `server_vlan` |
| `delete_image` | also deleting the RBD image behind a gateway disk | `iscsi_disk`, `nvmeof_disk` |
| `purge_objects` | deleting a bucket that still holds objects | `s3_bucket` |
| `ignore_warnings` | confirming croit's own "are you sure?" warnings | every module that writes |

The flags are checked before anything is sent, in check mode too.

One-shot actions (restart, rolling restart, reboot, run a backup now, IPMI actions) always report `changed` and are skipped in check mode, like `ansible.builtin.service` with `state: restarted`.

Secrets (passwords, CHAP secrets, S3 secret keys, keyrings, bootstrap tokens) are marked `no_log`, never appear in diffs, and are only returned when you ask for them. Write-only secrets follow the `ansible.builtin.user` pattern (`update_password: on_create|always`).

## Included content

The collection has 82 modules. Every module supports check mode (`croit.ceph.api` only for GET requests), and every resource module supports diff mode. Full documentation for each one: `ansible-doc croit.ceph.<module>`.

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

## Documentation

- **Module reference:** run `ansible-doc croit.ceph.<module>`, or see the docsite once the collection is published on Galaxy.
- **Guides:** in [`docs/docsite/rst/`](docs/docsite/rst/):
  - [Getting started](docs/docsite/rst/guide_getting_started.rst)
  - [Idempotency, check mode and safety flags](docs/docsite/rst/guide_safety.rst)
  - [Background tasks and croit warnings](docs/docsite/rst/guide_tasks_and_warnings.rst)
  - [Handling secrets](docs/docsite/rst/guide_secrets.rst)
- **Architecture and contracts:** [DESIGN.md](DESIGN.md).

## Testing

The collection is tested with `ansible-test` on every push (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)):

- **Sanity and unit tests:** on ansible-core 2.14 (Python 3.9, the EL9 baseline) up to devel, plus a job in a Rocky Linux 9 container.
- **Unit tests:** run every module against stateful fake croit APIs. Each resource module goes through the full sequence: create, re-run, update, delete, each in check mode first. The tests assert that check mode never writes.
- **Lint:** `ansible-lint --profile production`, plus `antsibull-docs` and `antsibull-changelog` lint.
- **Galaxy:** `galaxy-importer` runs on the built tarball.
- **Integration targets:** in `tests/integration/targets/`, run against a **lab** croit cluster. They're opt-in, because they change real resources:

  ```bash
  cp tests/integration/integration_config.yml.template tests/integration/integration_config.yml
  # edit it: lab API URL and token, plus any opt-in variables
  ansible-test integration --allow-unsupported
  ```

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md); AGENTS.md is the rulebook for every change, by humans or AI agents. Every module must stay idempotent, support check mode, and come with unit tests and a changelog fragment.

## Support

- **Bugs and feature requests:** [GitHub issues](https://github.com/damo2929/croit-ansible-modules/issues).
- **Security issues:** see [SECURITY.md](SECURITY.md); don't open a public issue.
- **croit itself:** [croit support](https://www.croit.io/).

## Release notes and roadmap

- **Release notes:** [CHANGELOG.rst](CHANGELOG.rst), generated with antsibull-changelog at each release.
- **Roadmap and open questions:** [PLAN.md](PLAN.md).
- **Versioning:** [Semantic Versioning](https://semver.org/). Releases are published to Ansible Galaxy from tagged CI builds only.

## Related information

- [croit API reference](https://www.croit.io/api-docs)
- [croit documentation](https://www.croit.io/docs)
- [Ceph documentation](https://docs.ceph.com/en/latest/)
- [Using Ansible collections](https://docs.ansible.com/ansible/latest/collections_guide/index.html)

## License

GNU General Public License v3.0 or later (see [COPYING](COPYING)). `plugins/module_utils/` is under the BSD 2-Clause license (see [LICENSES/BSD-2-Clause.txt](LICENSES/BSD-2-Clause.txt)). Every file carries an SPDX header.
