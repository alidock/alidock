#!/bin/bash -ex
cd "$(dirname "$0")"/..

# What tests to run based on what changed (on Travis)
if [[ $TRAVIS_COMMIT_RANGE ]]; then
  RUN_SETUP=1
  git diff --name-only $TRAVIS_COMMIT_RANGE | grep -q ^setup.py$ || RUN_SETUP=
fi

# Pylint
find . -name '*.py' -a -not -name 'setup.py' | xargs pylint

# Deployment/test sdist creation
if [[ $TRAVIS_PYTHON_VERSION == 3* && $TRAVIS_TAG && $TRAVIS_PULL_REQUEST == false ]]; then
  # Deploy if this is a tag (do it only for one Python version, not all matrix tests)
  sed -i.deleteme -e "s/LAST_TAG/${TRAVIS_TAG}/g" setup.py
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
