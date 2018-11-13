#!/bin/bash -ex
cd "$(dirname "$0")"/..
find . -name '*.py' -a -not -name 'setup.py' | xargs pylint
