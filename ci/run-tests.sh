#!/bin/bash -e

set -o pipefail
cd "$(dirname "$0")"/..

# Travis CI fold and timing
# See http://www.garbers.co.za/2017/11/01/code-folding-and-timing-in-travis-ci/
function fold_start() {
  if [[ $CURRENT_SECTION ]]; then
    fold_end
  fi
  CURRENT_SECTION=$(echo "$1" | sed -e 's![^A-Za-z0-9\._]!_!g')
  if [[ $TRAVIS == true ]]; then
    travis_fold start "$CURRENT_SECTION"
    travis_time_start
  fi
  echo -e "\033[34;1m$1\033[m"
}

function fold_end() {
  if [[ $TRAVIS == true ]]; then
    travis_time_finish
    travis_fold end "$CURRENT_SECTION"
  fi
  CURRENT_SECTION=
}

function fatal() {
  echo -e "\033[31;1m$1\033[m"
  exit 1
}

function info() {
  echo -e "\033[32;1m$1\033[m"
}

if [[ $TRAVIS != true && ! $VIRTUAL_ENV ]]; then
  # Not on Travis: try to load alidock's virtualenv (non-fatal)
  source "$HOME/.virtualenvs/alidock/bin/activate" || true
fi
type pylint

# Pylint
fold_start "Running pylint"
  find . -name '*.py' -a -not -path './dist/*'  \
                      -a -not -path './build/*' | xargs pylint
fold_end

fold_start "Producing wheel"
  if [[ $TRAVIS_TAG && $TRAVIS_PULL_REQUEST == false ]]; then
    # Real deployment: use official index server
    PIP_REPO=
    PIP_PASS=$PYPI_PASSWORD  # encrypted from Travis CI
    PIP_USER=dberzano
    PIP_TAG=$TRAVIS_TAG
  elif [[ $TRAVIS_PULL_REQUEST && $TRAVIS_PULL_REQUEST != false ]]; then
    # Test deployment: use test index server
    PIP_REPO="https://test.pypi.org/legacy/"
    PIP_PASS=$PYPI_TEST_PASSWORD  # encrypted from Travis CI
    PIP_USER=dberzano
    PIP_TAG="0.0.post${TRAVIS_PULL_REQUEST}.dev${TRAVIS_BUILD_NUMBER}"
  fi

  if [[ $PIP_PASS ]]; then
    sed -i.deleteme -e "s/LAST-TAG/${PIP_TAG}/g" setup.py
    rm -f setup.py.deleteme
    git clean -fxd
    git diff
  fi
  python setup.py bdist_wheel
  twine check dist/*
fold_end

if [[ $PIP_PASS ]]; then
  fold_start "Uploading wheel"
    twine upload ${PIP_REPO:+--repository-url "$PIP_REPO"} \
                 --skip-existing \
                 -u "$PIP_USER" \
                 -p "$PIP_PASS" \
                 dist/*
  fold_end
  if [[ $PIP_REPO == *test* ]]; then
    info "Install this build's package:"
    info "  pip install --extra-index-url https://test.pypi.org/simple 'alidock==$PIP_TAG'"
  fi
else
  info "Not uploading wheel"
fi
