# AGENTS.md

These are instructions for AI agents (and humans) working in this repository: the `croit.ceph` Ansible collection for the croit REST API. `CLAUDE.md` imports this file. Every change must follow it.

## Read first

1. [DESIGN.md](DESIGN.md) is the architecture, the shared behaviour, the **idempotency/check-mode contract** and the **decisions log**. It is authoritative; don't contradict a logged decision without agreeing it first.
2. [PLAN.md](PLAN.md) holds the module inventory, the phase status and the open questions, including the list of **unverified croit API assumptions**. Don't start a module that isn't planned without agreeing it first.
3. The API reference is `docs/openapi.json`, a vendored snapshot of https://www.croit.io/api-docs. Check every endpoint, field, enum and response shape against it. Never guess. Where the spec doesn't settle a behaviour, make the safest assumption and record it (see "Unverified API behaviour").

## Non-negotiable rules

- **EL9 compatibility.**
  - Python ≥ 3.9 and ansible-core ≥ 2.14.
  - No `match` statements, no `X | Y` type unions, and no stdlib features added in 3.10 or later.
  - No third-party imports. HTTP goes through `ansible.module_utils.urls.open_url`, via the shared client only.
- **Fully idempotent.** Every module does read → compare → write, and writes only the fields that differ. A converged resource gets zero write calls and returns `changed=false`.
- **Check mode on every module** (`supports_check_mode=True`).
  - Check mode issues **GET requests only**: no task is started and no warning is confirmed.
  - It returns the same `changed` and diff that a real run would.
  - `CroitModule.write()` raises `CheckModeViolation` if this is ever broken.
- **Diff mode.** Return `before` and `after` for the managed fields only, with secrets masked.
- **Auth is API token only** (`Authorization: Bearer`). Don't add username/password or session login.
- **Secrets.**
  - Mark them `no_log=True`.
  - Never put them in diffs, error messages or default return values. In diffs, a changed secret shows as `********` or `******** (changed)`.
  - Return a secret only on explicit request (`return_*`, `show_secrets`), or when it can only ever be returned once (`api_token`), and document `no_log: true` for those tasks.
- **Unset options mean "leave alone".** Only `state: absent`, or an explicit `exclusive` option on a list, removes things.
- **Never auto-confirm croit's ignorable warnings** unless the user set `ignore_warnings: true`. The one exception: an explicit safety flag for the same risk may confirm the matching warning, with `write(..., confirm_warnings=True)`.
- **No destructive recreate.** A change to an immutable or create-only field fails clearly. It is never a delete-and-create.
- **Safety flags are checked before any request, in check mode too.** See "Safety and semantics".
- **Reuse Ansible as much as possible; don't duplicate code you don't need to.** Before writing a helper, look for existing code, in this order:
  1. ansible-core `module_utils` (e.g. `urls`, `basic`, `common.text.converters`, `common.network`, `common.dict_transformations`);
  2. the Python standard library (e.g. `ipaddress`), which is also what upstream Ansible filters often call;
  3. this collection's `plugins/module_utils`.

  Modules can't import other collections' filter, test or `plugin_utils` code (AnsiballZ only bundles `module_utils`), and a dependency on another collection or a third-party library needs the maintainer's agreement. When nothing reusable exists, write the helper once in `plugins/module_utils`, never in a module.
- **Reuse `plugins/module_utils`.** Never duplicate HTTP, task polling, diff, lookup or parsing logic in a module.

## Safety and semantics (match the existing modules exactly)

| Situation | Rule |
|---|---|
| Deleting something that **destroys data**, or **disconnects every client** of a gateway | require `confirm_delete: true` |
| A delete where no data is lost, or croit itself refuses non-empty deletes | no flag; the module docs say what the removal affects |
| Creating or replacing an OSD (erases the disk) | require `confirm_wipe: true` |
| Rebooting or shutting down a node; IPMI power off / cycle / BIOS; one-way or disruptive cluster changes (multisite convert, join or promote; NFS implementation switch; SMB DNS name or migration) | require `confirm_action: true` |
| Changing or deleting the interface that carries a node's management IP | require `allow_management_ip_change: true` |
| Also deleting the RBD image behind a gateway disk | require `delete_image: true` (plus `confirm_delete`) |
| One-shot actions (restart, reboot, redetect, run now, IPMI actions) | always `changed=true`, skipped in check mode, separate from the declarative options |
| Anything with readable state | model it declaratively (`state: started`, `in: true`, `power: on`, `enabled: true`) |
| Write-only secrets that croit can't return | `update_password` / `update_secret` / `update_shared_key`: `on_create` (default) or `always`, where `always` always reports a change |
| Secrets croit does return | compare them directly; still never show them |
| A list option the user may want to make exact | add `exclusive: false` (default) / `true` |
| User or token modules | never delete, or remove admin from, the identity the playbook authenticates as (`/auth/token-info`) |

## Unverified API behaviour

When the spec doesn't settle a behaviour (response shape, null vs 0, whether a PUT replaces or merges, pagination):

1. Make the safest assumption, and handle both plausible shapes where you can.
2. Encode it in the unit-test fake, so the assumption is visible.
3. Mention it in the module's `notes`.
4. Add it to the unverified-assumptions list in PLAN.md (open questions 12–15, or a new item), so the lab integration run can confirm it.

## Definition of done for a module

- [ ] **Docs:** `DOCUMENTATION`, `EXAMPLES` and `RETURN` meet the documentation standard below, and `python tools/check_docs.py <module>` reports 0 problems.
- [ ] **Modes:** `supports_check_mode=True`, and diff is implemented.
- [ ] **Unit tests** (stateful fake, mocked HTTP):
  - [ ] the full **10-step sequence**, each step in check mode first: create check, create, re-run, re-run check, update check, update, update again, delete check, delete, delete again. Set/unset resources use the equivalent steps.
  - [ ] check-mode and converged steps assert `fake.writes() == []`;
  - [ ] API errors, task failure, ignorable warnings and every safety-flag refusal (including in check mode);
  - [ ] no secret appears in the result or diff.
- [ ] **Integration target** in `tests/integration/targets/<module>/`:
  - [ ] aliases `unsupported` and `context/controller`;
  - [ ] the same sequence;
  - [ ] cleanup or restore in `always`;
  - [ ] anything destructive gated behind an opt-in variable, documented in `tests/integration/integration_config.yml.template`.
- [ ] **Registration:** the module is in `meta/runtime.yml` `action_groups.all`, and its endpoints are declared as `# croit-api:` markers.
- [ ] **Changelog:** a fragment in `changelogs/fragments/`.
- [ ] **All checks pass** (see "Commands"), on ansible-core 2.20 **and** on the EL9 baseline (2.14, Python 3.9), with no new entries in `tests/sanity/ignore-*.txt`.
- [ ] **Docs updated** (see "Keep the docs current").

## Module documentation standard

`tools/check_docs.py` enforces this mechanically. Accuracy is still your job: read the code and the spec before writing docs, and never document behaviour the code doesn't have.

**DOCUMENTATION**
- **`short_description`:** a verb phrase with no trailing period, such as "Manage Ceph pools on a croit cluster".
- **`description`:** at least two sentences covering:
  - what the module manages, and how the resource is identified (its natural key);
  - that options left unset are left alone;
  - anything create-only, immutable or destructive.
- **Every option:** at least one full sentence, ending in a period. Also give:
  - units, and binary sizes such as V(10G);
  - what an unset value means;
  - what V(null) or an empty value does;
  - whether the option is create-only;
  - which other options it interacts with (`required_together`, `mutually_exclusive`).
- **Semantic markup:**
  - O(option) and O(option=value) **only for this module's real options** (antsibull lint and the docsite build fail otherwise); V(value) for values;
  - E(ENV_VAR) for environment variables; RV(return) for return values;
  - M(croit.ceph.module) for other modules;
  - C() for literal code or API paths, and for option names of other modules or concepts;
  - U() or L() for links.
- **`seealso`:** every module has one, containing:
  - related `croit.ceph` modules (`module:` plus a one-line `description:`), always including the `*_info` or resource counterpart;
  - the croit API docs (`link: https://www.croit.io/api-docs`, `name: croit API reference`);
  - the relevant upstream Ceph docs page where one exists (`https://docs.ceph.com/en/latest/...`). Check that the link returns 200.
- **`notes`:** required for anything that destroys data, disrupts clients, handles secrets or depends on an unverified croit behaviour.
- **`attributes`:** say `check_mode` and `diff_mode` support honestly, and use `partial` plus `details` where it applies (e.g. `api`).
- **Fragments:** `croit.ceph.croit` + `.attributes` on every module; `.wait` / `.warnings` only where they apply. A module with `.wait` must return `task`.
- **`author`:** `Damien Dye (@damo2929)`; `version_added` is the next release.

**EXAMPLES**
- **Header:** start with the comment `# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).`, and leave out the connection options in the tasks.
- **Every task:** a `name:`, and the FQCN (`croit.ceph.<module>`).
- **Resource modules**, at least:
  - create, or a typical use;
  - an update of a single setting;
  - a `register:` plus a use of the result;
  - delete or remove when supported, with any `confirm_*` flag and a comment saying what it does.
- **Info modules:** at least two examples (everything, and a filtered read), plus a use of the result.
- **Realism:** values must be valid for the options' types and choices, and never invented names. Look things up (e.g. with an `*_info` module) when croit decides the names. Use `no_log: true` on tasks that pass or return secrets. Don't name a registered variable after a reserved name (`tasks`, `vars`, ...).

**RETURN**
- **Every key:** `description`, `returned` (a precise condition, such as "when O(state=present)") and `type`.
- **`dict` and `list` returns:** need `contains:` (fields with description, returned, type and sample) or a realistic `sample`. Main resource returns use `contains:`, with fields taken from the code and the spec.
- **Scalars:** need a `sample`.
- **Secrets:** say how they are masked, and use `********` in samples, never a real-looking secret.

## Keep the docs current (required in the same change)

| When you… | Update |
|---|---|
| add, rename or change the status of a module | the README.md module table, `meta/runtime.yml`, and PLAN.md |
| change architecture, shared options, module_utils behaviour or the contract | DESIGN.md, including a new row in the **Decisions log** |
| change requirements, install steps, auth or usage | README.md, and `docs/docsite/rst/guide_getting_started.rst` |
| add or change a safety flag, secret handling or task/warning behaviour | `guide_safety.rst`, `guide_secrets.rst` or `guide_tasks_and_warnings.rst`, and the README safety table |
| add or change any example (README, guides, module or `examples/` playbooks) | run `python tools/check_docs.py` and `ansible-lint --profile production` |
| add a module that fits a common workflow | consider adding or extending a playbook in `examples/`, and update `examples/README.md` |
| add an integration variable | `tests/integration/integration_config.yml.template` |
| make an unverified API assumption | the module `notes` and the PLAN.md assumptions list |
| change workflow, rules or tooling for contributors | AGENTS.md and CONTRIBUTING.md |
| resolve an open question | PLAN.md (mark it decided) and the DESIGN.md decisions log |

A change that leaves any of these files inaccurate is incomplete.

## Conventions

- **Base class.** Every module uses `CroitModule` (`plugins/module_utils/module.py`). Reads go through `get` / `get_list` / `get_or_none`. Writes go through `write()`, and tasks through `handle_task()`. Only `croit.ceph.api` calls `client.request()` directly.
- **`pool.py` is the reference module.** Follow its structure: find → desired → compare → write → re-read → exit with diff.
- **Endpoint markers.** List every endpoint a module calls as a `# croit-api: METHOD /path` comment, using the spec's path template. `tools/check_spec_drift.py` checks them.
- **Shared helpers.** Reuse these before writing your own:

  | File | Helpers |
  |---|---|
  | `module.py` | `parse_size`; `parse_quota` (0 means unlimited); `parse_mode`; `ceil_mib` / `MIB`; `changed_fields`; `subset` |
  | `lookup.py` | `find_one`; `find_server` / `require_server`; `require_disk`; `find_nic`; `normalise_mac`; `resolve_interface` (server + NIC + VLAN tag → croit records) |
  | `qos.py` | RBD QoS limits |
  | `rgw.py` | S3 quotas (-1 means unlimited) |
  | `crush.py` | CRUSH rule parsing |
  | `iscsi.py`, `nvmeof.py`, `smb.py` | gateway lookups |
  | `ip.py` | stdlib-`ipaddress` `ip_address`, `ip_interface`, `ip_network`, `normalise_ip`, `normalise_network` (same code as `ansible.utils.ipv6form`) |
  | `client.py` | `path_join` for URL-safe paths |

  If two modules need the same logic, move it into `module_utils` with unit tests. Modules can't import each other, because AnsiballZ only bundles `module_utils`.
- **Names.**
  - Modules are `croit.ceph.<resource>`, with `_info` for read-only modules.
  - Options are snake_case even where the API uses camelCase; map them in the module.
  - Never reuse a shared option name (`timeout`, `wait`, `wait_timeout`, `api_url`, `api_token`, `validate_certs`, `ignore_warnings`) for a module option. Use, for example, `alert_timeout`.
  - Never name a return value `keys`, `items` or `values` (they clash with Jinja dict methods); use `ssh_keys`, `ceph_keys` and so on.
- **Identity.** Take natural keys (name, hostname, CIDR, IQN, NQN) and look up croit's numeric ids in the module. When croit stores a cluster's "name" as its `description`, say so in the docs.
- **Unit-test fakes.**
  - `tests/unit/fake_croit.py` provides `FakeCroit`, `Text` (text/plain answers) and `run_module()`.
  - Per-area stateful fakes live in `tests/unit/plugins/modules/fake_<area>.py`.
  - Assert check mode with `fake.writes() == []`.
- **Licence headers.** Modules, doc fragments, tests and tools use GPL-3.0-or-later; `plugins/module_utils/` uses BSD-2-Clause. Copy the header from an existing file.

## Known pitfalls (each of these has broken a check before)

- **YAML in docs.**
  - A plain scalar containing `: ` breaks parsing, so reword or quote it (e.g. not "use C(delegate_to: localhost)").
  - Python string literals in docs must stay inside the `r"""..."""` block.
- **pep8.**
  - Two blank lines go before top-level `def`/`class`.
  - No blank line goes between a decorator and its function.
  - No trailing blank lines.
  - Run sanity after moving code between files.
- **Reserved pytest names.** Never name a test helper `setup`, `teardown`, `setup_module` or `setup_function`. The older pytest in the ansible-core 2.14–2.16 test containers runs a module-level `setup` as a nose-style hook (passing the module object), while pytest 8 doesn't, so only CI on old cores fails. Reproduce CI with `ansible-test units --docker default` on those cores, not just the newest one.
- **pylint false positives.** `dict(base, key=...)` gives `repeated-keyword`; build the dict and `update()` it instead. The older pylint on 2.14 rejects `-(-x // y)` on a value that may be `None`, so use `ceil_mib` or explicit integer maths.
- **`tools/` scripts** must not use `urlopen` (2.14's `replace-urlopen` check), and have no shebang (`shebang` check).
- **EL9.** Code that passes on 2.20 can still fail on 2.14 with Python 3.9. Run the EL9 container before calling a change done.
- **Example playbooks** (`examples/`):
  - parameterise them through `vars:` at the top;
  - use `module_defaults` with `group/croit.ceph.all` and the `croit_*` vars from `group_vars/all/croit.yml`;
  - put secrets only in `vault_*` variables, with `no_log: true` where they pass through;
  - guard anything that reboots or destroys behind an explicit `-e ..._confirm=true` assert;
  - write generated files (reports, keyrings, tokens) only to git-ignored directories, with restrictive modes.
- **IP addresses.**
  - Parse and compare addresses only with `module_utils/ip.py` (`normalise_ip`, `normalise_network`, `ip_interface`, ...), never raw strings or a private `ipaddress` wrapper: croit may report `2001:db8::1/64` for `2001:DB8:0::1/64`.
  - Docs, examples and tests use documentation ranges only: `2001:db8::/32` (IPv6), `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` (IPv4) or private ranges.
  - URLs with an IPv6 literal need brackets (`https://[2001:db8::5]/api`).
  - Modules cannot import filter or `plugin_utils` code from other collections (e.g. `ansible.utils.ipv6form`): AnsiballZ only bundles `module_utils`. Call the underlying stdlib code instead.
- **Return values and the `wait` fragment.** The `.wait` fragment refers to `RV(task)`; a module that returns several tasks must still return `task` (the last one).

## Commands

Run these from a checkout at `.../ansible_collections/croit/ceph`:

```bash
ansible-test sanity --venv --python 3.9        # and on the newest Python version you have
ansible-test units  --venv --python 3.9
ansible-lint --profile production
antsibull-docs lint-collection-docs --plugin-docs .
antsibull-changelog lint
python tools/check_spec_drift.py               # add --refresh to re-download the spec
python tools/check_docs.py                     # documentation standard + all examples
ansible-galaxy collection build && python -m galaxy_importer.main croit-ceph-*.tar.gz
```

Docsite build, with warnings as errors (same as CI):

```bash
antsibull-docs sphinx-init --use-current --fail-on-error --dest-dir /tmp/docbuild croit.ceph
cd /tmp/docbuild && pip install -r requirements.txt && ./build.sh
```

EL9 baseline (same as the CI `el9` job):

```bash
podman run --rm -v "$PWD/../../..:/work:Z" -w /work/ansible_collections/croit/ceph quay.io/rockylinux/rockylinux:9 bash -c \
  "dnf -y install python3-pip git-core && pip3 install 'ansible-core>=2.14,<2.15' pytest && \
   git config --global --add safe.directory \$PWD && \
   ansible-test units --python 3.9 --requirements && ansible-test sanity --python 3.9 --requirements"
```

## Workflow

- **Ask first.** Check with the maintainer before starting a new phase, adding a module that isn't planned, or making a design decision that DESIGN.md doesn't cover.
- **Committing and pushing.**
  - Commit or push only when asked.
  - Before committing, run every check above and scan the staged files for secrets.
  - Commit to `main` on `git@github.com:damo2929/croit-ansible-modules.git`, with clear commit messages.
  - Never force-push, and never rewrite pushed history.
- **Releases.**
  - Never run `ansible-galaxy collection publish` by hand; releases go only through the tagged CI workflow (a Galaxy version can't be overwritten).
  - Change `galaxy.yml` `version` only as part of the release process in DESIGN.md §5.
- **Integration tests.** Never run them against a production cluster. They need explicit `CROIT_API_URL` / `CROIT_API_TOKEN` (or `integration_config.yml`) pointing at a lab.

### Parallel work (several agents at once)

Large changes are split across parallel workers. The rules:

- **Each worker owns a fixed set of files:** its modules, their tests, their fakes and their integration targets. It edits nothing else.
- **Shared files are edited only by the coordinating agent:** `plugins/module_utils/*`, doc fragments, `tests/unit/fake_croit.py`, `meta/runtime.yml`, `galaxy.yml`, README, DESIGN, PLAN, AGENTS, CONTRIBUTING, changelogs and the integration config template.
- **What a worker reports:**
  - any shared change it needs (new helpers, runtime.yml entries, integration variables);
  - duplicated code that should move to `module_utils`;
  - API assumptions it made.
- **Workers run sanity in their own scratch copy** of the repo. Never rsync into the real checkout, or into a symlink that points at it.
- **When all workers finish, the coordinator:**
  1. moves duplicated helpers into `module_utils` (with tests);
  2. updates the shared files;
  3. confirms with a diff against HEAD that docs-only work didn't change code;
  4. runs every check in "Commands" on the whole collection, including EL9 and the docsite build.
