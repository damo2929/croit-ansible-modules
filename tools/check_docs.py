# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check module documentation against the AGENTS.md documentation standard.

Runs ``ansible-doc --json`` on every module, then checks:

* the module docs: description depth, seealso, option descriptions and types,
  RETURN completeness (returned/type, contains or sample), EXAMPLES quality;
* every ``croit.ceph.*`` task in the module EXAMPLES, README.md, the
  docsite guides and the playbooks in examples/: options must exist
  (aliases count) and values must be valid choices.

Run it from a checkout at ``.../ansible_collections/croit/ceph``::

    python tools/check_docs.py              # all modules
    python tools/check_docs.py pool rbd     # selected modules

Exits non-zero when anything is found.
"""

import glob
import json
import os
import re
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTIONS_PATH = os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))
EXAMPLES_HEADER = "module_defaults for group/croit.ceph.all"
MIN_OPTION_TEXT = 25
MIN_DESCRIPTION_TEXT = 80


def load_docs(modules):
    env = dict(os.environ)
    if "ANSIBLE_COLLECTIONS_PATH" not in env:
        if not ROOT.replace(os.sep, "/").endswith("ansible_collections/croit/ceph"):
            sys.exit(
                "Run this from a checkout at .../ansible_collections/croit/ceph, "
                "or set ANSIBLE_COLLECTIONS_PATH to a directory containing ansible_collections/croit/ceph."
            )
        env["ANSIBLE_COLLECTIONS_PATH"] = COLLECTIONS_PATH
    names = ["croit.ceph.%s" % m for m in modules]
    out = subprocess.run(
        ["ansible-doc", "--json", "--type", "module"] + names,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)


def text_of(value):
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value or "")


class Checker:
    def __init__(self, docs):
        self.docs = docs
        self.problems = []

    def add(self, where, message):
        self.problems.append("%s: %s" % (where, message))

    # Module docs ----------------------------------------------------------

    def options(self, where, opts, prefix=""):
        for name, opt in (opts or {}).items():
            full = prefix + name
            desc = text_of(opt.get("description"))
            if not desc:
                self.add(where, "option %s has no description" % full)
            elif len(desc) < MIN_OPTION_TEXT:
                self.add(where, "option %s description is too short (%r)" % (full, desc))
            if "type" not in opt:
                self.add(where, "option %s has no type" % full)
            if opt.get("type") == "list" and "elements" not in opt:
                self.add(where, "option %s is a list without elements" % full)
            if opt.get("suboptions"):
                self.options(where, opt["suboptions"], full + ".")

    def returns(self, where, rets, prefix=""):
        for name, ret in (rets or {}).items():
            full = prefix + name
            for key in ("description", "returned", "type"):
                if key not in ret:
                    self.add(where, "return %s has no %s" % (full, key))
            if ret.get("type") in ("dict", "list") and "sample" not in ret and "contains" not in ret:
                self.add(where, "return %s (%s) has neither contains nor sample" % (full, ret.get("type")))
            if ret.get("contains"):
                self.returns(where, ret["contains"], full + ".")

    def module(self, fqcn):
        entry = self.docs[fqcn]
        doc = entry.get("doc") or {}
        where = fqcn
        if not doc.get("short_description"):
            self.add(where, "no short_description")
        if len(text_of(doc.get("description"))) < MIN_DESCRIPTION_TEXT:
            self.add(where, "module description is too thin")
        for key in ("seealso", "notes", "attributes"):
            if not doc.get(key):
                self.add(where, "no %s" % key)
        self.options(where, doc.get("options"))
        if not entry.get("return"):
            self.add(where, "no RETURN")
        self.returns(where, entry.get("return"))
        examples = entry.get("examples") or ""
        if EXAMPLES_HEADER not in examples.split("\n- ", 1)[0]:
            self.add(where, "EXAMPLES do not start with the standard header comment")
        try:
            tasks = yaml.safe_load(examples) or []
        except yaml.YAMLError as e:
            self.add(where, "EXAMPLES are not valid YAML: %s" % e)
            return
        if len(tasks) < 2:
            self.add(where, "only %d example(s)" % len(tasks))
        if "register:" not in examples:
            self.add(where, "no example registers and uses a result")
        for task in tasks:
            if isinstance(task, dict) and "name" not in task:
                self.add(where, "an example task has no name")
        self.tasks(where + " EXAMPLES", tasks)

    # Task validation ------------------------------------------------------

    def task_options(self, where, fqcn, spec, given, path=""):
        names = {}
        for name, opt in spec.items():
            names[name] = opt
            for alias in opt.get("aliases") or []:
                names[alias] = opt
        for key, value in (given or {}).items():
            if key not in names:
                self.add(where, "%s: unknown option %s%s" % (fqcn, path, key))
                continue
            opt = names[key]
            choices = opt.get("choices")
            values = value if isinstance(value, list) else [value]
            if choices:
                for item in values:
                    templated = isinstance(item, str) and "{{" in item
                    if isinstance(item, (str, int)) and not isinstance(item, bool) and not templated and item not in choices:
                        self.add(where, "%s: %s%s=%r is not one of %s" % (fqcn, path, key, item, choices))
            if opt.get("suboptions"):
                for item in values:
                    if isinstance(item, dict):
                        self.task_options(where, fqcn, opt["suboptions"], item, path + key + ".")

    def tasks(self, where, data):
        found = []

        def collect(node):
            if isinstance(node, list):
                for item in node:
                    collect(item)
            elif isinstance(node, dict):
                for key in ("tasks", "block", "rescue", "always", "pre_tasks", "post_tasks"):
                    if key in node:
                        collect(node[key])
                found.append(node)

        collect(data)
        for task in found:
            for key, value in task.items():
                if not key.startswith("croit.ceph."):
                    continue
                if key not in self.docs:
                    self.add(where, "unknown module %s" % key)
                    continue
                self.task_options(where, key, self.docs[key]["doc"].get("options") or {}, value if isinstance(value, dict) else {})

    def markdown(self, path):
        text = open(path).read()
        for block in re.findall(r"```yaml\n(.*?)```", text, re.S):
            try:
                self.tasks(os.path.relpath(path, ROOT), yaml.safe_load(block))
            except yaml.YAMLError as e:
                self.add(os.path.relpath(path, ROOT), "YAML block does not parse: %s" % e)

    def playbook(self, path):
        try:
            self.tasks(os.path.relpath(path, ROOT), yaml.safe_load(open(path)))
        except yaml.YAMLError as e:
            self.add(os.path.relpath(path, ROOT), "does not parse: %s" % e)

    def rst(self, path):
        lines = open(path).read().split("\n")
        i = 0
        while i < len(lines):
            if re.match(r"\.\. code-block:: yaml", lines[i].strip()):
                i += 1
                block = []
                while i < len(lines) and (not lines[i].strip() or lines[i].startswith("   ")):
                    block.append(lines[i][3:])
                    i += 1
                try:
                    self.tasks(os.path.relpath(path, ROOT), yaml.safe_load("\n".join(block)))
                except yaml.YAMLError as e:
                    self.add(os.path.relpath(path, ROOT), "YAML code block does not parse: %s" % e)
            else:
                i += 1


def main():
    wanted = sys.argv[1:]
    all_modules = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "plugins", "modules", "*.py")))
    modules = wanted or all_modules
    docs = load_docs(all_modules)
    missing = [m for m in all_modules if "croit.ceph.%s" % m not in docs]
    if missing:
        sys.exit("ansible-doc could not load %s; check ANSIBLE_COLLECTIONS_PATH" % ", ".join(missing))
    checker = Checker(docs)
    for name in modules:
        checker.module("croit.ceph.%s" % name)
    if not wanted:
        checker.markdown(os.path.join(ROOT, "README.md"))
        for path in sorted(glob.glob(os.path.join(ROOT, "docs", "docsite", "rst", "*.rst"))):
            checker.rst(path)
        for path in sorted(glob.glob(os.path.join(ROOT, "examples", "*.yml"))):
            checker.playbook(path)
    for problem in checker.problems:
        print(problem)
    print("Checked %d module(s); %d problem(s)." % (len(modules), len(checker.problems)))
    return 1 if checker.problems else 0


if __name__ == "__main__":
    sys.exit(main())
