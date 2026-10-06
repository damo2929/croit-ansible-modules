.. _ansible_collections.croit.ceph.docsite.guide_safety:

Idempotency, check mode and safety flags
========================================

Every ``croit.ceph`` module follows the same contract. Once you know it, every module behaves predictably.

.. contents::
   :local:
   :depth: 1

Read, compare, write
--------------------

Each run goes through these steps:

#. The module reads the current state from croit.
#. It builds the desired state from the options you set.
#. It sends write requests only for the fields that differ.

A resource that already matches gets no write requests at all, and the module reports ``changed=false``. Run the same playbook twice: the second run must report no changes. If it doesn't, that's a bug; please report it.

Options you leave out are left alone. ``state: absent`` removes a resource. Some list options replace their whole list only when you also set ``exclusive: true``, for example S3 keys, SSH keys, iSCSI mappings and NVMe-oF attachments.

Values are normalised before they're compared, so equivalent spellings don't cause changes:

- sizes such as ``100G`` or ``100GiB``;
- MAC addresses and CIDRs;
- list order, where it doesn't matter;
- the case of enum values;
- Ceph option names written with spaces or underscores.

Check mode and diff mode
------------------------

In check mode (``--check``) a module only sends **GET** requests. It never writes, never starts a croit task and never confirms a warning, and the shared module code refuses any write in check mode. It still returns the ``changed`` value and the diff a real run would produce.

With ``--diff`` each module returns ``before`` and ``after`` for the fields it manages, with secrets masked.

Fields that can't be changed
----------------------------

Some settings can only be set when a resource is created, for example:

- a pool's erasure-code profile;
- an RBD image's data pool;
- a subvolume's uid, gid and mode;
- an iSCSI portal's IP.

If you ask for a different value, the module fails with a clear message. It never deletes and recreates the resource for you.

Some options are only used at creation (for example ``device_class`` on :ansplugin:`croit.ceph.pool#module`), and an existing resource is never compared against them. Each module's documentation says which options are create-only.

Safety flags
------------

Operations that destroy data, take nodes down or can't be undone need an explicit flag. The flag is checked **before** anything is sent, in check mode too.

.. list-table::
   :header-rows: 1
   :widths: 25 40 35

   * - Flag
     - Needed for
     - Modules
   * - ``confirm_delete``
     - Deleting anything that destroys data or disconnects every client.
     - pool, rbd, rbd_snapshot, cephfs_volume, cephfs_subvolume_group, cephfs_subvolume, s3_bucket, s3_placement, server, server_nic, server_bond, server_vlan, service (MON/MDS), nfs_cluster, smb_cluster, iscsi_gateway, iscsi_disk, nvmeof_gateway, nvmeof_subsystem, nvmeof_disk
   * - ``confirm_wipe``
     - Creating or replacing an OSD, which erases the disk.
     - osd
   * - ``confirm_action``
     - Rebooting or shutting down a node; IPMI power off, power cycle and reboot to BIOS; S3 multisite convert, join and promote; the NFS implementation switch; the SMB DNS-name change and generation migration.
     - server, ipmi, s3_multisite, nfs_cluster, smb_cluster
   * - ``allow_management_ip_change``
     - Changing or deleting the interface that carries a node's management IP.
     - server_nic, server_bond, server_vlan
   * - ``delete_image``
     - Deleting the RBD image behind a gateway disk, not just the export.
     - iscsi_disk, nvmeof_disk
   * - ``purge_objects``
     - Deleting a bucket that still holds objects.
     - s3_bucket

Deletes that don't need a flag are the ones where no data is lost, or where croit itself refuses to remove a non-empty resource. Examples are RBD namespaces, S3 users that still own buckets, network definitions, NFS exports and SMB shares (croit keeps the data). Each module's documentation says what a removal affects.

Lockout protection
------------------

:ansplugin:`croit.ceph.user#module` and :ansplugin:`croit.ceph.api_token#module` refuse to delete, or remove the admin role from, the user or token that the playbook itself authenticates as.

One-shot actions
----------------

Some operations are actions, not states: restarting or rolling-restarting services, rebooting a node, re-detecting hardware, running a backup now, and the IPMI identify, power cycle and BIOS actions. Like ``ansible.builtin.service`` with ``state: restarted``, they always report ``changed=true`` and are skipped in check mode. Wherever croit exposes the state, the modules use declarative options instead (``state: started``, ``in: true``, ``power: on``), and those are idempotent.
