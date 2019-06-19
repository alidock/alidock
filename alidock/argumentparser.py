import os.path
import argparse
from collections import namedtuple

AliDockArg = namedtuple("AliDockArg", "option config descr")

class AliDockArgumentParser(argparse.ArgumentParser):
    """Lightweight subclass of ArgumentParser implementing some features required to display the
       alidock help: addition of normal arguments, addition of arguments only valid when starting a
       new container, and matching between command-line options and configuration file options."""

    def __init__(self, *args, atStartTitle, **kwargs):
        self.argsNormal = []
        self.argsAtStart = []
        super(AliDockArgumentParser, self).__init__(*args,
                                                    formatter_class=argparse.RawTextHelpFormatter,
                                                    **kwargs)
        self.groupAtStart = self.add_argument_group(atStartTitle)

    def addArgument(self, *args, atStart=False, config=False, **kwargs):
        configVar = None
        if config:
            configVar = kwargs["dest"]
            kwargs["help"] = kwargs.get("help", "") + " [" + configVar + "]"
        if atStart:
            self.argsAtStart.append(AliDockArg(args[0], configVar, kwargs.get("help", "")))
            return self.groupAtStart.add_argument(*args, **kwargs)
        self.argsNormal.append(AliDockArg(args[0], configVar, kwargs.get("help", "")))
        return self.add_argument(*args, **kwargs)

    def addArgumentStart(self, *args, **kwargs):
        return self.addArgument(*args, **kwargs, atStart=True)

    def genConfigHelp(self):
        confFile = os.path.join(os.path.expanduser("~"), ".alidock-config.yaml")
        epilog = "if you frequently specify some options you may want to add them to %s " \
                 "like the following (including `---`):\n---\n" % confFile
        longest = 0
        for opt in self.argsNormal + self.argsAtStart:
            if opt.config:
                longest = max(longest, len(opt.config))
        fmt = "%%-%ds: \"see help above for option %%s\"\n" % (longest + 1)
        for opt in self.argsNormal + self.argsAtStart:
            if not opt.config:
                continue
            epilog += fmt % (opt.config, opt.option)
        self.epilog = epilog
