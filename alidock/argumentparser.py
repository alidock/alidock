import os.path
import argparse
from collections import namedtuple
import yaml

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

    def genConfigHelp(self, defaultConf):
        confFile = os.path.join(os.path.expanduser("~"), ".alidock-config.yaml")
        epilog = "it is possible to specify the most frequently used options in a YAML " \
                 "configuration file in {confFile}\n" \
                 "the following options (along with their default values) can be specified " \
                 "(please include `---` as first line):\n---\n".format(confFile=confFile)
        yamlLines = {}
        longest = 0
        for opt in self.argsNormal + self.argsAtStart:
            if opt.config:
                assert opt.config in defaultConf, "option %s expected in default conf" % opt.config
                yamlLines[opt.option] = yaml.dump({opt.config: defaultConf[opt.config]}).rstrip()
                longest = max(longest, len(yamlLines[opt.option]))
        fmt = "%%-%ds  # same as option %%s\n" % longest
        for yLine in yamlLines:
            epilog += fmt % (yamlLines[yLine], yLine)

        self.epilog = epilog
