#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

# croit-api: GET /gateways/smb
# croit-api: GET /services/smb/{serviceId}
# croit-api: POST /services/smb
# croit-api: POST /services/smb/active-directory-authentication
# croit-api: PATCH /services/smb/{serviceId}
# croit-api: DELETE /services/smb/{serviceId}
# croit-api: POST /services/smb/{serviceId}/servers
# croit-api: DELETE /services/smb/{serviceId}/servers/{serverId}
# croit-api: POST /services/smb/{serviceId}/service-dns-name
# croit-api: POST /services/smb/{serviceId}/migrate-generation
# croit-api: GET /servers
# croit-api: GET /servers/{serverId}/nics

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
module: smb_cluster
short_description: Manage SMB gateway clusters on a croit cluster
version_added: 0.1.0
description:
  - Create, update and delete croit SMB gateway clusters, either with managed local users (O(type=simple))
    or joined to an Active Directory domain (O(type=active_directory)).
  - croit SMB clusters have no name of their own. This module identifies a cluster by O(name), which croit
    stores as the cluster's description, so it must be unique.
  - Options that are not set keep their current value. Options that only apply to the other O(type) fail the task.
  - O(type), O(domain), O(netbios_domain_name) and O(volume) are create-only; a different O(type), O(domain) or
    O(netbios_domain_name) for an existing cluster fails the task instead of recreating it.
  - Deleting a cluster needs O(confirm_delete=true), and disruptive changes (migration to generation 2, a new
    O(service_dns_name)) need O(confirm_action=true).
  - Shares, managed local users and groups are managed with M(croit.ceph.smb_share), M(croit.ceph.smb_user)
    and M(croit.ceph.smb_group).
author:
  - Damien Dye (@damo2929)
extends_documentation_fragment:
  - croit.ceph.croit
  - croit.ceph.croit.attributes
  - croit.ceph.croit.wait
  - croit.ceph.croit.warnings
attributes:
  check_mode:
    support: full
  diff_mode:
    support: full
options:
  name:
    description:
      - Name of the cluster, stored by croit as its description. Must be unique among SMB clusters.
      - A numeric value that matches no description is looked up as croit's service id.
    type: str
    required: true
  state:
    description:
      - Whether the cluster should exist.
      - V(absent) stops samba on every member and removes the cluster, and needs O(confirm_delete=true).
        The exported CephFS directories and their data stay.
    type: str
    choices: [present, absent]
    default: present
  type:
    description:
      - Kind of cluster. V(simple) clusters authenticate managed local users; V(active_directory) clusters
        are joined to an Active Directory domain.
      - Defaults to V(simple) when the cluster is created. Cannot be changed afterwards.
    type: str
    choices: [simple, active_directory]
  servers:
    description:
      - The complete list of member servers. Servers not listed are taken out of the cluster; an empty list is
        refused (use O(state=absent) instead).
      - Required when the cluster is created. Adding a member to an V(active_directory) cluster needs
        O(domain_admin_user) and O(domain_admin_password).
      - The interface and VLAN of an existing member cannot be changed; remove the server and add it again.
    type: list
    elements: dict
    suboptions:
      server:
        description:
          - Hostname or numeric croit id of the server.
        type: str
        required: true
      nic:
        description:
          - Interface the virtual IPs are bound on, by croit NIC name, Linux interface name, MAC address or croit id.
          - When not set, no interface is sent and croit picks one.
        type: str
      vlan:
        description:
          - VLAN tag on that interface, when the virtual IPs are bound on a VLAN. The VLAN must exist on O(servers[].nic).
        type: int
  virtual_ips:
    description:
      - Virtual IPs croit distributes across the healthy members. Compared as a set, after normalising the
        address notation.
      - Required when the cluster is created. When not set on an existing cluster, the virtual IPs are left alone.
    type: list
    elements: str
  volume:
    description:
      - CephFS volume the cluster serves. croit uses the default filesystem when not set.
      - Only used when the cluster is created.
    type: str
  ceph_snapshots:
    description:
      - Whether to expose CephFS snapshots as Windows "Previous Versions". Needs Samba 4.24.4 or later on every member.
      - croit disables it when a cluster is created without it.
    type: bool
  global_parameters:
    description:
      - Additional C(smb.conf) C([global]) parameters. Replaces the stored set; V({}) removes every
        additional line. Generation-2 clusters only.
    type: dict
  share_defaults:
    description:
      - Advanced configuration every share of the cluster renders. Only the sub-options that are set are
        managed. Generation-2 clusters only.
    type: dict
    suboptions:
      parameters:
        description:
          - Additional C(smb.conf) parameters of every share, as key/value pairs.
        type: dict
      vfs_objects:
        description:
          - Additional VFS modules stacked after the ones croit manages, in this order.
        type: list
        elements: str
      vfs_objects_before:
        description:
          - Additional VFS modules stacked ahead of the ones croit manages, in this order.
        type: list
        elements: str
  initial_users:
    description:
      - Managed local users created together with a V(simple) cluster. croit needs at least one.
      - Only used when the cluster is created; manage users afterwards with M(croit.ceph.smb_user).
    type: list
    elements: dict
    suboptions:
      username:
        description:
          - Lowercase POSIX user name.
        type: str
        required: true
      password:
        description:
          - Initial SMB password. It is never returned or shown in diffs.
        type: str
      uid:
        description:
          - Unix uid of the user. croit derives one when not set.
        type: int
  domain:
    description:
      - Active Directory domain (realm), for example V(MY-ORG.LOCAL). Required to create an
        V(active_directory) cluster. Cannot be changed afterwards.
    type: str
  netbios_domain_name:
    description:
      - NetBIOS domain name, for example V(MY-ORG). Required to create an V(active_directory) cluster.
        Cannot be changed afterwards.
    type: str
  domain_controller:
    description:
      - Host name of the domain controller. Required to create an V(active_directory) cluster.
    type: str
  dns_servers:
    description:
      - DNS servers the members resolve names with, in this order. V([]) uses the DHCP-provided ones.
      - V(active_directory) clusters only.
    type: list
    elements: str
  service_dns_name:
    description:
      - Service DNS name, used as the NetBIOS name clients reach the cluster by. V(active_directory) only.
      - Changing it on an existing cluster joins the domain again under a new computer account. That
        interrupts clients, so it needs O(confirm_action=true) and the O(domain_admin_user) and
        O(domain_admin_password) credentials.
    type: str
  organizational_unit:
    description:
      - DN of the organizational unit for the machine accounts, for example
        V(OU=Gateways,DC=my-org,DC=local). AD's default Computers container when not set.
      - Only used when the cluster is created or migrated to generation 2; croit reports it in a
        different notation, so it is not compared.
    type: str
  customize_idmap:
    description:
      - Make Linux user ids consistent with external systems (custom winbind idmap). Unlocks POSIX-ACL
        shares. V(active_directory) only.
      - Fixed at creation, except when migrating to generation 2.
    type: bool
  idmap_configs:
    description:
      - Per-domain winbind idmap blocks, honoured when O(customize_idmap=true).
      - Only used when the cluster is created or migrated to generation 2; not compared afterwards.
    type: list
    elements: dict
    suboptions:
      domain:
        description:
          - Domain the block applies to, or V(*) for the default block.
        type: str
        required: true
      backend:
        description:
          - Winbind idmap backend, for example V(rid) or V(autorid).
        type: str
        required: true
      options:
        description:
          - Backend options such as C(range), as key/value pairs. Values are sent as strings.
        type: dict
  domain_admin_user:
    description:
      - Domain administrator used to join members to the domain. Used when the cluster is created, when
        a member is added and when O(service_dns_name) changes. Never stored by croit.
    type: str
  domain_admin_password:
    description:
      - Password of O(domain_admin_user). Never stored by croit, never returned or shown in diffs.
    type: str
  generation:
    description:
      - Configuration generation the cluster should run. Generation 1 is the legacy template; generation 2
        brings managed local users, share options and on-disk ACLs.
      - V(2) on a generation-1 cluster (or one whose migration was interrupted) migrates it in one
        downtime window, in which the cluster restarts and every share's ACL is rebuilt. That needs
        O(confirm_action=true). A cluster cannot go back to generation 1.
      - Only for existing clusters; new clusters always get croit's current generation, and setting it on create
        fails the task.
    type: int
    choices: [2]
  migrate_posix_shares:
    description:
      - Names of the shares to switch to POSIX-ACL mode while migrating to generation 2; the others stay
        Windows-ACL. Only used during the migration.
    type: list
    elements: str
  confirm_action:
    description:
      - Must be V(true) for disruptive one-off changes, which interrupt clients - migrating to
        generation 2 and changing O(service_dns_name).
      - Not needed for any other change.
    type: bool
    default: false
  confirm_delete:
    description:
      - Must be V(true) for O(state=absent) to remove an existing cluster. This also confirms croit's
        warning about removing a cluster with several members.
    type: bool
    default: false
notes:
  - Passwords are write-only. They are sent when they are needed and never compared, returned or shown
    in diffs. Set C(no_log) on tasks that pass them.
  - Removing a cluster or a member disconnects the SMB clients served by it; the CephFS data stays.
  - The fixed C(root)/C(croit-ro) passwords of legacy generation-1 clusters are not managed; migrate the
    cluster to generation 2 instead.
  - With O(wait=false), RV(cluster) is empty after a create, because croit lists the cluster only once its task ran.
  - The cluster's name is croit's description, and croit is assumed to keep it verbatim. This follows the croit API
    reference and has not yet been verified against a live croit cluster.
seealso:
  - module: croit.ceph.smb_share
    description: Manage the shares of an SMB cluster.
  - module: croit.ceph.smb_user
    description: Manage the local users of a simple SMB cluster.
  - module: croit.ceph.smb_group
    description: Manage the local groups of a simple SMB cluster.
  - module: croit.ceph.smb_info
    description: Read SMB clusters, shares, users and groups.
  - name: croit API reference
    description: The croit REST API this module uses (SMB gateways).
    link: https://www.croit.io/api-docs
  - name: Ceph SMB manager module
    description: Upstream Ceph documentation on serving CephFS over SMB.
    link: https://docs.ceph.com/en/latest/mgr/smb/
  - name: smb.conf reference
    description: Samba's documentation of the parameters accepted by O(global_parameters) and O(share_defaults).
    link: https://www.samba.org/samba/docs/current/man-html/smb.conf.5.html
"""

EXAMPLES = r"""
# All examples assume api_url and api_token are set with module_defaults for group/croit.ceph.all (see the collection README).

- name: Create an SMB cluster with managed local users
  croit.ceph.smb_cluster:
    name: smb-office
    type: simple
    servers:
      - server: node1
        nic: eth0
      - server: node2
        nic: eth0
    virtual_ips: [10.0.0.200/24, 10.0.0.201/24]
    initial_users:
      - username: admin
        password: "{{ vault_smb_admin_password }}"
  no_log: true

- name: Create an SMB cluster joined to Active Directory
  croit.ceph.smb_cluster:
    name: smb-ad
    type: active_directory
    servers:
      - server: node1
        nic: eth0
    virtual_ips: [10.0.0.210/24]
    domain: MY-ORG.LOCAL
    netbios_domain_name: MY-ORG
    domain_controller: dc01
    service_dns_name: files
    domain_admin_user: Administrator
    domain_admin_password: "{{ vault_ad_password }}"
  no_log: true

- name: Add a third virtual IP and enable Previous Versions
  croit.ceph.smb_cluster:
    name: smb-office
    virtual_ips: [10.0.0.200/24, 10.0.0.201/24, 10.0.0.202/24]
    ceph_snapshots: true
  register: smb

- name: Show the members and their health
  ansible.builtin.debug:
    msg: "{{ smb.cluster.servers | map(attribute='healthy') | list }}"

- name: Migrate a legacy cluster to generation 2 (restarts it)
  croit.ceph.smb_cluster:
    name: smb-legacy
    generation: 2
    migrate_posix_shares: [scratch]
    confirm_action: true

- name: Remove a cluster (the shared data stays)
  croit.ceph.smb_cluster:
    name: smb-office
    state: absent
    confirm_delete: true
"""

RETURN = r"""
cluster:
  description:
    - The cluster as croit reports it after the change - the C(SmbGatewayConfigResponse) list entry merged
      with the C(SmbGatewayServiceResponse) detail (servers and shares).
    - In check mode the cluster before the change. Empty when the cluster does not exist or was removed, and after a
      create with O(wait=false).
  returned: always
  type: dict
  contains:
    serviceId:
      description: croit's id of the SMB service.
      returned: when the cluster exists
      type: int
      sample: 52
    description:
      description: The cluster's name (O(name)).
      returned: when the cluster exists
      type: str
      sample: smb-office
    type:
      description: croit's cluster type, V(simple) or V(active-directory).
      returned: when the cluster exists
      type: str
      sample: simple
    configGeneration:
      description: Configuration generation; V(1) is the legacy template, V(2) or later the current one.
      returned: when the cluster exists
      type: int
      sample: 2
    migrationInProgress:
      description: Whether a generation-2 migration was interrupted and can be resumed with O(generation=2).
      returned: when the cluster exists
      type: bool
      sample: false
    virtualIps:
      description: The cluster's virtual IPs.
      returned: when the cluster exists
      type: list
      elements: str
      sample: [10.0.0.200/24, 10.0.0.201/24]
    cephSnapshots:
      description: Whether CephFS snapshots are exposed as "Previous Versions".
      returned: when the cluster exists
      type: bool
      sample: true
    globalParameters:
      description: Additional C(smb.conf) C([global]) parameters.
      returned: when the cluster exists
      type: dict
      sample: {"server min protocol": SMB3}
    shareDefaults:
      description: Advanced configuration every share renders, with C(parameters), C(vfsObjects) and C(vfsObjectsBefore).
      returned: when the cluster exists
      type: dict
      sample: {parameters: {}, vfsObjects: [], vfsObjectsBefore: []}
    servers:
      description: The members, each with C(server) (croit id), C(nic), C(vlan), C(ip), C(virtualIps) and C(healthy).
      returned: when the cluster exists
      type: list
      elements: dict
      sample: [{server: 1, nic: eth0, vlan: null, ip: 10.0.0.11, virtualIps: [10.0.0.200/24], healthy: true}]
    shares:
      description: The cluster's shares (C(SmbGatewayShareResponse)); see M(croit.ceph.smb_share).
      returned: when the cluster exists
      type: list
      elements: dict
      sample: [{id: 3, share: projects, path: /volumes/_nogroup/projects, aclMode: windows}]
    domain:
      description: Active Directory realm.
      returned: for V(active_directory) clusters
      type: str
      sample: MY-ORG.LOCAL
    serviceDnsName:
      description: The service DNS name clients reach the cluster by.
      returned: for V(active_directory) clusters
      type: str
      sample: files
task:
  description: The last croit background task the change ran as.
  returned: when a task ran
  type: dict
  contains:
    id:
      description: croit's task id.
      returned: always
      type: int
      sample: 618
    name:
      description: What the task did.
      returned: always
      type: str
      sample: Create SMB cluster
    state:
      description: Final state of the task, one of C(FINISHED), C(FAILED), C(CANCELED), or C(RUNNING) with O(wait=false).
      returned: always
      type: str
      sample: FINISHED
    output:
      description: The task's transcript.
      returned: always
      type: str
      sample: "Configuring samba on node1 ... done"
tasks:
  description:
    - Every croit background task the change ran, in order, for example a migration followed by a member addition.
      Each entry has the same fields as RV(task).
  returned: when a task ran
  type: list
  elements: dict
  sample: [{id: 617, name: Migrate SMB cluster, state: FINISHED}, {id: 618, name: Add SMB server, state: FINISHED}]
"""

from ansible_collections.croit.ceph.plugins.module_utils.client import path_join
from ansible_collections.croit.ceph.plugins.module_utils.lookup import list_servers, require_server, resolve_interface
from ansible_collections.croit.ceph.plugins.module_utils.module import CroitModule
from ansible_collections.croit.ceph.plugins.module_utils.smb import (
    OPTIONS_SPEC,
    TYPE_AD,
    TYPE_SIMPLE,
    TYPES,
    cluster_detail,
    find_cluster,
    generation,
    list_clusters,
    merge_options,
    normalise_ip,
    options_request,
    options_view,
)

AD_OPTIONS = (
    "domain",
    "netbios_domain_name",
    "domain_controller",
    "dns_servers",
    "service_dns_name",
    "customize_idmap",
    "idmap_configs",
    "organizational_unit",
    "domain_admin_user",
    "domain_admin_password",
)


def vip_set(values):
    return sorted(set(normalise_ip(v) for v in values or []))


class SmbClusterModule(CroitModule):
    def __init__(self):
        super(SmbClusterModule, self).__init__(
            dict(
                name=dict(type="str", required=True),
                state=dict(type="str", default="present", choices=["present", "absent"]),
                type=dict(type="str", choices=list(TYPES)),
                servers=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        server=dict(type="str", required=True),
                        nic=dict(type="str"),
                        vlan=dict(type="int"),
                    ),
                ),
                virtual_ips=dict(type="list", elements="str"),
                volume=dict(type="str"),
                ceph_snapshots=dict(type="bool"),
                global_parameters=dict(type="dict"),
                share_defaults=dict(type="dict", options=OPTIONS_SPEC),
                initial_users=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        username=dict(type="str", required=True),
                        password=dict(type="str", no_log=True),
                        uid=dict(type="int"),
                    ),
                ),
                domain=dict(type="str"),
                netbios_domain_name=dict(type="str"),
                domain_controller=dict(type="str"),
                dns_servers=dict(type="list", elements="str"),
                service_dns_name=dict(type="str"),
                organizational_unit=dict(type="str"),
                customize_idmap=dict(type="bool"),
                idmap_configs=dict(
                    type="list",
                    elements="dict",
                    options=dict(
                        domain=dict(type="str", required=True),
                        backend=dict(type="str", required=True),
                        options=dict(type="dict"),
                    ),
                ),
                domain_admin_user=dict(type="str"),
                domain_admin_password=dict(type="str", no_log=True),
                generation=dict(type="int", choices=[2]),
                migrate_posix_shares=dict(type="list", elements="str"),
                confirm_action=dict(type="bool", default=False),
                confirm_delete=dict(type="bool", default=False),
            ),
        )
        self.tasks = []
        self._servers = None

    # Lookups --------------------------------------------------------------

    @property
    def all_servers(self):
        if self._servers is None:
            self._servers = list_servers(self)
        return self._servers

    def hostname(self, server_id):
        for server in self.all_servers:
            if server.get("id") == server_id:
                return server.get("hostname")
        return str(server_id)

    def resolve_member(self, member):
        """A servers entry -> dict(server id, hostname, nic id, nic name, vlan tag)."""
        server = require_server(self, member["server"], self.all_servers)
        resolved = dict(server=server["id"], hostname=server["hostname"], nic=None, nic_name=None, vlan=member["vlan"])
        if member["nic"] is not None:
            # SMB members carry the VLAN tag itself; resolve_interface only checks it exists.
            server, nic, _vlan_id = resolve_interface(self, server["id"], member["nic"], member["vlan"], servers=self.all_servers)
            resolved["nic"] = nic["id"]
            resolved["nic_name"] = nic.get("name")
        return resolved

    def find(self):
        config = find_cluster(self, self.params["name"], list_clusters(self))
        if config is None:
            return None, None
        return config, cluster_detail(self, config["serviceId"]) or {}

    # Views ----------------------------------------------------------------

    def member_view(self, member):
        return dict(server=self.hostname(member.get("server")), nic=member.get("nic"), vlan=member.get("vlan"))

    def view(self, config, detail):
        if not config:
            return {}
        view = dict(
            type=next((k for k, v in TYPES.items() if v == config.get("type")), config.get("type")),
            servers=sorted((self.member_view(m) for m in detail.get("servers") or []), key=lambda m: m["server"] or ""),
            virtual_ips=vip_set(config.get("virtualIps")),
            ceph_snapshots=bool(config.get("cephSnapshots")),
            global_parameters=dict(config.get("globalParameters") or {}),
            share_defaults=options_view(config.get("shareDefaults")),
            generation=generation(config),
        )
        if config.get("type") == TYPE_AD:
            view.update(
                domain=config.get("domain"),
                netbios_domain_name=config.get("netbiosDomainName"),
                domain_controller=config.get("domainController"),
                dns_servers=list(config.get("dnsServers") or []),
                service_dns_name=config.get("serviceDnsName"),
                customize_idmap=bool(detail.get("customizeIdmap")),
            )
        return view

    def result_cluster(self, config, detail):
        if not config:
            return {}
        merged = dict(config)
        merged.update(detail or {})
        return merged

    # Validation -----------------------------------------------------------

    def validate(self, kind):
        p = self.params
        if kind == TYPE_SIMPLE:
            bad = [o for o in AD_OPTIONS if p[o] is not None]
            if bad:
                self.module.fail_json(msg="%s only apply to active_directory clusters" % ", ".join(bad))
        elif p["initial_users"] is not None:
            self.module.fail_json(msg="initial_users only apply to simple clusters")
        if p["servers"] is not None and not p["servers"]:
            self.module.fail_json(msg="servers must list at least one server; use state=absent to remove the cluster")
        if p["servers"]:
            names = [m["server"] for m in p["servers"]]
            if len(set(names)) != len(names):
                self.module.fail_json(msg="servers lists a server more than once")

    def need_admin_credentials(self, why):
        p = self.params
        if not p["domain_admin_user"] or not p["domain_admin_password"]:
            self.module.fail_json(msg="domain_admin_user and domain_admin_password are needed to %s" % why)

    # Main -----------------------------------------------------------------

    def run(self):
        config, detail = self.find()
        if self.params["state"] == "absent":
            return self.absent(config, detail)
        if config is None:
            return self.create()
        return self.update(config, detail)

    def finish(self, changed, before, after, cluster):
        result = dict(changed=changed, before=before, after=after, cluster=cluster)
        if self.tasks:
            result["tasks"] = self.tasks
            result["task"] = self.tasks[-1]
        self.exit(**result)

    def run_write(self, method, path, body=None, **kwargs):
        task = self.handle_task(self.write(method, path, body=body, **kwargs))
        if task is not None:
            self.tasks.append(task)
        return task

    def absent(self, config, detail):
        if config is None:
            self.exit(changed=False, cluster={})
        if not self.params["confirm_delete"]:
            self.module.fail_json(
                msg="Refusing to remove SMB cluster %r without confirm_delete=true" % config.get("description")
            )
        before = self.view(config, detail)
        if not self.check_mode:
            self.run_write("DELETE", path_join("services", "smb", config["serviceId"]), confirm_warnings=True)
        self.finish(True, before, {}, {})

    def create(self):
        p = self.params
        kind = TYPES[p["type"] or "simple"]
        self.validate(kind)
        missing = [o for o in ("servers", "virtual_ips") if p[o] is None]
        if kind == TYPE_AD:
            missing += [o for o in ("domain", "netbios_domain_name", "domain_controller") if not p[o]]
        if missing:
            self.module.fail_json(msg="Creating SMB cluster %r needs %s" % (p["name"], ", ".join(missing)))
        if kind == TYPE_AD:
            self.need_admin_credentials("join the members to the domain")
        if p["generation"] is not None:
            self.module.fail_json(msg="generation only applies to an existing cluster; new clusters get croit's current generation")

        members = [self.resolve_member(m) for m in p["servers"]]
        servers_body = []
        for m in members:
            entry = dict(server=m["server"], nic=m["nic"], vlan=m["vlan"])
            if kind == TYPE_AD:
                entry.update(domainAdminUser=p["domain_admin_user"], domainAdminPassword=p["domain_admin_password"])
            servers_body.append(entry)
        body = dict(
            description=p["name"],
            servers=servers_body,
            virtualIps=list(p["virtual_ips"]),
            shares=[],
        )
        if p["volume"] is not None:
            body["fsName"] = p["volume"]
        if p["ceph_snapshots"] is not None:
            body["cephSnapshots"] = p["ceph_snapshots"]
        if p["global_parameters"] is not None:
            body["globalParameters"] = dict((k, str(v)) for k, v in p["global_parameters"].items())
        defaults = options_view(None)
        if p["share_defaults"]:
            defaults = merge_options(defaults, p["share_defaults"])[0]
            body["shareDefaults"] = options_request(defaults)
        if kind == TYPE_SIMPLE:
            body["users"] = [
                dict((k, v) for k, v in dict(username=u["username"], password=u["password"], uid=u["uid"]).items() if v is not None)
                for u in p["initial_users"] or []
            ]
            path = "/services/smb"
        else:
            body.update(
                domain=p["domain"],
                netbiosDomainName=p["netbios_domain_name"],
                domainController=p["domain_controller"],
                dnsServers=list(p["dns_servers"] or []),
            )
            for opt, api in (("service_dns_name", "serviceDnsName"), ("organizational_unit", "organizationalUnit"), ("customize_idmap", "customizeIdmap")):
                if p[opt] is not None:
                    body[api] = p[opt]
            if p["idmap_configs"] is not None:
                body["idmapConfigs"] = [
                    dict(domain=c["domain"], backend=c["backend"], options=dict((k, str(v)) for k, v in (c["options"] or {}).items()))
                    for c in p["idmap_configs"]
                ]
            path = "/services/smb/active-directory-authentication"

        after = dict(
            type=next(k for k, v in TYPES.items() if v == kind),
            servers=sorted((dict(server=m["hostname"], nic=m["nic_name"], vlan=m["vlan"]) for m in members), key=lambda m: m["server"]),
            virtual_ips=vip_set(p["virtual_ips"]),
            ceph_snapshots=bool(p["ceph_snapshots"]),
            global_parameters=dict((k, str(v)) for k, v in (p["global_parameters"] or {}).items()),
            share_defaults=defaults,
        )
        if kind == TYPE_AD:
            after.update(
                domain=p["domain"],
                netbios_domain_name=p["netbios_domain_name"],
                domain_controller=p["domain_controller"],
                dns_servers=list(p["dns_servers"] or []),
                service_dns_name=p["service_dns_name"],
                customize_idmap=bool(p["customize_idmap"]),
            )
        if self.check_mode:
            self.finish(True, {}, after, {})

        self.run_write("POST", path, body=body)
        config, detail = self.find() if p["wait"] else (None, None)
        self.finish(True, {}, after, self.result_cluster(config, detail))

    def update(self, config, detail):
        p = self.params
        kind = config.get("type")
        if p["type"] is not None and TYPES[p["type"]] != kind:
            self.module.fail_json(
                msg="SMB cluster %r is %s and cannot be changed to %s; create a new cluster instead"
                % (config.get("description"), kind, p["type"])
            )
        self.validate(kind)
        for opt, api in (("domain", "domain"), ("netbios_domain_name", "netbiosDomainName")):
            if p[opt] is not None and p[opt] != config.get(api):
                self.module.fail_json(
                    msg="%s of SMB cluster %r is %r and cannot be changed to %r" % (opt, config.get("description"), config.get(api), p[opt])
                )
        migrating = p["generation"] == 2 and (generation(config) < 2 or config.get("migrationInProgress"))
        if p["customize_idmap"] is not None and not migrating and bool(p["customize_idmap"]) != bool(detail.get("customizeIdmap")):
            self.module.fail_json(
                msg="customize_idmap of SMB cluster %r is fixed at creation (it can only change while migrating to generation 2)"
                % config.get("description")
            )
        gen2 = generation(config) >= 2 or migrating
        if not gen2 and (p["global_parameters"] is not None or p["share_defaults"] is not None):
            self.module.fail_json(msg="global_parameters and share_defaults need a generation-2 cluster; set generation=2 to migrate it")

        before = self.view(config, detail)
        after = dict(before)
        patch = {}

        if p["virtual_ips"] is not None and vip_set(p["virtual_ips"]) != before["virtual_ips"]:
            patch["virtualIps"] = list(p["virtual_ips"])
            after["virtual_ips"] = vip_set(p["virtual_ips"])
        if p["ceph_snapshots"] is not None and p["ceph_snapshots"] != before["ceph_snapshots"]:
            patch["cephSnapshots"] = p["ceph_snapshots"]
            after["ceph_snapshots"] = p["ceph_snapshots"]
        if p["global_parameters"] is not None:
            wanted = dict((k, str(v)) for k, v in p["global_parameters"].items())
            if wanted != before["global_parameters"]:
                patch["globalParameters"] = wanted
                after["global_parameters"] = wanted
        if p["share_defaults"] is not None:
            merged, differs = merge_options(before["share_defaults"], p["share_defaults"])
            if differs:
                patch["shareDefaults"] = options_request(merged)
                after["share_defaults"] = merged
        if kind == TYPE_AD:
            if p["domain_controller"] is not None and p["domain_controller"] != before["domain_controller"]:
                patch["domainController"] = p["domain_controller"]
                after["domain_controller"] = p["domain_controller"]
            if p["dns_servers"] is not None and list(p["dns_servers"]) != before["dns_servers"]:
                patch["dnsServers"] = list(p["dns_servers"])
                after["dns_servers"] = list(p["dns_servers"])

        # Members: add the missing ones, remove the unlisted ones.
        to_add, to_remove = [], []
        if p["servers"] is not None:
            current = dict((m.get("server"), m) for m in detail.get("servers") or [])
            desired = [self.resolve_member(m) for m in p["servers"]]
            for m in desired:
                existing = current.get(m["server"])
                if existing is None:
                    to_add.append(m)
                    continue
                if m["nic_name"] is not None and m["nic_name"] != existing.get("nic") or (
                    m["vlan"] is not None and m["vlan"] != existing.get("vlan")
                ):
                    self.module.fail_json(
                        msg="Server %s is a member of SMB cluster %r on %s%s; the interface of a member cannot be changed. "
                        "Remove the server from servers, then add it back."
                        % (
                            m["hostname"],
                            config.get("description"),
                            existing.get("nic"),
                            " VLAN %s" % existing.get("vlan") if existing.get("vlan") is not None else "",
                        )
                    )
            wanted_ids = set(m["server"] for m in desired)
            to_remove = [sid for sid in current if sid not in wanted_ids]
            if to_add or to_remove:
                after["servers"] = sorted(
                    [self.member_view(current[sid]) for sid in current if sid in wanted_ids]
                    + [dict(server=m["hostname"], nic=m["nic_name"], vlan=m["vlan"]) for m in to_add],
                    key=lambda m: m["server"] or "",
                )
            if to_add and kind == TYPE_AD:
                self.need_admin_credentials("join the new members to the domain")

        dns_change = kind == TYPE_AD and p["service_dns_name"] is not None and p["service_dns_name"] != before["service_dns_name"]
        if dns_change:
            if not p["confirm_action"]:
                self.module.fail_json(
                    msg="Changing service_dns_name of SMB cluster %r re-joins the domain and interrupts clients; "
                    "set confirm_action=true to do it" % config.get("description")
                )
            self.need_admin_credentials("join the domain under the new service DNS name")
            after["service_dns_name"] = p["service_dns_name"]

        migration = None
        if migrating:
            if not p["confirm_action"]:
                self.module.fail_json(
                    msg="Migrating SMB cluster %r to generation 2 restarts it and rebuilds every share's ACL; "
                    "set confirm_action=true to do it" % config.get("description")
                )
            migration = {}
            if p["customize_idmap"] is not None:
                migration["customizeIdmap"] = p["customize_idmap"]
            if p["idmap_configs"] is not None:
                migration["idmapConfigs"] = [
                    dict(domain=c["domain"], backend=c["backend"], options=dict((k, str(v)) for k, v in (c["options"] or {}).items()))
                    for c in p["idmap_configs"]
                ]
            if p["organizational_unit"] is not None:
                migration["organizationalUnit"] = p["organizational_unit"]
            if p["migrate_posix_shares"]:
                shares = dict((s.get("share"), s.get("id")) for s in detail.get("shares") or [])
                unknown = [s for s in p["migrate_posix_shares"] if s not in shares]
                if unknown:
                    self.module.fail_json(
                        msg="migrate_posix_shares names unknown share(s) %s; shares: %s" % (", ".join(unknown), ", ".join(sorted(shares)) or "none")
                    )
                migration["posixShareIds"] = sorted(shares[s] for s in p["migrate_posix_shares"])
            after["generation"] = 2

        changed = bool(patch or to_add or to_remove or dns_change or migration is not None)
        if not changed or self.check_mode:
            self.finish(changed, before, after, self.result_cluster(config, detail))

        service_path = path_join("services", "smb", config["serviceId"])
        # Migrate first: the generation-2 settings below need a generation-2 cluster.
        if migration is not None:
            self.run_write("POST", service_path + "/migrate-generation", body=migration)
        if patch:
            self.run_write("PATCH", service_path, body=patch)
        for m in to_add:
            entry = dict(server=m["server"], nic=m["nic"], vlan=m["vlan"])
            if kind == TYPE_AD:
                entry.update(domainAdminUser=p["domain_admin_user"], domainAdminPassword=p["domain_admin_password"])
            self.run_write("POST", service_path + "/servers", body=entry)
        for sid in to_remove:
            self.run_write("DELETE", path_join("services", "smb", config["serviceId"], "servers", sid))
        if dns_change:
            self.run_write(
                "POST",
                service_path + "/service-dns-name",
                body=dict(
                    serviceDnsName=p["service_dns_name"],
                    domainAdminUser=p["domain_admin_user"],
                    domainAdminPassword=p["domain_admin_password"],
                ),
            )

        config, detail = self.find()
        self.finish(True, before, after, self.result_cluster(config, detail))


def main():
    SmbClusterModule().run()


if __name__ == "__main__":
    main()
