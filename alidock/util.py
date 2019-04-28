import os
import re
import sys
import platform
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
    appropriate system method is not available, a unique identifier is computed out of the user
    login name."""
    return USERID

def getUserName():
    """Return the current user's username. Sanitize it and cope with pure numerical usernames
    """
    userName = re.sub("[^0-9a-z_-]", "_", os.getlogin().lower())
    return "alidock-" + userName if userName.isdigit() else userName

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
