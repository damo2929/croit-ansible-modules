.. _ansible_collections.croit.ceph.docsite.guide_secrets:

Handling secrets
================

.. contents::
   :local:
   :depth: 1

Secret options
--------------

Options that carry secrets are marked ``no_log``, so Ansible masks them in its output and logs. These are:

- passwords;
- S3 secret keys;
- iSCSI CHAP secrets;
- NVMe-oF DH-HMAC-CHAP keys;
- AD join credentials;
- registry passwords;
- multisite and mirroring bootstrap tokens;
- webhook URLs.

They never appear in diffs, where a changed secret shows as ``******** (changed)``.

Secrets that can't be read back
-------------------------------

croit doesn't return some secrets, so the module can't tell whether they match. For these, the modules follow the ``ansible.builtin.user`` pattern:

``update_password: on_create`` (the default)
  Send the secret only when the resource is created.

``update_password: always``
  Send it on every run. The module then always reports ``changed``.

Modules: :ansplugin:`croit.ceph.user#module`, :ansplugin:`croit.ceph.smb_user#module`, :ansplugin:`croit.ceph.iscsi_client#module`, :ansplugin:`croit.ceph.image_config#module`, and :ansplugin:`croit.ceph.config_backup#module` (``update_secret``) and :ansplugin:`croit.ceph.nvmeof_host#module` (``update_shared_key``). Where croit does return the stored secret to an admin token, the module compares it directly and still never shows it.

Secrets the modules return
--------------------------

Some secrets are returned, but only on request or only once. Set ``no_log: true`` on these tasks, because Ansible can't mask a value it returns.

.. list-table::
   :header-rows: 1

   * - Module
     - What is returned
     - When
   * - :ansplugin:`croit.ceph.api_token#module`
     - ``token``, the new API token
     - only on the run that creates the token; croit can't show it again
   * - :ansplugin:`croit.ceph.ceph_key#module`
     - ``keyring``
     - with ``return_keyring: true``
   * - :ansplugin:`croit.ceph.ceph_key_info#module`
     - the key secrets
     - with ``show_secrets: true``
   * - :ansplugin:`croit.ceph.s3_multisite#module`, :ansplugin:`croit.ceph.rbd_mirror#module`
     - a bootstrap token
     - with ``return_token: true``
   * - :ansplugin:`croit.ceph.config_backup#module`
     - the backup encryption key
     - with ``return_encryption_key: true``
   * - :ansplugin:`croit.ceph.iscsi_info#module`, :ansplugin:`croit.ceph.nvmeof_info#module`
     - CHAP passwords and host keys
     - with ``show_secrets: true``

.. code-block:: yaml+jinja

   - name: API token for a CI pipeline
     croit.ceph.api_token:
       name: ci-pipeline
       roles: [admin, viewer]
     register: ci_token
     no_log: true

The connection token
--------------------

Keep ``api_token`` in Ansible Vault, or pass it through ``CROIT_API_TOKEN``. Error messages never include request URLs with query strings, because some croit endpoints take secrets as query parameters.
