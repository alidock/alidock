import os
import os.path
import re
import sys
import platform
from pathlib import Path
from subprocess import call
from hashlib import md5

def splitEsc(inp, delim, nDelim):
    """Splits input string inp with nDelim delimiters. Returns a tuple of nDelim+1 components: some
       components may be empty if not enough separators are found. Use the backslash to escape the
       delimiters (double backslash will be expanded to a single backslash)."""
    idx = None
    esc = False
    first = ""
    for i, cha in enumerate(inp):
        if esc:
            first += cha
            esc = False
        elif cha == "\\":
            esc = True
        elif cha == delim:
            idx = i
            break
        else:
            first += cha
    # Not using generic unpacking as we need to support Python < 3.5 :-(
    remainder = inp[idx+1:] if idx is not None else ""
    if nDelim > 1:
        return (first,) + splitEsc(remainder, delim, nDelim-1)
    return (first, remainder)

if hasattr(os, "getuid"):
    USERID = os.getuid()  # pylint: disable=no-member
else:
    HASH = md5()
    HASH.update(os.getlogin().lower().encode())
    USERID = 10000 + int(HASH.hexdigest()[2:5], 16)
    del HASH

def getUserId():
    """Return the current user's numeric identifier according to the operating system. When the
    appropriate system method is not available, a unique identifier is computed from the user
    login name."""
    return USERID

def getUserName():
    """Return the username to be used inside the container. Username is computed according to the
    host system's username, and sanitized appropriately (in particular we handle special symbols,
    casing and purely numerical usernames)."""
    userName = re.sub("[^0-9a-z_-]", "_", os.getlogin().lower())
    return "u" + userName if userName.isdigit() else userName

def deactivateVenv(env):
    """Given a dictionary with the current environment it cleans it up by removing the current
    Python virtual environment."""
    if not "VIRTUAL_ENV" in env:
        return
    venvPrefix = os.path.realpath(os.path.expanduser(env["VIRTUAL_ENV"]))
    for var in ["PYTHONHOME", "PYTHONPATH", "PATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"]:
        if not var in env:
            continue
        val = os.path.realpath(os.path.expanduser(env[var]))
        env[var] = ":".join(x for x in val.split(":")
                            if not os.path.realpath(os.path.expanduser(x)).startswith(venvPrefix))
    del env["VIRTUAL_ENV"]

def getRocmVideoGid():
    try:
        if not Path("/dev/kfd").is_char_device() or not Path("/dev/dri").is_dir():
            return None
    except OSError:
        return None
    try:
        from grp import getgrnam
        return getgrnam("video").gr_gid
    except (KeyError, AttributeError, ModuleNotFoundError):  # pylint: disable=undefined-variable
        return None

if platform.system() == "Windows":
    def execReturn(_, args):
        """Executes the given program on Windows (no process substitution) and exits with the
        appropriate status code."""
        ret = call(args)
        if ret < 0:  # fatal signal
            ret = 128 + ret
        sys.exit(ret)
else:
    def execReturn(progName, args):
        """Executes the given progName with the given args by replacing the current process."""
        os.execvp(progName, args)
