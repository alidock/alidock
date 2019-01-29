import sys
import colorama

class Log(object):

    def __init__(self):
        colorama.init()
        self.quiet = False

    def setQuiet(self, quiet=True):
        self.quiet = quiet

    def printColor(self, colorCode, msg):
        if self.quiet:
            return
        sys.stderr.write(colorCode)
        sys.stderr.write(msg)
        sys.stderr.write(colorama.Style.RESET_ALL)
        sys.stderr.write("\n")
        sys.stderr.flush()

    def debug(self, msg):
        self.printColor(colorama.Fore.MAGENTA, msg)

    def info(self, msg):
        self.printColor(colorama.Fore.GREEN, msg)

    def warning(self, msg):
        self.printColor(colorama.Fore.YELLOW, msg)

    def error(self, msg):
        self.printColor(colorama.Fore.RED, msg)
