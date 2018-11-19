import sys

class Log(object):
    green = "32"
    yellow = "33"
    red = "31"
    magenta = "35"

    def __init__(self):
        self.quiet = False

    def setQuiet(self, quiet=True):
        self.quiet = quiet

    def printColor(self, colEsc, msg):
        if self.quiet:
            return
        sys.stderr.write("\033[" + colEsc + "m" + msg + "\033[m\n")
        sys.stderr.flush()

    def debug(self, msg):
        self.printColor(self.magenta, msg)

    def info(self, msg):
        self.printColor(self.green, msg)

    def warning(self, msg):
        self.printColor(self.yellow, msg)

    def error(self, msg):
        self.printColor(self.red, msg)
