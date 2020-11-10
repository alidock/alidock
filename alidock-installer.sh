#!/bin/bash -e

# alidock-installer.sh -- simplify the installation of alidock
#
# This Bash script simplifies the installation of alidock by using a Python
# virtualenv. We make sure we are using our own isolated Python environment for
# it, and it should work seamlessly without being root.

set -e
set -o pipefail

TMPDIR=$(mktemp -d /tmp/alidock-installer-XXXXX)
VENV_DEST="$HOME/.virtualenvs/alidock"
PROG_DIR=$(cd "$(dirname "$0")"; pwd)

cd /

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
function restore_quit() {
  [[ -d ${VENV_DEST}.bak ]] || exit 8
  rm -rf "$VENV_DEST"
  mv "${VENV_DEST}.bak" "$VENV_DEST"
  pwarn "Old alidock installation was restored"
  exit 7
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
    pull*)
      MODE=pull
      PRNUM=${1:4}
    ;;
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
      pwarn "    alidock-installer.sh pull<num>  # install version from pull request <num>"
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

URL=
case "$MODE" in
  default) URL=alidock ;;
  git) URL=git+https://github.com/alidock/alidock ;;
  devel)
    if [[ ! -f "$PROG_DIR/setup.py" ]]; then
      perr "Run from the development directory to install in development mode"
      exit 4
    fi
    URL=("-e" "$PROG_DIR[devel]")
  ;;
  pull) URL=git+https://github.com/alidock/alidock@refs/pull/$PRNUM/head ;;
  *) URL="alidock==$MODE" ;;
esac

# Check for Python 3
PYTHON_BIN=python3
if ! type "${PYTHON_BIN}" &> /dev/null; then
  perr "python3 executable not found. Alidock supports Python 3 only."
  exit 3
fi

# Check if Python distutils is available (otherwise virtualenv will fail)
if ! "$PYTHON_BIN" -c 'import distutils.spawn' &> /dev/null; then
  perr "Your Python installation using $PYTHON_BIN seems incomplete: distutils is missing"
  if [[ $(uname) == Linux && -x /usr/bin/apt-get && "$PYTHON_BIN" == *python3 ]]; then
    perr "Try installing it with:"
    perr "  sudo apt-get update && sudo apt-get install python3-distutils"
  fi
  exit 6
fi

# Check if Docker is there and user can use it
if [[ $CHECK_DOCKER ]]; then
  pinfo "Checking if your Docker installation works"
  IT=
  [[ -t 1 ]] && IT="-it" || IT=""
  swallow docker run $IT --rm hello-world
fi

pushd "$TMPDIR" &> /dev/null
  PYTHON_INFO="$("$PYTHON_BIN" --version 2>&1 | grep Python) ("$PYTHON_BIN")"
  pinfo "Creating an environment for alidock using $PYTHON_INFO"
  if [[ -d $VENV_DEST ]]; then
    rm -rf "${VENV_DEST}.bak"
    mv "$VENV_DEST" "${VENV_DEST}.bak"  # make backup of current venv
  fi
  swallow "$PYTHON_BIN" -m venv "$VENV_DEST" || restore_quit
popd &> /dev/null

pinfo "Installing alidock under $VENV_DEST"
source "$VENV_DEST/bin/activate"

swallow pip install --upgrade "${URL[@]}" || restore_quit
rm -rf "${VENV_DEST}.bak"  # not needed anymore

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
