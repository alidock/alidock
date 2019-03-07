#!/bin/bash -ex
cd "$(dirname "$0")"/..

if [[ $TRAVIS_PULL_REQUEST != false && $TRAVIS_COMMIT_RANGE ]]; then
  # We are testing a Pull Request
  RUN_SETUP=1
  [[ $TRAVIS_PYTHON_VERSION == 3* ]] && RUN_DOCK=1 || RUN_DOCK=
  git diff --name-only $TRAVIS_COMMIT_RANGE | grep -q ^setup.py$ || RUN_SETUP=
  git diff --name-only $TRAVIS_COMMIT_RANGE | grep -q ^dock/     || RUN_DOCK=
  DOCKER_REPO=aliswdev
elif [[ $TRAVIS_PULL_REQUEST == false && $TRAVIS_BRANCH == master ]]; then
  # We are testing the master branch. Get list of changed files for the topmost commit and trust it:
  # we should have squashed the Pull Requests, so it should be fine
  [[ $TRAVIS_PYTHON_VERSION == 3* ]] && RUN_DOCK=1 || RUN_DOCK=
  if [[ $TRAVIS_EVENT_TYPE != cron ]]; then
    # Build if needed on merge; build always on cron (to get possible changes of the FROM container)
    git diff-tree --no-commit-id --name-only -r HEAD | grep -q ^dock/ || RUN_DOCK=
  fi
  DOCKER_REPO=alisw
fi

if [[ $TRAVIS != true && ! $VIRTUAL_ENV ]]; then
  # Not on Travis: try to load alidock's virtualenv (non-fatal)
  source "$HOME/.virtualenvs/alidock/bin/activate" || true
fi
type pylint

# Pylint
find . -name '*.py' -a -not -path './dist/*'  \
                    -a -not -path './build/*' | xargs pylint

# Docker
if [[ $RUN_DOCK ]]; then
  docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"
  pushd dock
    docker build . -t "$DOCKER_REPO"/alidock:latest
    docker tag "$DOCKER_REPO"/alidock:latest "$DOCKER_REPO"/alidock:cc7
  popd
  docker push "$DOCKER_REPO"/alidock:latest
  docker push "$DOCKER_REPO"/alidock:cc7
fi

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
