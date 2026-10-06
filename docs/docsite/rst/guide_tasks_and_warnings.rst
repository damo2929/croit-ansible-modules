.. _ansible_collections.croit.ceph.docsite.guide_tasks_and_warnings:

Background tasks and croit warnings
===================================

.. contents::
   :local:
   :depth: 1

Background tasks
----------------

Many croit changes run as background tasks: creating pools, deploying services, creating OSDs, downloading images and more. Modules that can start a task have two options:

``wait`` (default ``true``)
  Wait for the task to end. If it fails or is cancelled, the Ansible task fails and shows the tail of croit's task output. After the task ends, the module reads the resource again, so the result reflects reality.

``wait_timeout`` (default ``600`` seconds)
  How long to wait.

With ``wait: false`` the module returns as soon as croit accepts the change, and puts the task in the ``task`` return value. Use :ansplugin:`croit.ceph.task#module` to wait for it later:

.. code-block:: yaml+jinja

   - name: Start a long job
     croit.ceph.pool:
       name: archive
       erasure_coding: true
       data_chunks: 8
       parity_chunks: 3
       wait: false
     register: created

   - name: Wait for it
     croit.ceph.task:
       task_id: "{{ created.task.id }}"
       wait_timeout: 3600
     when: created.task is defined

:ansplugin:`croit.ceph.task_info#module` lists the tasks that are still running.

Tasks that ask a question
~~~~~~~~~~~~~~~~~~~~~~~~~

Some croit tasks stop to ask the operator something, for example whether to go ahead when stopping OSDs would make placement groups inactive. A module never answers on your behalf. It fails and shows the question and the possible answers. Answer it in the croit UI, or with :ansplugin:`croit.ceph.task#module`:

.. code-block:: yaml+jinja

   - name: Confirm the question
     croit.ceph.task:
       task_id: 512
       action: answer
       answer: "Yes"

croit's warnings
----------------

croit refuses some risky changes with a warning that has to be confirmed, for example changing a pool's application or removing the last MDS. By default the module fails and shows croit's warning text. Set ``ignore_warnings: true`` to confirm the warning and go ahead:

.. code-block:: yaml+jinja

   - name: Change the application of a pool (croit warns that metadata is removed)
     croit.ceph.pool:
       name: scratch
       application: cephfs
       ignore_warnings: true

Warnings are never confirmed in check mode. If an explicit safety flag already covers the same risk (for example ``confirm_delete: true`` on :ansplugin:`croit.ceph.cephfs_volume#module`), the flag also confirms croit's matching warning.

Errors
------

A request croit refuses fails the task, with croit's message, the HTTP status and croit's details. HTTP 401 means the API token was rejected. HTTP 403 means the token lacks a role: changes need ``admin``.
