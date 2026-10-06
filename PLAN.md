# croit Ansible Collection: Implementation Plan

**Status:** All phases (0–4) implemented (2026-10-06, 82 modules) and waiting for review. Nothing has run against a live croit cluster yet.
**Design:** see [DESIGN.md](DESIGN.md) for the architecture, the shared behaviour and the idempotency/check-mode contract. This file only tracks scope, phases and open questions.
**Prior art:** Ansible Galaxy has no collection for croit, so this one starts from scratch.

---

## 1. Module inventory (phased)

Each phase can ship on its own. The ✱ marks the resources I'd treat as top priority.

### Phase 0: Foundation ✅ (implemented 2026-10-06, waiting for review)
- [x] `module_utils`: `client.py` (bearer token, errors, ignorable-warning loop, list unwrapping), `tasks.py` (wait, judge, questions), `module.py` (`CroitModule` base, check-mode guard, size parsing, diff helpers).
- [x] Doc fragments `croit.ceph.croit` with `.wait`, `.warnings` and `.attributes`.
- [x] **Galaxy readiness:** `galaxy.yml`, `meta/runtime.yml`, `COPYING` and `LICENSES/`, `changelogs/`, `.ansible-lint`, `tests/config.yml`, and CI and release workflows. galaxy-importer passes.
- [x] `croit.ceph.api`: the generic request module.
- [x] `croit.ceph.task_info` and `croit.ceph.task` (wait, cancel, answer).
- [x] `croit.ceph.cluster_info`.
- [x] `croit.ceph.pool`: the reference module, with the full idempotency/check-mode test sequence.
- [x] `tools/check_spec_drift.py`, plus `docs/openapi.json` vendored.
- [ ] Run the integration targets (`pool`, `cluster_info`) against a lab croit cluster. They are written but have **not been run**, because there's no lab access yet.
- [x] Pushed to https://github.com/damo2929/croit-ansible-modules (2026-10-06).

### Phase 1: Core storage objects ✅ (implemented 2026-10-06, waiting for review)

All 19 modules below are implemented, with unit tests (the full idempotency sequence for each resource module) and integration targets. The integration targets **have not been run**. Notes:
- Cloning lives in `rbd` (`clone_from`), not in `rbd_snapshot`, because the result is an image.
- `rbd_namespace` and `s3_user` need no `confirm_delete`: croit refuses to delete a non-empty namespace, or a user who still owns buckets (the module checks this up front).
- `s3_bucket` deletion needs `confirm_delete`, plus `purge_objects` when the bucket holds objects.

| Module | Endpoints | Key |
|---|---|---|
| ✅ `pool_info` (`pool` is done in Phase 0) | `/pools`, `/pools/{name}/details` | name |
| ✱ `pool_qos` | `/pools/{pool}/qos` | pool |
| ✱ `rbd` / `rbd_info` | `/pools/{pool}/rbds[/{rbd}]` (create, resize, rename, features) | pool/namespace/name |
| `rbd_namespace` | `/pools/{pool}/rbd-namespaces/{ns}` | pool/name |
| `rbd_snapshot` | `/pools/{pool}/rbds/{rbd}/snapshots/{snap}` (+ protect and clone) | pool/rbd/name |
| ✱ `ceph_key` / `ceph_key_info` | `/keys`, `/keys/{user}`, `/keys/{user}/download` | entity |
| ✱ `cephfs_volume` | `/cephfs/volumes/{name}` | name |
| `cephfs_subvolume_group`, `cephfs_subvolume` | `/cephfs/subvolume-groups/*`, `/cephfs/subvolumes/*` (+ resize) | volume/group/name |
| `cephfs_quota` | `/cephfs/quota`, `/cephfs/layout` | path |
| ✱ `s3_user` / `s3_user_info` | `/s3/users[/{uid}]`, plus quota and bucket-quota | uid |
| `s3_user_key`, `s3_subuser` | `/s3/users/{uid}/keys/*`, `/subusers/*` | uid/access key |
| ✱ `s3_bucket` / `s3_bucket_info` | `/s3/buckets/{name}` (owner, versioning, ACL), `/quota`, `/policy` | name |
| `snapshot_schedule` | `/snapshot-schedule/{cephfs,rbd}` | type/path or image + schedule |

### Phase 2: Cluster configuration and access ✅ (implemented 2026-10-06, waiting for review)

All modules below are implemented with unit tests and integration targets (**not run**). Notes:
- `ceph_config` keys options by name + `section` + `mask`. `use_default: croit|ceph` pins an option to a default.
- `api_token` returns the secret only on the run that creates it, unmasked. Users should set `no_log: true` on that task.
- `user` and `api_token` refuse to lock out the identity the playbook runs as (via `/auth/token-info`).
- `network` deletion needs no `confirm_delete`, because croit documents that nodes keep their addresses.

| Module | Endpoints |
|---|---|
| ✱ `ceph_config` / `ceph_config_info` | `/config` (set/unset an option, with section and mask) |
| ✱ `setting` / `setting_info` | `/settings` (croit settings) |
| `config_template` | `/config-templates/templates/{template}` |
| ✱ `user` | `/users`, `/users/{id}`, `/users/{id}/password` (local croit users) |
| `api_token` | `/api-tokens` (the secret is returned on create only) |
| `oidc_provider` | `/auth/oidc` |
| `network` / `network_info` | `/networks` (natural key: CIDR or name) |
| `hook_script` | `/events/hook-scripts`, `/events/scripts/{id}` |
| `server_ssh_keys` | `/server-access/keys` (replaces the whole list, so `exclusive` semantics) |
| `crush_rule` / `crush_info` | `/crush/rules/simple`, `/crush/rules/ssd-primary`, `/crush/rules/{name}`, `/crush/ec-profiles` |
| `mgr_module` | `/modules/{name}` enable/disable plus options, and the balancer |
| `osd_flag` | `/maintenance/flags/{flag}/set` and `/unset` (e.g. `noout` around maintenance) |
| `cluster_tuning` | recovery-speed, osd-full-ratios, min-compat-client, scheduling-timezone |
| `config_backup` | `/maintenance/config-backups` and `/s3` (enable, configure, run now) |

### Phase 3: Servers, disks and services ✅ (implemented 2026-10-06, waiting for review)

All modules below are implemented with unit tests and integration targets (**not run**). Integration targets that would change real hardware are opt-in. Notes:
- **Safety flags:**
  - `confirm_wipe` for OSD creation and replacement;
  - `confirm_action` for reboot, shutdown, IPMI power off, power cycle and reboot-to-BIOS;
  - `confirm_delete` for servers, NICs, bonds, VLANs, MONs and MDSs.
  `allow_management_ip_change` guards changing or deleting the interface that carries a node's management IP.
- `server` can't create servers: nodes register themselves when they PXE boot.
- `service` covers MON, MDS and rbd-mirror. RGW and gateway services belong to Phase 4.
- **Extra module:** `image_config` (cluster-wide image architectures, registry and Ceph build) was added next to `image`, because these settings aren't per image.

| Module | Endpoints |
|---|---|
| ✱ `server` / `server_info` | `/servers`, `/servers/{id}` (hostname, image, notes), reboot, shutdown, redetect |
| `server_nic`, `server_bond`, `server_vlan` | `/servers/{id}/nics/*` |
| ✱ `osd` | `/disks/create-osds`, `/disks/replace-osds`, `/crush/osd/{id}/in` and `/out` |
| `disk_info` | `/disks`, `/servers/{id}/disks` |
| ✱ `service` / `service_info` | `/services` (start/stop/restart/rolling-restart, delete), add mon, mds or rbd-mirror per server |
| `ha_group` | `/servers/ha-groups` |
| `image` | `/images` (download, set default, registry, archs) |
| `ipmi` | `/ipmi` (power on/off/cycle, identify) |
| `rbd_mirror` | `/pools/{pool}/rbd-mirror` (mode, peers, bootstrap token, schedules) |

### Phase 4: Gateways ✅ (implemented 2026-10-06, waiting for review)

All modules below are implemented, with unit tests and integration targets (**not run**; changes are opt-in). Additions and changes compared with the original list:
- **Added:**
  - `rgw_service`: split from `rgw_bootstrap`, because a multisite secondary gets gateways without a bootstrap;
  - `nfs_info`, `smb_info`, `iscsi_info`, `nvmeof_info`;
  - `cephfs_guard_webhook` and `cephfs_guard_info`.
- **Out of scope:** cephfs-guard incident triage (operator task; incidents are readable through `cephfs_guard_info`).
- **Naming:** the iSCSI gateway has no name, because Ceph allows one per cluster.
- **Safety:**
  - `confirm_action` is needed for multisite convert, join and promote, the NFS implementation switch, the SMB DNS-name change and SMB generation migration.
  - `confirm_delete` is needed for deleting whole gateway clusters, NVMe-oF subsystems and disks, and S3 placement classes.
  - Deleting the RBD image behind an iSCSI or NVMe-oF disk needs `delete_image: true` as well.

| Module | Endpoints |
|---|---|
| `rgw_bootstrap`, `s3_placement`, `s3_multisite` | `/s3/bootstrap`, `/s3/placements/*`, `/s3/multisite/*` |
| `nfs_cluster`, `nfs_export` | `/services/nfs-gateways/*` |
| `smb_cluster`, `smb_share`, `smb_user`, `smb_group` | `/services/smb/*` |
| `iscsi_gateway`, `iscsi_client`, `iscsi_disk`, `iscsi_group` | `/services/iscsi/*` |
| `nvmeof_gateway`, `nvmeof_subsystem`, `nvmeof_disk`, `nvmeof_host`, `nvmeof_listener` | `/gateways/nvmeof/*` |
| `cephfs_guard` | `/services/cephfsguard/*` |

### Deliberately out of scope (reachable through `croit.ceph.api` if needed)
- `ai-assistant`, `survey`, `support`, `debug`, `stats`, `logs` and `audit`: these are interactive or observability endpoints, not configuration.
- CephFS file browser and S3 object operations (upload, download, copy, move, ACL per object). The existing tools (`ansible.builtin.copy` on a mount, `amazon.aws.s3_object`) already do this well.
- Initial setup, backup restore, key renewal, Ceph major-version migrations and CRUSH map editing through change requests. These are one-off, high-risk workflows. If they're wanted later, they'd be better served by **roles** with explicit confirmation than by idempotent modules.

## 2. Proposed order of work

1. Phase 0 plus `pool` as the reference module. I'd stop there to review the patterns with you before going further.
2. The rest of Phase 1.
3. Phases 2, 3 and 4, in an order you can reshuffle.

## 3. Open questions

1. ~~**Namespace and name.**~~ Decided: `croit.ceph`, published on Galaxy.
2. **Target versions.** Which croit release(s) and minimum version should we support? Is the API at `/api` stable enough to pin against, and does a live management node serve the spec, so we can check for drift against it?
3. ~~**Auth.**~~ Decided: API token only.
4. **Priorities.** Does the phase ordering match what customers actually automate? For example, should servers and OSD lifecycle come before S3 and CephFS?
5. **Test environment.** Is there a lab croit cluster, or a containerised croit mgmt instance, available for integration tests and CI?
6. **Licence.** GPL-3.0-or-later for the modules and BSD-2-Clause for `module_utils` is applied as the default. Please confirm it.
7. ~~**Repo.**~~ Decided: git, pushed to `git@github.com:damo2929/croit-ansible-modules.git` (branch `main`).
8. ~~**Docs.**~~ Decided: keep `DESIGN.md`, `README.md` and `AGENTS.md` maintained alongside the code.
9. **Galaxy namespace (human action).** Someone with croit authority needs to sign in to galaxy.ansible.com and claim the `croit` namespace (unregistered as of 2026-10-06), then add a `GALAXY_API_KEY` CI secret. Who should own it?
10. ~~**Repository URL.**~~ Decided: https://github.com/damo2929/croit-ansible-modules.
11. ~~**Author GitHub handle.**~~ Decided: `@damo2929`.
12. **Unverified API details** (they need a lab cluster): how the `pagination` query parameter is encoded (the client never sends it today, it only handles both response shapes), and the exact `/pools` field values a real cluster returns (for example `description` when unset), which `croit.ceph.pool` normalises.
13. **Unverified Phase 1 API assumptions** (all need a lab cluster; each module's docs and the unit-test fakes encode the assumption):
    - **ceph_key:** a PATCH that leaves out a daemon type removes that daemon's caps. Missing caps come back as null or empty `rawPermissions`. The `/keys/{user}/download` answer carries `fileContents`.
    - **rbd:** `/rbds/rbd-names` is current straight after a create. The `/rbds/rbd-infos` `image` parameter is repeated, and its answer is keyed by `pool/[namespace/]image`. A missing image gives 404.
    - **CephFS:**
      - `mode` comes back as the full `st_mode`.
      - uid, gid and mode are treated as create-only.
      - A `snapshot-retained` subvolume is listed and counts as absent.
      - An unset quota may be null or 0.
    - **S3:**
      - Bucket purge reuses the pool confirmation sentence.
      - `PUT /s3/users/{uid}/keys/{accessKey}` also creates a key.
      - List endpoints may return placeholder rows that croit hasn't read yet.
      - A missing bucket gives 404.
      - A user created with `tenant` gets the uid `tenant$uid`.
14. **Unverified Phase 2/3 API assumptions** (they need a lab cluster). Each is encoded in the module docs and the unit-test fakes:
    - **ceph_config / setting / config_template:**
      - an unconfigured option shows in `/config/available` with every flag false;
      - `PUT /settings` takes typed JSON values;
      - `currentTemplateName` differs from every predefined name when the content is custom;
      - `min-compat-client` answers empty or null when unset.
    - **Access:**
      - `/auth/token-info.username` is the token name for API-token sessions (the lockout guard depends on this);
      - PATCH `roles` replaces the roles;
      - `GET /auth/oidc` returns `clientSecret`.
    - **Network / hooks / backups:**
      - unpaginated `GET /events/hook-scripts` returns every script;
      - the network PUT accepts the stored `ip`;
      - null fields in the S3 backup PUT clear them.
    - **CRUSH / mgr:**
      - the step format of class-pinned takes;
      - `GET /modules` `enabled` reflects whether the balancer is active.
    - **Servers:**
      - NIC and VLAN `ip` include the prefix;
      - `image: default` compares literally;
      - bonds are listed as NICs with `type: bond`.
    - **OSD / services:**
      - OSDs aren't in `GET /services`;
      - a multi-server gateway is one row;
      - `DELETE /services/{id}?server=` removes only that node;
      - CRUSH `reweight` 0 means out.
    - **Platform:**
      - `HaGroupServer.vlan` is croit's VLAN record id;
      - `/ipmi/poll-state` is keyed by id;
      - the IPMI initialize call takes no body;
      - a mirror peer's `siteName` is the label given at import.
15. **Unverified Phase 4 API assumptions** (they need a lab cluster). Each is encoded in the module docs and the test fakes:
    - **Lists:** paginated-only list endpoints (`/gateways/*`, SMB users/groups, hook scripts) return every row when no `pagination` parameter is sent.
    - **Names:** NFS, SMB and HA "names" are croit's `description`.
    - **VLAN ids:** `vlanId` in HA, NFS, cephfs-guard and NVMe-oF requests is croit's VLAN record id, not the tag. SMB members use the tag.
    - **RGW:** gateways are `GET /services` rows of type `radosgw`; `rgw-config` returns null for inherited values.
    - **Multisite:** the primary token is a bare JSON string.
    - **iSCSI:** `DELETE .../disks/{wwn}` without `deleteData` keeps the image.
    - **NVMe-oF:** the disk DELETE accepts a JSON body; a target service's ANA state is set by a follow-up PATCH.
    - **Secret masking:** CHAP passwords and NVMe-oF host keys read `(masked)` for non-admin tokens.
