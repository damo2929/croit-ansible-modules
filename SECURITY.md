# Security Policy

## Reporting a vulnerability

**Please don't report security issues in public GitHub issues.**

Report them privately through [GitHub security advisories](https://github.com/damo2929/croit-ansible-modules/security/advisories/new), or by email to the maintainer listed in `galaxy.yml`. Include the affected version, steps to reproduce, and the impact.

You will get an acknowledgement within a few working days. Fixes are released as a patch version and noted under `security_fixes` in the changelog.

## Scope

In scope:

- secrets leaking into logs, diffs, return values or error messages;
- a module writing to croit in check mode;
- a destructive operation running without its `confirm_*` flag;
- TLS verification being skipped while `validate_certs` is true.

Vulnerabilities in croit or Ceph themselves should go to croit or the Ceph project.

## Supported versions

Until 1.0.0, only the latest release gets security fixes.
