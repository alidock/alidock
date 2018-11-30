#!/bin/bash -e

# alidock-installer.sh -- simplify the installation of alidock
#
# This Bash script simplifies the installation of alidock by using a Python
# virtualenv. We make sure we are using our own isolated Python environment for
# it, and it should work seamlessly without being root.

set -e
set -o pipefail

VIRTUALENV_VERSION=16.1.0
TMPDIR=$(mktemp -d /tmp/alidock-installer-XXXXX)
VENV_DEST="$HOME/.virtualenvs/alidock"
PROG_DIR=$(cd "$(dirname "$0")"; pwd)

function pinfo() { echo -e "\033[32m${1}\033[m" >&2; }
function pwarn() { echo -e "\033[33m${1}\033[m" >&2; }
function perr() { echo -e "\033[31m${1}\033[m" >&2; }
function swallow() {
  local ERR=0
  "$@" &> "$TMPDIR/log" || ERR=$?
  if [[ $ERR != 0 ]]; then
    perr "+ $*"
    cat "$TMPDIR/log" >&2
  else
    rm -f "$TMPDIR/log"
  fi
  return $ERR
}

if [[ $(id -u) == 0 ]]; then
  perr "Refusing to continue the installation as root"
  exit 5
fi

# Check parameters
MODE=default
CHECK_DOCKER=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    git) MODE=git ;;
    devel) MODE=devel ;;
    --no-check-docker) CHECK_DOCKER= ;;
    --quiet)
      function pinfo() { :; }
      function pwarn() { :; }
    ;;
    --help)
      pinfo "alidock-installer.sh: install alidock in a Python virtualenv"
      pinfo ""
      pinfo "Normal usage:"
      pinfo "    alidock-installer.sh            # use this if in doubt!"
      pinfo ""
      pwarn "Advanced usage:"
      pwarn "    alidock-installer.sh git        # install latest version from Git"
      pwarn "    alidock-installer.sh devel      # install local development version"
      pwarn "    alidock-installer.sh <version>  # install specific version from PyPI"
      pwarn ""
      pwarn "Parameters:"
      pwarn "    --no-check-docker            # don't check if Docker works"
      pwarn "    --quiet                      # suppress messages (except errors)"
      exit 1
    ;;
    -*)
      perr "Unknown option: $1"
      exit 2
    ;;
    *) MODE="$1" ;;
  esac
  shift
done

# Favour `python3`, fall back on `python`
PYTHON_BIN=python3
type "$PYTHON_BIN" &> /dev/null || PYTHON_BIN=python
if ! type "$PYTHON_BIN" &> /dev/null; then
  perr "It appears Python is not available on your system: cannot continue"
  exit 3
fi

# Check if Docker is there and user can use it
if [[ $CHECK_DOCKER ]]; then
  pinfo "Checking if your Docker installation works"
  swallow docker run -it --rm hello-world
fi

cd /

pushd "$TMPDIR" &> /dev/null
  pinfo "Creating an environment for alidock using $("$PYTHON_BIN" --version 2>&1 | grep Python) ("$PYTHON_BIN")"
  curl -Lso - https://github.com/pypa/virtualenv/tarball/${VIRTUALENV_VERSION} | tar xzf -
  rm -rf "$VENV_DEST"  # always start from scratch
  swallow "$PYTHON_BIN" pypa-virtualenv-*/src/virtualenv.py "$VENV_DEST"
popd &> /dev/null

pinfo "Installing alidock under $VENV_DEST"
swallow source "$VENV_DEST/bin/activate"

URL=
DEVEL=
case "$MODE" in
  default) URL=alidock ;;
  git) URL=git+https://github.com/dberzano/alidock ;;
  devel)
    URL="$PROG_DIR"
    if [[ ! -f "$URL/setup.py" ]]; then
      perr "You did not execute the installer from the development directory"
      exit 4
    fi
    DEVEL="-e"
  ;;
  *) URL="alidock==$MODE" ;;
esac

swallow pip install --upgrade ${DEVEL} "${URL}"
if [[ $DEVEL ]]; then
  swallow pip install pylint
fi

# Patch init scripts for bash and zsh
SHELL_CHANGED=
for SHELLRC in $HOME/.bashrc $HOME/.bash_profile $HOME/.zshrc; do
  if ! grep -q 'function alidock()' "$SHELLRC" &> /dev/null; then
    pinfo "Adding alidock to $SHELLRC"
    touch "$SHELLRC"
    if [[ $(tail -c 1 "$SHELLRC") ]]; then
      echo >> "$SHELLRC"
    fi
    echo '# Execute alidock within the appropriate Python virtual environment' >> "$SHELLRC"
    echo 'function alidock() {( source "'$VENV_DEST'/bin/activate" && command alidock "$@"; exit $?; )}' >> "$SHELLRC"
    SHELL_CHANGED=1
  fi
done

pinfo "Installed: $(alidock --version)"

if [[ $SHELL_CHANGED ]]; then
  pwarn "Please open a new shell (terminal window, tab, etc.) in order to use alidock."
  pwarn "When you are done, you can use it by typing:"
  pwarn "    alidock"
else
  pwarn "You can use alidock by simply typing:"
  pwarn "    alidock"
fi

rm -rf "$TMPDIR"

if [[ $ALIDOCK_RUN ]]; then
  # Updater started from alidock. Re-run alidock immediately after the update
  unset alidock &> /dev/null || true
  exec alidock $ALIDOCK_ARGS
fi
