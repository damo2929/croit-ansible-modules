# croit.ceph example playbooks

Ready-to-adapt playbooks for common croit operations. Each one is self-contained and parameterised through the `vars:` at its top. All of them are idempotent: run them as often as you like, and preview them with `--check --diff`.

| Playbook | What it does | Changes the cluster |
|---|---|---|
| [01_cluster_health.yml](01_cluster_health.yml) | Health gate: fails unless Ceph is healthy (ignoring `noout` and similar planned flags) | no |
| [02_cluster_report.yml](02_cluster_report.yml) | Writes a Markdown inventory report (servers, disks, pools, services, S3 users) to `reports/` | no |
| [03_rbd_vm_storage.yml](03_rbd_vm_storage.yml) | RBD for VMs: pool, tenant namespaces, disks, hourly snapshot schedule, hypervisor client key | yes |
| [04_cephfs_team_share.yml](04_cephfs_team_share.yml) | CephFS subvolume per team with a quota, exported over NFS | yes |
| [05_s3_tenant.yml](05_s3_tenant.yml) | S3 tenant: user with quotas, access key, versioned buckets, bucket policy | yes |
| [06_s3_key_rotation.yml](06_s3_key_rotation.yml) | Zero-downtime S3 key rotation in two phases | yes |
| [07_ceph_configuration.yml](07_ceph_configuration.yml) | Ceph options, cluster tuning, the balancer, a CRUSH rule | yes |
| [08_rolling_maintenance.yml](08_rolling_maintenance.yml) | Rolling reboot of storage nodes, one at a time, waiting for recovery; needs `-e rolling_reboot_confirm=true` | yes, **reboots nodes** |
| [09_access_management.yml](09_access_management.yml) | croit users, a CI API token (stored once, on creation), and server SSH keys | yes |
| [10_smb_share.yml](10_smb_share.yml) | SMB group, user and share on an existing SMB cluster | yes |
| [11_long_running_tasks.yml](11_long_running_tasks.yml) | Start a slow job with `wait: false`, then wait for its croit task later | yes |
| [12_ipv6_networking.yml](12_ipv6_networking.yml) | IPv6 / dual-stack: networks, node and VLAN addresses, an S3 virtual IP, NFS access for IPv6 clients (all in `2001:db8::/32`) | yes |

## Setup

1. Install the collection:

   ```bash
   ansible-galaxy collection install -r requirements.yml
   ```

2. Point the examples at your croit management node in [`group_vars/all/croit.yml`](group_vars/all/croit.yml), and list your clusters (and, for playbook 08, your storage nodes' croit hostnames) in [`inventory.yml`](inventory.yml).

3. Store the secrets in Ansible Vault:

   ```bash
   cp group_vars/all/vault.yml.example group_vars/all/vault.yml
   $EDITOR group_vars/all/vault.yml          # at least vault_croit_api_token
   ansible-vault encrypt group_vars/all/vault.yml
   ```

   Use a token with the `viewer` role for 01 and 02 and for any `--check` run, and an `admin` + `viewer` token for the rest.

## Running

Run these from this directory, so `ansible.cfg` and the inventory are picked up:

```bash
# Preview: only reads from croit, shows what would change
ansible-playbook 05_s3_tenant.yml --check --diff --ask-vault-pass

# Apply
ansible-playbook 05_s3_tenant.yml --ask-vault-pass

# Run it again: it should report changed=0
ansible-playbook 05_s3_tenant.yml --ask-vault-pass
```

Gate any change on cluster health by importing the health check first:

```yaml
- name: Health gate
  ansible.builtin.import_playbook: 01_cluster_health.yml

- name: The actual change
  ansible.builtin.import_playbook: 05_s3_tenant.yml
```

## Notes

- **Where they run:** the modules run on the Ansible controller (`ansible_connection: local`) and talk to croit over HTTPS. No SSH access to the storage nodes is needed.
- **Generated files:** `reports/`, `keyrings/` and `tokens/` are created next to the playbooks and are git-ignored. Keyrings and tokens are written with mode 0600.
- **Destructive operations:** these always need an explicit flag (`confirm_delete`, `confirm_wipe`, `confirm_action`). See the collection's [safety guide](../docs/docsite/rst/guide_safety.rst).
- **Validation:** every `croit.ceph` task here is checked against the real module options in CI (`tools/check_docs.py`), and the playbooks pass `ansible-lint --profile production`.
