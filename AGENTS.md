# AGENTS.md

These are instructions for AI agents (and humans) working in this repository: the `croit.ceph` Ansible collection for the croit REST API.

## Read first

1. [DESIGN.md](DESIGN.md) is the architecture, the shared behaviour and the **idempotency/check-mode contract**. It is authoritative.
2. [PLAN.md](PLAN.md) holds the phases, the module inventory and the open questions. Don't start work on a module that isn't planned without agreeing it first.
3. The API reference is `docs/openapi.json`, a vendored snapshot of https://www.croit.io/api-docs. Check every endpoint, field and enum against it. Never guess.

## Non-negotiable rules

- **EL9 compatibility.**
  - Python ≥ 3.9 and ansible-core ≥ 2.14.
  - No `match` statements, no `X | Y` type unions, and no stdlib features added in 3.10 or later.
  - No third-party imports. Use `ansible.module_utils.urls.open_url` for HTTP.
- **Fully idempotent.** Every module does read → compare → write, and only writes the fields that differ. A converged resource gets zero write calls and returns `changed=false`.
- **Check mode on every module** (`supports_check_mode=True`). Check mode issues **GET requests only**, starts no croit task, and returns the same `changed`/`diff` a real run would.
- **Diff mode.** Return `before` and `after` for the managed fields, with secrets masked.
- **Auth is API token only** (`Authorization: Bearer`). Don't add username/password or session login.
- **Secrets.** Mark them `no_log=True`, and never put them in diffs, return values or error messages.
- **Unset options mean "leave alone".** Only `state: absent`, or an explicit `exclusive`/`purge` option, removes things.
- **Never auto-confirm croit ignorable warnings** unless the user set `ignore_warnings: true`.
- **No destructive recreate.** A change to an immutable field is a clear failure, not a delete-and-create.
- **Reuse `plugins/module_utils`** (client, tasks, base module) and don't duplicate HTTP, task-polling or diff logic in modules.

## Definition of done for a module

- [ ] The `DOCUMENTATION`, `EXAMPLES` and `RETURN` blocks are complete and pass `ansible-doc`. The module uses the shared doc fragment.
- [ ] `supports_check_mode=True`. Diff support is implemented.
- [ ] Unit tests (mocked HTTP) cover: create, update, delete, a no-op re-run (asserting no write calls), check mode (asserting GET only), diff output, API errors, task failure, and ignorable warnings.
- [ ] An integration target in `tests/integration/targets/<module>/` follows the standard sequence in DESIGN.md §4: check, then apply, then re-apply with `changed=false`, for create, update and delete.
- [ ] `ansible-test sanity --python 3.9` and the unit tests pass, with no new entries in `tests/sanity/ignore-*.txt`.
- [ ] A changelog fragment is added under `changelogs/fragments/`.
- [ ] The `DOCUMENTATION` block has `author` and `version_added`. `ansible-lint --profile production` and `galaxy-importer` on the built tarball both pass (DESIGN.md §5).
- [ ] The docs are updated (see below).

## Keep the docs current (required in the same change)

| When you… | Update |
|---|---|
| add, rename or change the status of a module | the README.md module table, and PLAN.md (tick it off or move it) |
| change architecture, shared options, module_utils behaviour or the contract | DESIGN.md, including a new row in the **Decisions log** |
| change requirements, install steps, auth or usage | README.md |
| change workflow, rules or tooling for contributors | AGENTS.md |
| resolve an open question | PLAN.md §3 (mark it decided) and the DESIGN.md decisions log |

A change that makes these files inaccurate is incomplete.

## Conventions

- **Base class.** Every module subclasses or uses `CroitModule` (`plugins/module_utils/module.py`). Reads go through `get`/`get_list`/`get_or_none`, and every write goes through `write()`, which raises `CheckModeViolation` in check mode. Never call `client.request()` for writes from a module (the `api` module is the only exception).
- **Endpoint markers.** List every endpoint a module calls as a `# croit-api: METHOD /path` comment at the top of the module, using the path template from the spec. `tools/check_spec_drift.py` checks them.
- **Unit tests** use `tests/unit/fake_croit.py`: a stateful `FakeCroit` subclass per resource, plus `run_module()`. Assert check mode with `fake.writes() == []`.
- **Shared helpers:** reuse them before writing your own.
  - `module.py`: `parse_size`, `parse_quota` (0 = unlimited), `parse_mode`, `changed_fields`, `subset`.
  - `qos.py`: RBD QoS limits.
  - `rgw.py`: S3 quotas (-1 = unlimited).
  - `lookup.py`: `require_server`, `require_disk`, `find_nic`, `normalise_mac`.
  - `crush.py`: CRUSH rule parsing.
  - `lookup.py`: also `resolve_interface` (server + NIC + VLAN tag).
  - `module.py`: also `MIB` and `ceil_mib`.
  - `iscsi.py`, `nvmeof.py`, `smb.py`: gateway lookups.
  - If two modules need the same logic, move it into `module_utils` with unit tests.
- **Hardware safety flags:** use the same names and semantics as the existing modules: `confirm_wipe`, `confirm_action`, `confirm_delete`, `allow_management_ip_change`. When unset they refuse, in check mode too.
- **Option names:** never reuse a shared connection option name (`timeout`, `wait`, `api_url` and so on) for a module option, because they clash. Use, for example, `alert_timeout`.
- **Return values:** never name a return value `keys`, `items` or `values`; they clash with dict methods in Jinja. Use `ssh_keys`, `ceph_keys` and so on.
- **Secrets in query parameters:** never put the URL in a message; the client already strips query strings.
- **`pool.py` is the reference module.** Copy its structure (find → desired → compare → write → re-read → exit with diff).

- **Module names:** `croit.ceph.<resource>` for resources and `croit.ceph.<resource>_info` for read-only modules. Use snake_case options, even where the API uses camelCase. Do the mapping in the module.
- **Resource identity:** take natural keys (name, hostname, CIDR) and look up croit's numeric IDs inside the module.
- **One file per module** in `plugins/modules/`. Every module joins the `croit.ceph.all` action group in `meta/runtime.yml`.
- **Licence headers:** modules, doc fragments, tests and tools use the GPL-3.0-or-later SPDX header; `plugins/module_utils/` uses BSD-2-Clause. Copy the header from an existing file.

## Commands

Run these from a checkout at `.../ansible_collections/croit/ceph`:

```bash
ansible-test sanity --venv --python 3.9        # plus the newest Python version you have
ansible-test units  --venv --python 3.9
ansible-lint --profile production
antsibull-changelog lint
python tools/check_spec_drift.py
ansible-galaxy collection build && python -m galaxy_importer.main croit-ceph-*.tar.gz
```

To check EL9 locally, run the units and sanity inside `quay.io/rockylinux/rockylinux:9` with `pip install 'ansible-core<2.15'` on its Python 3.9. That is what the CI `el9` job does.

## Workflow

- Check with the maintainer before starting a new phase, or when a design decision isn't covered by DESIGN.md.
- Don't commit or push unless asked.
- Never run `ansible-galaxy collection publish` by hand. Releases only go through the tagged CI workflow, because a Galaxy version can't be overwritten.
- Don't edit `galaxy.yml` `version` outside the release process in DESIGN.md §5.
- Never run integration tests against a production cluster. They need explicit `CROIT_API_URL`/`CROIT_API_TOKEN` pointing at a lab.
