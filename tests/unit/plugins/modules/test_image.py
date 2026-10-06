# -*- coding: utf-8 -*-
# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy

from ansible_collections.croit.ceph.plugins.modules import image, image_config
from ansible_collections.croit.ceph.tests.unit.fake_croit import FakeCroit, run_module

OLD = "11111111-1111-1111-1111-111111111111"
NEW = "22222222-2222-2222-2222-222222222222"
ARM = "33333333-3333-3333-3333-333333333333"


def img(image_id, arch="x86_64", downloaded=False, downloading=False):
    return dict(id=image_id, cpuArchitecture=arch, downloaded=downloaded, downloading=downloading, description=image_id)


class ImageCluster(FakeCroit):
    def __init__(self):
        super(ImageCluster, self).__init__()
        self.images = dict((i["id"], i) for i in [img(OLD, downloaded=True), img(NEW), img(ARM, arch="arm64")])
        self.defaults = dict(defaultX86=OLD, defaultArm64=None)
        self.archs = dict(x86_64=True, arm64=False)
        self.registry = dict(registry="", repository="", username="", passwordSet=False, plaintext=False, skipCertCheck=False)
        self.variant = "core"
        self.serve_tasks()
        self.route("GET", "/images", self.list)
        self.route("POST", "/images/(?P<iid>[^/]+)/start-download", self.download)
        self.route("DELETE", "/images/(?P<iid>[^/]+)", self.delete)
        self.route("POST", "/images/default", self.set_default)
        self.route("GET", "/images/archs", lambda call: (200, dict(self.archs)))
        self.route("PUT", "/images/archs", self.put_archs)
        self.route("GET", "/images/registry", lambda call: (200, dict(self.registry)))
        self.route("PUT", "/images/registry", self.put_registry)
        self.route("GET", "/images/config", lambda call: (200, dict(variant=self.variant, frontierEnabled=True)))
        self.route("PUT", "/images/config", self.put_config)

    def list(self, call):
        reply = dict(images=[copy.deepcopy(i) for i in self.images.values()], latestX86=NEW, latestArm64=ARM)
        reply.update(self.defaults)
        return 200, reply

    def download(self, call, iid):
        self.images[iid]["downloaded"] = True
        return 200, self.new_task("Download image", iid)

    def delete(self, call, iid):
        if iid in self.defaults.values():
            return 400, dict(code=400, message="default image")
        self.images[iid]["downloaded"] = False
        return 204, None

    def set_default(self, call):
        image_id = call.body["default"]
        key = "defaultX86" if self.images[image_id]["cpuArchitecture"] == "x86_64" else "defaultArm64"
        self.defaults[key] = image_id
        return 200, self.new_task("Set default image", image_id)

    def put_archs(self, call):
        self.archs = dict(call.body)
        return 204, None

    def put_registry(self, call):
        body = dict(call.body)
        password = body.pop("password", None)
        self.registry.update(body)
        if body.get("username") == "":
            self.registry["passwordSet"] = False
        elif password:
            self.registry["passwordSet"] = True
        return 204, None

    def put_config(self, call):
        self.variant = call.body["variant"]
        return 200, self.new_task("Switch variant")


def run(monkeypatch, fake, main=image.main, check_mode=False, **params):
    monkeypatch.setattr(image.time, "sleep", lambda s: None)
    return run_module(monkeypatch, fake, main, check_mode=check_mode, **params)


def assert_only_gets(fake):
    assert fake.writes() == [], fake.writes()


def test_image_idempotency_sequence(monkeypatch):
    fake = ImageCluster()
    # "create" = download, "update" = make default, "delete" = remove files
    r = run(monkeypatch, fake, check_mode=True, latest=True)
    assert r["changed"] and r["diff"]["after"]["downloaded"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, latest=True)
    assert r["changed"] and r["image"]["downloaded"]
    assert r["task"]["state"] == "FINISHED"

    r = run(monkeypatch, fake, latest=True)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, latest=True)
    assert not r["changed"]

    r = run(monkeypatch, fake, check_mode=True, id=NEW, default=True)
    assert r["changed"]
    assert r["diff"]["before"]["default"] is False and r["diff"]["after"]["default"] is True
    assert_only_gets(fake)

    r = run(monkeypatch, fake, id=NEW, default=True)
    assert r["changed"]
    assert fake.writes()[0].body == dict(default=NEW, overrideServers=False)
    assert fake.defaults["defaultX86"] == NEW

    r = run(monkeypatch, fake, id=NEW, default=True)
    assert not r["changed"]
    assert_only_gets(fake)

    r = run(monkeypatch, fake, check_mode=True, id=OLD, state="absent")
    assert r["changed"]
    assert_only_gets(fake)
    assert fake.images[OLD]["downloaded"]

    r = run(monkeypatch, fake, id=OLD, state="absent")
    assert r["changed"]
    assert not fake.images[OLD]["downloaded"]

    r = run(monkeypatch, fake, id=OLD, state="absent")
    assert not r["changed"]
    assert_only_gets(fake)


def test_default_image_cannot_be_undefaulted(monkeypatch):
    fake = ImageCluster()
    r = run(monkeypatch, fake, id=OLD, default=False)
    assert r["failed"]
    r = run(monkeypatch, fake, id=OLD, state="absent", default=True)
    assert r["failed"]


def test_removing_default_surfaces_croit_error(monkeypatch):
    fake = ImageCluster()
    r = run(monkeypatch, fake, id=OLD, state="absent")
    assert r["failed"]
    assert "default image" in r["msg"]


def test_unknown_image_fails(monkeypatch):
    fake = ImageCluster()
    r = run(monkeypatch, fake, id="nope")
    assert r["failed"]


def test_latest_arm(monkeypatch):
    fake = ImageCluster()
    r = run(monkeypatch, fake, check_mode=True, latest=True, arch="arm64")
    assert r["diff"]["before"]["id"] == ARM


def test_waits_for_running_download_without_change(monkeypatch):
    fake = ImageCluster()
    fake.images[NEW]["downloading"] = True
    polls = []

    def lister(call):
        polls.append(1)
        if len(polls) > 2:
            fake.images[NEW].update(downloading=False, downloaded=True)
        return fake.list(call)

    fake.routes = [r for r in fake.routes if r[1].pattern != "^/images$"]
    fake.route("GET", "/images", lister)
    r = run(monkeypatch, fake, id=NEW)
    assert not r["changed"]
    assert r["image"]["downloaded"]
    assert_only_gets(fake)


def test_id_and_latest_exclusive(monkeypatch):
    r = run(monkeypatch, ImageCluster(), id=NEW, latest=True)
    assert r["failed"]


# image_config ------------------------------------------------------------------


def cfg(monkeypatch, fake, check_mode=False, **params):
    return run(monkeypatch, fake, main=image_config.main, check_mode=check_mode, **params)


def test_config_idempotency_sequence(monkeypatch):
    fake = ImageCluster()
    spec = dict(archs=dict(arm64=True), registry=dict(registry="reg.example.com", repository="croit/os"), variant="enhanced")

    r = cfg(monkeypatch, fake, check_mode=True, **spec)
    assert r["changed"]
    assert r["diff"]["after"]["archs"] == dict(x86_64=True, arm64=True)
    assert_only_gets(fake)

    r = cfg(monkeypatch, fake, **spec)
    assert r["changed"]
    assert [c.path for c in fake.writes()] == ["/images/archs", "/images/registry", "/images/config"]
    assert fake.archs == dict(x86_64=True, arm64=True)
    assert fake.variant == "enhanced"

    r = cfg(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    r = cfg(monkeypatch, fake, check_mode=True, **spec)
    assert not r["changed"]

    update = dict(archs=dict(arm64=False), registry=dict(repository=""))
    r = cfg(monkeypatch, fake, check_mode=True, **update)
    assert r["changed"]
    assert_only_gets(fake)

    r = cfg(monkeypatch, fake, **update)
    assert r["changed"]
    assert fake.registry["repository"] == "" and fake.registry["registry"] == "reg.example.com"

    r = cfg(monkeypatch, fake, **update)
    assert not r["changed"]
    assert_only_gets(fake)


def test_registry_password_update_pattern(monkeypatch):
    fake = ImageCluster()
    spec = dict(registry=dict(username="pull", password="hunter2"))
    r = cfg(monkeypatch, fake, **spec)
    assert r["changed"]
    assert fake.writes()[0].body["password"] == "hunter2"
    assert "hunter2" not in repr(r)

    r = cfg(monkeypatch, fake, **spec)
    assert not r["changed"]
    assert_only_gets(fake)

    r = cfg(monkeypatch, fake, registry=dict(username="pull", password="hunter3", update_password="always"))
    assert r["changed"]
    assert "hunter3" not in repr(r)
    assert r["diff"]["after"]["registry"]["password"] == "******** (changed)"


def test_at_least_one_arch(monkeypatch):
    fake = ImageCluster()
    r = cfg(monkeypatch, fake, archs=dict(x86_64=False))
    assert r["failed"]
    assert_only_gets(fake)


def test_config_needs_an_option(monkeypatch):
    r = cfg(monkeypatch, ImageCluster())
    assert r["failed"]
