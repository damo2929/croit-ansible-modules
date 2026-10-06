# Contributing to croit.ceph

Thanks for helping. This collection holds itself to a strict standard, because its modules run against production storage.

## Before you start

- Read [AGENTS.md](AGENTS.md). It is the rulebook for every change, whether it comes from a person or an AI agent: EL9 compatibility, the idempotency and check-mode contract, the safety flags, the documentation standard and the definition of done.
- Read [DESIGN.md](DESIGN.md) for the architecture and the decisions log.
- For a new module, check [PLAN.md](PLAN.md), and open an issue to agree the design before writing code.

## Workflow

1. Fork the repo and check it out at a path ending in `ansible_collections/croit/ceph`, because `ansible-test` and `tools/check_docs.py` need that layout.
2. Create a branch.
3. Make the change. Follow `plugins/modules/pool.py` as the reference module, and reuse `plugins/module_utils`.
4. Add or update:
   - unit tests in `tests/unit/` (resource modules run the full idempotency sequence);
   - an integration target in `tests/integration/targets/`;
   - a changelog fragment in `changelogs/fragments/` (see [antsibull-changelog](https://github.com/ansible-community/antsibull-changelog/blob/main/docs/changelogs.rst#changelog-fragment-categories));
   - the docs listed in AGENTS.md ("Keep the docs current").
5. Run the checks locally:

   ```bash
   ansible-test sanity --venv --python 3.9
   ansible-test units --venv --python 3.9
   ansible-lint --profile production
   antsibull-docs lint-collection-docs --plugin-docs .
   antsibull-changelog lint
   python tools/check_spec_drift.py
   python tools/check_docs.py
   ```

6. Open a pull request. CI runs the same checks, on ansible-core 2.14 through devel.

## Integration tests

Integration tests change real resources. Run them only against a **lab** croit cluster:

```bash
cp tests/integration/integration_config.yml.template tests/integration/integration_config.yml
ansible-test integration --allow-unsupported <target>
```

Anything destructive (OSD creation, writes to gateways, backups) is opt-in through the variables documented in the template.

## Commit messages

Use short, imperative subjects ("Add rbd_mirror schedule support"), with detail in the body when it helps.

## Code of conduct

This project follows the [Ansible Community Code of Conduct](CODE_OF_CONDUCT.md).
