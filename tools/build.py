#!/usr/bin/env python3
# SPDX-License-Identifier: EUPL-1.2
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import themebuild


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the Resina icon theme tree")
    parser.add_argument("out", help="output directory, must not exist")
    parser.add_argument("--profile", choices=themebuild.PROFILES, default="full")
    parser.add_argument("--repo", default=os.path.dirname(HERE))
    args = parser.parse_args(argv)
    try:
        themebuild.build(os.path.abspath(args.repo), os.path.abspath(args.out), args.profile)
    except (themebuild.BuildError, OSError, UnicodeDecodeError) as error:
        print("build failed: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
