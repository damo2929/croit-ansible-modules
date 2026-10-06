# Copyright (c) croit GmbH
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check that every croit endpoint the modules use exists in the API spec.

Modules declare the endpoints they call with comments such as::

    # croit-api: PATCH /pools/{name}

This script checks each one against docs/openapi.json, and can refresh that
snapshot from the croit API docs page (the spec is embedded in it).

    python tools/check_spec_drift.py             # check
    python tools/check_spec_drift.py --refresh   # re-download the spec first
"""

import argparse
import glob
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "docs", "openapi.json")
DOCS_URL = "https://www.croit.io/api-docs"
MARKER = re.compile(r"^#\s*croit-api:\s*(GET|POST|PUT|PATCH|DELETE)\s+(\S+)\s*$", re.MULTILINE)


def refresh(url):
    with urllib.request.build_opener().open(url, timeout=60) as resp:
        html = resp.read().decode("utf-8")
    match = re.search(r"createApiReference\('#app',\s*", html)
    if not match:
        sys.exit("Could not find the embedded OpenAPI spec in %s" % url)
    config, _end = json.JSONDecoder().raw_decode(html[match.end():])
    with open(SPEC, "w") as f:
        json.dump(config["content"], f, indent=1, sort_keys=True)
        f.write("\n")
    print("Refreshed %s from %s" % (os.path.relpath(SPEC, ROOT), url))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="re-download the spec before checking")
    parser.add_argument("--url", default=DOCS_URL, help="croit API docs page to extract the spec from")
    args = parser.parse_args()

    if args.refresh:
        refresh(args.url)

    with open(SPEC) as f:
        paths = json.load(f)["paths"]

    problems = []
    used = 0
    for module in sorted(glob.glob(os.path.join(ROOT, "plugins", "modules", "*.py"))):
        with open(module) as f:
            markers = MARKER.findall(f.read())
        name = os.path.relpath(module, ROOT)
        for method, path in markers:
            used += 1
            if path not in paths:
                problems.append("%s: %s %s - path not in spec" % (name, method, path))
            elif method.lower() not in paths[path]:
                problems.append("%s: %s %s - method not in spec" % (name, method, path))

    for problem in problems:
        print("DRIFT " + problem)
    print("Checked %d endpoint declaration(s); %d problem(s)." % (used, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
