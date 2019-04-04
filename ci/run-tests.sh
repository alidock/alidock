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

# Deployment/test sdist creation
if [[ $TRAVIS_PYTHON_VERSION == 3* && $TRAVIS_TAG && $TRAVIS_PULL_REQUEST == false ]]; then
  # Deploy if this is a tag (do it only for one Python version, not all matrix tests)
  sed -i.deleteme -e "s/LAST-TAG/${TRAVIS_TAG}/g" setup.py
  rm -f *.deleteme
  git clean -fxd
  git diff
  python setup.py sdist
  cat > ~/.pypirc <<EOF
[distutils]
index-servers=pypi
[pypi]
username = dberzano
password = $PYPI_PASSWORD
EOF
  twine upload dist/*
  rm -f ~/.pypirc
elif [[ $RUN_SETUP ]]; then
  # Do not deploy, but setup scripts changed: try to create sdist
  python setup.py sdist
fi
