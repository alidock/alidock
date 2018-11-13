import sys

def info(msg):
    sys.stderr.write("\033[32m" + msg + "\033[m\n")
    sys.stderr.flush()

def error(msg):
    sys.stderr.write("\033[31m" + msg + "\033[m\n")
    sys.stderr.flush()
