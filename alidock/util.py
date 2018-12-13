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
