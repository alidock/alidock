#!/bin/bash -e

set -o pipefail
cd "$(dirname "$0")"/..

function fatal() {
  echo -e "\033[31;1m$1\033[m"
  exit 1
}

function info() {
  echo -e "\033[32;1m$1\033[m"
}

function alidock ()
{
    ( source "${HOME}/.virtualenvs/alidock/bin/activate" && command alidock "$@"; exit $? )
}

alidock stop
alidock --version
DOCKER_IMAGE=alisw/alidock:latest
EXPECTED_HELLO_WORLD='hello, world!'

HELLO_WORLD=$( alidock --no-update-image --image "$DOCKER_IMAGE" exec /bin/echo -n "$EXPECTED_HELLO_WORLD" | tail -n1)
if [[ "$HELLO_WORLD" != "$EXPECTED_HELLO_WORLD" ]]; then
  fatal "Container $DOCKER_IMAGE seems not to be usable with $(alidock --version)"
fi