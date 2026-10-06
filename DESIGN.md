# croit Ansible Collection: Design

This is the authoritative design for the `croit.ceph` collection. Read it before you change any code, and keep it up to date in the same change whenever the design moves on. The roadmap and open questions are in [PLAN.md](PLAN.md).

**Source of truth for the API:** the OpenAPI 3.1 spec built into https://www.croit.io/api-docs (Scalar). It has 475 paths, 629 operations, 757 schemas and 42 tags, and its info block says `version: 1.0.0`. A snapshot will be vendored at `docs/openapi.json`.

## Decisions log

| Date | Decision |
|---|---|
| 2026-10-06 | Supported baseline is **EL9**: Python ≥ 3.9 and ansible-core ≥ 2.14, with no third-party Python dependencies. |
| 2026-10-06 | Every module is **fully idempotent and supports check mode** (see §3). |
| 2026-10-06 | **Auth is API token only** (Bearer). Username/password login is not supported. |
| 2026-10-06 | The collection is published to **Ansible Galaxy** as `croit.ceph`, and every release has to pass `galaxy-importer` first (see §5). |
| 2026-10-06 | Licence: modules, doc fragments and tests are **GPL-3.0-or-later**; `plugins/module_utils/` is **BSD-2-Clause**. This is the proposed default, applied in Phase 0 and still waiting on confirmation (PLAN.md §3). |
| 2026-10-06 | Check mode is enforced at runtime as well as by tests: `CroitModule.write()` raises `CheckModeViolation` if any non-GET request is attempted in check mode. |
| 2026-10-06 | Each module declares the endpoints it calls with `# croit-api: METHOD /path` comments. `tools/check_spec_drift.py` checks them against `docs/openapi.json`. |
| 2026-10-06 | Deleting a pool needs `confirm_delete: true`, mirroring croit's own confirmation sentence. Delete protection is lifted automatically. |
| 2026-10-06 | `requires_ansible: ">=2.14.0"` stays, even though ansible-lint and galaxy-importer warn that 2.14 is upstream-EOL. EL9 support takes priority, so `.ansible-lint` skips `meta-runtime[unsupported-version]`. |
| 2026-10-06 | Phase 1: QoS helpers live in `module_utils/qos.py` and RGW quota helpers (where -1 means no bound) in `module_utils/rgw.py`. `module.py` gains `parse_quota`/`parse_mode` (CephFS and pool semantics, where 0 means unlimited). |
| 2026-10-06 | `CroitModule.write(..., confirm_warnings=True)` confirms croit's warnings only for an action the user already confirmed explicitly (e.g. `cephfs_volume` with `confirm_delete=true`). |
| 2026-10-06 | The client never puts query strings in error messages, because some endpoints take secrets as query parameters (S3 `secretKey`). |
| 2026-10-06 | `confirm_delete` is required only where a delete destroys data that croit would otherwise delete: pool, rbd image, rbd snapshot, CephFS volume/group/subvolume, and S3 bucket (plus `purge_objects` when it holds objects). It isn't required where croit itself refuses to delete non-empty things (rbd namespace, S3 user with buckets). |
| 2026-10-06 | Info modules never return secrets unless asked (`ceph_key_info.show_secrets`, `ceph_key.return_keyring`). S3 secrets are never returned, and appear in diffs only as `********`. |
| 2026-10-06 | Phases 2/3: shared `module_utils/lookup.py` (`find_server`/`require_server`, `require_disk`, `find_nic`, `normalise_mac`) and `module_utils/crush.py` (CRUSH rule parsing). The client returns `text/plain` responses as text, never JSON-decoded. |
| 2026-10-06 | Hardware safety: `confirm_wipe` (OSD create/replace), `confirm_action` (reboot, shutdown, IPMI power off/cycle/BIOS), `confirm_delete` (servers, NICs, bonds, VLANs, MON/MDS), and `allow_management_ip_change` (anything that would cut a node off). Unset means refuse, in check mode too. |
| 2026-10-06 | Lockout protection: `user` and `api_token` never delete, or remove admin from, the identity the playbook authenticates as. |
| 2026-10-06 | One-shot actions (restart, rolling restart, reboot, redetect, run backup, IPMI actions) always report a change and are skipped in check mode, like `ansible.builtin.service: state=restarted`. |
| 2026-10-06 | Phase 4: gateway helpers live in `module_utils/iscsi.py`, `nvmeof.py` and `smb.py`. `lookup.resolve_interface` resolves server + NIC + VLAN tag to croit records (used by `ha_group`, `nfs_cluster`, `cephfs_guard`, `smb_cluster`). `module.ceil_mib` is the only place sizes are rounded to MiB. |
| 2026-10-06 | Deleting a gateway disk (iSCSI or NVMe-oF) only stops the export by default. Deleting the RBD image behind it needs `delete_image: true` (plus `confirm_delete`). |
| 2026-10-06 | One-way or disruptive cluster changes need `confirm_action`: S3 multisite convert, join and promote; the NFS implementation switch; the SMB DNS-name change and generation migration. They are never made in check mode. |
| 2026-10-06 | Documentation standard (AGENTS.md "Module documentation standard"): every module has `seealso`, fully described options, at least 3 examples (header comment plus `module_defaults`), and RETURN with `returned`, `type` and `contains`/`sample`. Collection docs live in `docs/docsite/` (guides, `links.yml`, `extra-docs.yml`). CI builds the docsite with warnings treated as errors. |
| 2026-10-06 | The repo keeps `DESIGN.md`, `README.md` and `AGENTS.md` (plus `PLAN.md`) up to date with every change. |

## 1. What the API tells us (design drivers)

| Finding | Consequence for the collection |
|---|---|
| Base URL is `https://<mgmt>/api`. The spec defines no `securitySchemes`. | The URL is a module parameter, and auth is handled by hand in `module_utils`. |
| Auth comes in two forms. **API tokens** (`/api-tokens`, with roles `admin`, `viewer` or `securefolder`) are sent directly as `Authorization: Bearer <token>`. A **user login** goes to `POST /auth/login` with Basic auth and `grant_type=client_credentials`, and returns `Token{access_token, expires_in}`. | **Decided: API token only.** Every request sends `Authorization: Bearer <api_token>`. There is no login call and no session handling, and username/password is not supported. Least privilege is the operator's job: a `viewer` token is enough for `*_info` modules and check-mode runs, while writes need an `admin` token. A 401 or 403 response is turned into a clear error that names the missing role. |
| **Async tasks**: about 150 write operations return `ManagedTask` or `ManagedThreadTask` (`id`, `done`, `state` with values WAITING/RUNNING/FINISHED/FAILED/CANCELED, `statusCode`, `output`, `question`). You poll them with `GET /tasks/{id}`. | Shared `wait` / `wait_timeout` handling. A FAILED task makes the module fail and shows the task output. A task that is waiting on a `question` fails clearly unless we add answer support later. |
| **Ignorable warnings**: 84 operations have an `ignoreWarning` query parameter. A risky call returns HTTP 400 with `IgnoreWarningResponse{ignorableWarning.token, warningText}`, and the client re-sends the request with that token. | One option, shared by every module: `ignore_warnings: false` by default. When it is false, the module fails and shows the warning text. When it is true, the module re-sends with the token automatically. It is never auto-confirmed silently. |
| Errors come back as `ErrorMessage{code, message, details}`. | They map to `module.fail_json(msg=..., status=..., details=...)`. |
| Several list endpoints can be paginated: `?pagination=` returns either a raw list or a paginated wrapper. | The client asks for the raw list, and handles the paginated wrapper if it comes back that way. |
| **Change requests**: `POST /crush` does not apply changes. It returns a diff that has to be approved through `/change-requests/{id}/approve`. These requests live only in memory. | CRUSH map editing gets a module of its own, deferred to a later phase (see PLAN.md). The simple CRUSH rule endpoints can still be used directly. |
| Some resources are keyed by a numeric ID: servers, networks, hook scripts, HA groups, users, snapshot schedules and NVMe-oF objects. | Modules accept a natural key (hostname, name, CIDR) and look up the ID themselves, so playbooks stay readable and idempotent. |
| Some create calls are idempotent on the server already. For example, `POST /pools` leaves an existing pool alone, and `PATCH /pools/{name}` runs no command for unchanged members. | We still do a read → compare → write cycle ourselves, so `changed`, `--check` and `--diff` are accurate. |
| Secrets are returned only once. The API token secret is shown once, and S3 keys, Ceph keyrings and passwords are sensitive. | Use `no_log` on secret parameters. A secret value is only returned on create, and the docs warn about it. |

## 2. Collection layout

FQCN: **`croit.ceph`** (decided 2026-10-06).

```
croit-ansible/  (checked out as ansible_collections/croit/ceph for ansible-test)
├── galaxy.yml
├── meta/runtime.yml               # requires_ansible, action_groups (croit.ceph.all)
├── README.md                      # user-facing: install, auth, usage, module list
├── DESIGN.md                      # this file: architecture and contracts
├── PLAN.md                        # roadmap, phases, open questions
├── AGENTS.md                      # rules for AI/human contributors (CLAUDE.md imports it)
├── CLAUDE.md                      # imports AGENTS.md
├── COPYING, LICENSES/             # GPL-3.0-or-later and BSD-2-Clause texts
├── changelogs/                    # antsibull-changelog config and fragments (CHANGELOG.rst is generated on release)
├── .ansible-lint                  # production profile
├── .github/workflows/ci.yml       # sanity/units matrix 2.14..devel, EL9 job, lint, galaxy-importer
├── .github/workflows/release.yml  # tag vX.Y.Z -> gates -> galaxy publish
├── .github/galaxy-importer.cfg
├── plugins/
│   ├── module_utils/
│   │   ├── client.py              # CroitClient: auth, request(), errors, warnings, pagination
│   │   ├── tasks.py               # wait_for_task(), task result helpers
│   │   ├── module.py              # CroitModule base: common args, check/diff, size/quota/mode parsing
│   │   ├── lookup.py              # server/disk/NIC/interface natural-key lookups
│   │   ├── crush.py               # CRUSH rule parsing (crush_rule, crush_info)
│   │   ├── iscsi.py               # iSCSI gateway lookups and disk requests
│   │   ├── nvmeof.py              # NVMe-oF gateway and service lookups
│   │   ├── smb.py                 # SMB cluster lookup, share options
│   │   ├── qos.py                 # RBD QoS limits (pool_qos, rbd)
│   │   └── rgw.py                 # RGW quota helpers (s3_user, s3_bucket)
│   ├── doc_fragments/croit.py     # croit.ceph.croit (connection), .wait, .warnings, .attributes
│   └── modules/                   # one file per resource (see PLAN.md)
├── tests/
│   ├── config.yml                 # modules.python_requires: ">=3.9"
│   ├── unit/fake_croit.py         # in-memory fake croit API + run_module() helper
│   ├── unit/plugins/module_utils/ # client, tasks, base module
│   ├── unit/plugins/modules/      # one test file per module, incl. the idempotency sequence; per-area stateful fakes (fake_rbd, fake_s3, fake_servers, fake_cluster, fake_rgw, fake_nfs, fake_smb, fake_iscsi, fake_nvmeof)
│   ├── integration/integration_config.yml.template
│   ├── integration/targets/<module>/  # aliases: unsupported (needs a live lab croit)
│   └── sanity/ignore-*.txt        # only if ever needed; none today
├── CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md
├── docs/docsite/                  # links.yml, extra-docs.yml, rst/ guides (rendered on Galaxy / docsite)
├── docs/openapi.json              # vendored spec snapshot (drift checks; excluded from the build)
└── tools/check_spec_drift.py      # flags module endpoints/fields that no longer match the spec
```

**Runtime requirements (EL9 compatible):** Python ≥ 3.9 and ansible-core ≥ 2.14.
- **Python 3.9** is EL9's system Python (`/usr/bin/python3`). All code stays 3.9-compatible: no `match`, no `X | Y` type unions, and no stdlib features added in 3.10 or later.
- **ansible-core 2.14** is the version EL9 AppStream ships. `meta/runtime.yml` sets `requires_ansible: ">=2.14.0"`, and nothing used may need a newer core.
- The collection uses **no third-party libraries**: HTTP goes through `ansible.module_utils.urls.open_url`. That way a plain `dnf install ansible-core` on EL9 is enough, with no pip.

**Execution model:** the modules run on the controller, usually with `delegate_to: localhost` or `connection: local`, and talk to the croit management node over HTTPS. An `action_group` called `croit.ceph.all` lets you set connection defaults once through `module_defaults`.

## 3. Shared module behaviour (module_utils)

Every module accepts the connection options below. Modules that change things also get the wait and warning options. They are documented once, in the `croit.ceph.croit` doc fragment and its `.wait` and `.warnings` sub-fragments.

```yaml
api_url:         # env CROIT_API_URL   e.g. https://croit-mgmt/api
api_token:       # required, env CROIT_API_TOKEN (no_log)
validate_certs:  true
timeout:         30           # per HTTP request
wait:            true         # wait for async croit tasks
wait_timeout:    600
ignore_warnings: false        # auto-confirm croit "ignorable warnings"
```

### Idempotency and check mode contract (hard requirement for every module)

Every module is a full declarative Ansible module, not a thin API wrapper. **No module ships unless it meets every rule below, and tests enforce each one.**

1. **`supports_check_mode=True` on every module.** There are no exceptions and no `check_mode: no` workarounds in the docs.
2. **Read → compare → write.** Each run does the following:
   - fetches the current state with GETs (looking up IDs from natural keys);
   - builds the desired state from the parameters the user actually set;
   - computes the difference between the two;
   - calls write endpoints **only** for the fields that differ.
   A converged resource gets **zero** write calls and returns `changed=false`.
3. **Check mode never writes.** In check mode the module does only the GETs, then returns the same `changed` and `diff` that a real run would produce. No POST, PUT, PATCH or DELETE calls are made, no croit task is started, and no warning-confirmation retry happens. A unit test asserts that only GET requests were made.
4. **Diff mode.** `--diff` returns `before` and `after` dicts, limited to the managed fields, with secrets masked. A field the user didn't set is never reported as a change.
5. **Partial specification.** Unset options (`None`) mean "leave alone". Only `state: absent`, or an explicit `exclusive`/`purge` flag on list-type options (SSH keys, subusers, ACLs, group members), removes things that aren't listed.
6. **Normalisation before comparing.** This covers:
   - size units (`100G` vs bytes);
   - CIDR and MAC formatting;
   - list ordering, where the API treats order as irrelevant;
   - case, for enums;
   - ceph option name spelling (spaces vs underscores, as the API allows);
   - croit's defaults, so that an unset option and its default value compare as equal.
   This stops a re-run from flapping between changed and unchanged.
7. **Write-only and secret fields** (user passwords, S3 secret keys, SMB passwords, IPMI credentials) can't be read back to compare. These follow the `ansible.builtin.user` pattern: `update_password: on_create` (the default) or `always`, which is honestly reported as `changed=true`. They are `no_log`, and their values are masked in diffs and return values.
8. **Immutable fields.** Some fields can't change after creation, such as a pool's `erasure_coding` or `data_chunks`, or an RBD image's pool. If one of these differs from the existing resource, the module fails with a clear message and doesn't try a destructive recreate. Checks that run in check mode (rule 3) catch this too.
9. **Imperative operations are modelled as states wherever the API exposes enough to compare against:**
   - services use `state: started/stopped`, comparing against the service status;
   - OSDs use `in: true/false`;
   - OSD flags and mgr modules use `present/absent` and `enabled`;
   - server power uses `power: on/off`, compared against the IPMI state.
   True one-shot actions (`restart`, `rolling_restart`, `reboot`, `scrub`, `run hook now`) behave like `ansible.builtin.service: state=restarted`. They always report `changed=true`, skip the action in check mode, and are kept clearly separate from the declarative options.
10. **Async tasks.** A module that starts a croit task waits for it (`wait: true`) before returning. A task that fails or gets cancelled fails the module. After the task, the module re-reads the resource, so the result reflects reality. With `wait: false`, the module returns `changed=true` together with the task, and a later run converges.
11. **Ignorable warnings.** These are only acted on in a real run. In check mode, the module adds a `warnings` entry saying a real run would need `ignore_warnings: true`.
12. **Return values.** Every module returns the resource as croit reports it after the change (as `before`, unchanged, in check mode), plus `task` when one ran.

`*_info` modules are read-only. They always return `changed=false` and support check mode.

The escape-hatch module **`croit.ceph.api`** sends a raw request, like `uri` but aware of croit. By its nature it isn't idempotent. A GET always runs. A write is skipped in check mode and reported as changed, unless the caller passes `changed_when`-style hints. It's documented as a last resort, and every endpoint it gets used for regularly becomes a candidate for a proper module.

## 4. Testing and quality

1. **Unit tests** (pytest, mocked `open_url`): bearer-token header and 401/403 handling, the warning and token retry loop, task polling (success, failure, timeout, question), pagination, and idempotency/diff for each module.
2. **Sanity tests**: `ansible-test sanity`, with no ignore entries as the goal.
3. **Idempotency and check-mode tests (mandatory for every module).** Each module gets unit tests with mocked HTTP and integration targets that follow the standard sequence:
   1. create in check mode: `changed=true`, and the resource still doesn't exist afterwards;
   2. create: `changed=true`;
   3. the same task again: `changed=false`, with no write calls (unit-asserted);
   4. the same task in check mode: `changed=false`;
   5. update in check mode: `changed=true`, the diff is correct, and the resource is unchanged;
   6. update: `changed=true`;
   7. update again: `changed=false`;
   8. delete in check mode: `changed=true`, and the resource still exists;
   9. delete: `changed=true`;
   10. delete again: `changed=false`.
   The unit tests also assert that check mode only ever issues GETs.
4. **Integration tests** run these targets from `tests/integration/targets/<module>` against a real croit lab cluster. They are gated by `CROIT_API_URL`/`CROIT_API_TOKEN` being set.
5. **Spec drift check**: `tools/check_spec_drift.py` compares the endpoints and request fields used by each module with the vendored `docs/openapi.json`. It can be refreshed from a live management node to catch API changes between croit releases.
6. **Docs**: `ansible-doc`-clean `DOCUMENTATION`/`EXAMPLES`/`RETURN` blocks, plus a docsite built with antsibull-docs.

## 5. Ansible Galaxy publishing

The collection is built from the start to be published on [Ansible Galaxy](https://galaxy.ansible.com). Checked on 2026-10-06, the `croit` namespace is **not yet registered** on Galaxy.

### Required artefacts

| Item | Requirement |
|---|---|
| `galaxy.yml` | These fields are set:<br>• `namespace: croit` and `name: ceph`: lowercase, `[a-z0-9_]`, not starting with a digit or `_`<br>• `version`: SemVer<br>• `readme: README.md`<br>• `authors`, `description`<br>• `license` (SPDX) or `license_file`<br>• `tags`: at most 20, lowercase `[a-z0-9_]`, e.g. `ceph`, `storage`, `croit`, `infrastructure`, `cloud`<br>• `repository`, `documentation`, `homepage`, `issues`<br>• `dependencies: {}`<br>• `build_ignore` |
| `meta/runtime.yml` | `requires_ansible: ">=2.14.0"` (Galaxy rejects an import without it), plus the `action_groups` and any `plugin_routing` for deprecations. |
| `LICENSE` / `COPYING` | The full licence text at the repo root, plus SPDX headers in each file. |
| `README.md` | Shown as the Galaxy landing page. It covers install, requirements, auth, usage and the module list. |
| `CHANGELOG.rst` and `changelogs/` | Managed by `antsibull-changelog`: `changelogs/config.yaml`, `changelog.yaml`, and a fragment for every change. Each module and plugin gets `version_added` in its docs. |
| Module docs | Complete `DOCUMENTATION`, `EXAMPLES` and `RETURN` blocks, with `author`, `version_added` and the shared doc fragment. Galaxy renders these, and the importer fails on broken docs. |
| `tests/sanity/ignore-2.X.txt` | One file per supported ansible-core version, kept empty where possible. |
| `build_ignore` | Leaves out `PLAN.md`, `AGENTS.md`, `CLAUDE.md`, `docs/openapi.json` (large), `tools/`, `.github/`, `*.tar.gz` and IDE/venv cruft, so the tarball stays small and clean. |

### Quality gates (run in CI before any release)

1. `ansible-test sanity` on every supported ansible-core version, from 2.14 on Python 3.9 up to the current stable release.
2. `ansible-test units`.
3. `ansible-lint --profile production`.
4. **`galaxy-importer`**, the same checker Galaxy runs on upload. It runs on the built tarball (`python -m galaxy_importer.main croit-ceph-X.Y.Z.tar.gz`), so an import can't fail after a tag has been pushed.
5. `antsibull-docs lint-collection-docs --plugin-docs`, and a full docsite build (`antsibull-docs sphinx-init` + `build.sh`) with warnings treated as errors.
6. `antsibull-changelog lint`.
7. `python tools/check_spec_drift.py`: every `# croit-api:` endpoint declared by a module exists in `docs/openapi.json`.

Status on 2026-10-06 (after Phase 4: 82 modules, 686 unit tests): every gate passes locally. That means sanity and units on ansible-core 2.20 with Python 3.14 **and** on ansible-core 2.14.18 with Python 3.9 in a Rocky 9 container, ansible-lint with the production profile, both antsibull lints, the drift check (461 endpoints), and galaxy-importer 0.4.43 ("Importer processing completed successfully"). The importer's only warning is the expected `meta-runtime[unsupported-version]` for 2.14 (see the decisions log).

### Release process

1. Bump `version` in `galaxy.yml` (SemVer). Breaking changes only happen in a major version, with a deprecation period through `plugin_routing`.
2. Run `antsibull-changelog release`, then commit and tag `vX.Y.Z`.
3. CI (GitHub Actions) builds the tarball and re-runs the gates. Then it runs `ansible-galaxy collection publish --api-key $GALAXY_API_KEY`, with the key kept as a repo secret.
4. A Galaxy version can never be re-uploaded or overwritten, so a bad release is fixed by publishing a new patch version.

### One-off setup (needs a human)

- Sign in to galaxy.ansible.com with GitHub and create or claim the **`croit`** namespace. Add the croit maintainers as owners, and set the logo, links and description.
- Create a Galaxy API key and store it as a CI secret.
- Optionally, Red Hat Automation Hub certification later. That needs the Red Hat partner programme and is out of scope for now.

## 6. Example target UX

```yaml
- hosts: localhost
  module_defaults:
    group/croit.ceph.all:
      api_url: https://croit-mgmt/api
      api_token: "{{ vault_croit_token }}"
  tasks:
    - croit.ceph.pool:
        name: rbd-ssd
        application: rbd
        size: 3
        min_size: 2
        crush_rule: 1
        pg_num: 128

    - croit.ceph.rbd:
        pool: rbd-ssd
        name: vm-disk-01
        size: 100G
        state: present

    - croit.ceph.s3_user:
        uid: backup
        display_name: Backup service
        quota: { max_size: 10T, enabled: true }
      register: s3u

    - croit.ceph.osd_flag:
        flag: noout
        state: present
```
