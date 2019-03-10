#!/bin/bash -ex
cd "$(dirname "$0")"/..

if [[ $TRAVIS_PULL_REQUEST != false && $TRAVIS_COMMIT_RANGE ]]; then
  # We are testing a Pull Request
  RUN_SETUP=1
  git diff --name-only $TRAVIS_COMMIT_RANGE | grep -q ^setup.py$ || RUN_SETUP=
fi

if [[ $TRAVIS != true && ! $VIRTUAL_ENV ]]; then
  # Not on Travis: try to load alidock's virtualenv (non-fatal)
  source "$HOME/.virtualenvs/alidock/bin/activate" || true
fi
type pylint

# Pylint
find . -name '*.py' -a -not -path './dist/*'  \
                    -a -not -path './build/*' | xargs pylint

# Produce wheel and deploy it
if [[ $TRAVIS_TAG && $TRAVIS_PULL_REQUEST == false ]]; then
  # Real deployment: use official index server
  PIP_REPO=
  PIP_PASS=$PYPI_PASSWORD  # encrypted from Travis CI
  PIP_USER=dberzano
  PIP_TAG=$TRAVIS_TAG
elif [[ $TRAVIS_PULL_REQUEST ]]; then
  # Test deployment: use test index server
  PIP_REPO="https://test.pypi.org/legacy/"
  PIP_PASS=$PYPI_TEST_PASSWORD  # encrypted from Travis CI
  PIP_USER=dberzano
  PIP_TAG="0.0.post${TRAVIS_PULL_REQUEST}.dev${TRAVIS_BUILD_NUMBER}"
fi

if [[ $PIP_USER ]]; then
  sed -i.deleteme -e "s/LAST-TAG/${PIP_TAG}/g" setup.py
  rm -f setup.py.deleteme
  git clean -fxd
  git diff
fi

python setup.py bdist_wheel
twine check dist/*
if [[ $PIP_USER ]]; then
  twine upload ${PIP_REPO:+--repository-url "$PIP_REPO"} \
               --skip-existing \
               -u "$PIP_USER" \
               -p "$PIP_PASS" \
               dist/*
else
  echo "Not uploading: test not on Travis CI"
fi
