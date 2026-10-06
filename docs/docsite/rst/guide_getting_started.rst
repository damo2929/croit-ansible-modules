.. _ansible_collections.croit.ceph.docsite.guide_getting_started:

Getting started with croit.ceph
===============================

The ``croit.ceph`` collection manages `croit <https://www.croit.io/>`_ Ceph clusters through the croit REST API. This guide covers installing the collection, creating an API token and running a first playbook.

.. contents::
   :local:
   :depth: 1

Requirements
------------

- ansible-core 2.14 or later. This is the version EL9 AppStream ships, so ``dnf install ansible-core`` is enough on RHEL, Rocky or Alma 9.
- Python 3.9 or later on the Ansible controller. No third-party Python libraries are needed.
- HTTPS access from the controller to the croit management node.

Installing the collection
-------------------------

.. code-block:: console

   $ ansible-galaxy collection install croit.ceph

Before the first Galaxy release, install from git:

.. code-block:: console

   $ ansible-galaxy collection install git+https://github.com/damo2929/croit-ansible-modules.git,main

Creating an API token
---------------------

The collection authenticates only with croit API tokens, which are sent as ``Authorization: Bearer <token>``. Create a token in the croit UI, or with :ansplugin:`croit.ceph.api_token#module` from an existing admin token. Pick its roles to match what the playbook does:

``viewer``
  Enough for every ``*_info`` module and for ``--check`` runs of any module.

``admin`` (together with ``viewer``)
  Needed to make changes.

Store the token in Ansible Vault:

.. code-block:: console

   $ ansible-vault encrypt_string --name vault_croit_token 'the-token'

Connecting
----------

The modules run on the Ansible controller. Point the play at ``localhost`` and set the connection options once with the ``croit.ceph.all`` action group:

.. code-block:: yaml+jinja

   - name: Manage croit
     hosts: localhost
     gather_facts: false
     module_defaults:
       group/croit.ceph.all:
         api_url: https://croit-mgmt/api
         api_token: "{{ vault_croit_token }}"
         validate_certs: true
     tasks:
       - name: Read the cluster status
         croit.ceph.cluster_info:
           gather: [status, version]
         register: cluster

       - name: Show the Ceph health
         ansible.builtin.debug:
           msg: "{{ (cluster.status.cephStatus | default({}, true)).health.status | default('unknown') }}"

Instead of setting ``api_url`` and ``api_token`` in the play, you can export the environment variables ``CROIT_API_URL`` and ``CROIT_API_TOKEN``.

A first change
--------------

.. code-block:: yaml+jinja

   - name: Replicated RBD pool
     croit.ceph.pool:
       name: rbd-vms
       application: rbd
       size: 3
       min_size: 2

Preview it first. In check mode the module only reads from croit:

.. code-block:: console

   $ ansible-playbook site.yml --check --diff

Run it for real, then run it again. The second run reports ``changed=0``.

Next steps
----------

- :ref:`ansible_collections.croit.ceph.docsite.guide_safety` explains how the modules decide what to change, and which flags guard destructive operations.
- :ref:`ansible_collections.croit.ceph.docsite.guide_tasks_and_warnings` covers croit's background tasks and its "are you sure?" warnings.
- :ref:`ansible_collections.croit.ceph.docsite.guide_secrets` covers keys, passwords and tokens.
