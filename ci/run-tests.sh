#!/bin/bash -ex
cd "$(dirname "$0")"/..

# Pylint
find . -name '*.py' -a -not -name 'setup.py' | xargs pylint

# Deploy if this is a tag (do it only for one Python version, not all matrix tests)
if [[ $TRAVIS_PYTHON_VERSION == 3* && $TRAVIS_TAG && $TRAVIS_PULL_REQUEST == false ]]; then
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
fi
