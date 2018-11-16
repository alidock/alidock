"""alidock module"""

from __future__ import print_function
from argparse import ArgumentParser
from pwd import getpwuid
from time import time, sleep
import errno
import os
import os.path
import json
import subprocess
import yaml
from yaml import YAMLError
import docker
import jinja2
import requests
from requests.exceptions import RequestException
from pkg_resources import resource_string, parse_version, require
from alidock.log import Log

LOG = Log()

class AliDockError(Exception):
    def __init__(self, msg):
        super(AliDockError, self).__init__()
        self.msg = msg
    def __str__(self):
        return self.msg

class AliDock(object):

    def __init__(self):
        self.cli = docker.from_env()
        self.lastUpdRelative = ".alidock_last_updated"
        self.dirInside = "/home/alidock"
        self.logRelative = ".alidock.log"
        self.conf = {
            "dockName"     : "/alidock",
            "imageName"    : "alisw/alidock:latest",
            "dirOutside"   : "~/alidock",
            "updatePeriod" : 43200
        }
        self.parseConfig()
        self.conf["dockName"] = "{dockName}-{userId}".format(dockName=self.conf["dockName"],
                                                             userId=os.getuid())

    def parseConfig(self):
        confFile = os.path.expanduser("~/.alidock-config.yaml")
        try:
            confOverride = yaml.safe_load(open(confFile).read())
            for k in self.conf:
                self.conf[k] = confOverride.get(k, self.conf[k])
        except (OSError, IOError, YAMLError, AttributeError):
            pass

    def isRunning(self):
        try:
            self.cli.containers.get(self.conf["dockName"])
        except docker.errors.NotFound:
            return False
        return True

    def getSshCommand(self):
        try:
            attrs = self.cli.containers.get(self.conf["dockName"]).attrs
            sshPort = attrs["NetworkSettings"]["Ports"]["22/tcp"][0]["HostPort"]
        except (docker.errors.NotFound, KeyError) as exc:
            outLog = os.path.join(self.conf["dirOutside"], self.logRelative)
            raise AliDockError("cannot find container, maybe it did not start up properly: "
                               "check log file {outLog} for details. Error: {msg}"
                               .format(outLog=outLog, msg=exc))
        return ["ssh", "localhost", "-p", str(sshPort), "-Y", "-F/dev/null",
                "-oForwardX11Trusted=no", "-oUserKnownHostsFile=/dev/null",
                "-oStrictHostKeyChecking=no", "-oLogLevel=QUIET",
                "-i", os.path.join(self.conf["dirOutside"], ".ssh", "id_rsa")]

    def waitSshUp(self):
        for _ in range(0, 40):
            try:
                nul = open(os.devnull, "w")
                subprocess.check_call(self.getSshCommand() + ["-T", "/bin/true"],
                                      stdout=nul, stderr=nul)
            except subprocess.CalledProcessError:
                sleep(0.5)
            else:
                return True
        return False

    def shell(self, cmd=None):
        os.execvp("ssh", self.getSshCommand() + (cmd if cmd else []))

    def rootShell(self):
        os.execvp("docker", ["docker", "exec", "-it", self.conf["dockName"], "/bin/bash"])

    def run(self):
        # Create directory to be shared with the container
        outDir = os.path.expanduser(self.conf["dirOutside"])
        try:
            os.mkdir(outDir)
        except OSError as exc:
            if not os.path.isdir(outDir) or exc.errno != errno.EEXIST:
                raise AliDockError("cannot create directory {dir} to share with container, "
                                   "check permissions".format(dir=self.conf["dirOutside"]))

        # Create initialisation script
        initSh = jinja2.Template(resource_string("alidock.helpers", "init.sh.j2"))
        userId = os.getuid()
        userName = getpwuid(userId).pw_name
        initShPath = os.path.join(outDir, ".alidock-init.sh")
        with open(initShPath, "w") as fil:
            fil.write(initSh.render(sharedDir=self.dirInside,
                                    logRelative=self.logRelative,
                                    userName=userName,
                                    userId=userId))
        os.chmod(initShPath, 0o755)

        # Start container with that script
        self.cli.containers.run(self.conf["imageName"],
                                command=[os.path.join(self.dirInside, ".alidock-init.sh")],
                                detach=True,
                                auto_remove=True,
                                cap_add=["SYS_PTRACE"],
                                name=self.conf["dockName"],
                                mounts=[docker.types.Mount(self.dirInside,
                                                           outDir, type="bind")],
                                ports={"22/tcp": None})  # None == random port

        return True

    def stop(self):
        try:
            self.cli.containers.get(self.conf["dockName"]).remove(force=True)
        except docker.errors.NotFound:
            pass  # final state is fine, container is gone

    def hasUpdates(self):
        if str(require(__package__)[0].version) == "LAST-TAG":
            # Local development or installed from Git
            return False

        tsFn = os.path.join(self.conf["dirOutside"], self.lastUpdRelative)
        try:
            with open(tsFn) as fil:
                lastUpdate = int(fil.read())
        except (IOError, OSError, ValueError):
            lastUpdate = 0

        now = int(time())
        if now - lastUpdate > int(self.conf["updatePeriod"]):
            try:
                pypaData = requests.get("https://pypi.org/pypi/{pkg}/json".format(pkg=__package__),
                                        timeout=5)
                pypaData.raise_for_status()
                availVersion = parse_version(pypaData.json()["info"]["version"])
                localVersion = parse_version(require(__package__)[0].version)
                if availVersion > localVersion:
                    return True
            except (requests.RequestException, ValueError) as exc:
                raise AliDockError(str(exc))

            with open(tsFn, "w") as fil:
                fil.write(str(now))

        return False

def entrypoint():
    argp = ArgumentParser()
    argp.add_argument("--quiet", dest="quiet", default=False, action="store_true",
                      help="Do not print any message")
    argp.add_argument("--tmux", dest="tmux", default=False, action="store_true",
                      help="Start or resume a detachable tmux session")
    argp.add_argument("action", default="enter", nargs="?",
                      choices=["enter", "root", "start", "status", "stop"],
                      help="What to do")
    args = argp.parse_args()

    LOG.setQuiet(args.quiet)

    try:
        processActions(args)
    except AliDockError as exc:
        LOG.error("Cannot continue: {msg}".format(msg=exc))
        exit(10)
    except docker.errors.APIError as exc:
        LOG.error("Docker error: {msg}".format(msg=exc))
        exit(11)
    except RequestException as exc:
        LOG.error("Cannot communicate to Docker, is it running? Full error: {msg}".format(msg=exc))
        exit(12)

def processEnterStart(aliDock, args):
    created = False
    if not aliDock.isRunning():
        created = True
        LOG.info("Creating container, hold on")
        aliDock.run()
    if args.action == "enter":
        if args.tmux and os.environ.get("TMUX") is None:
            LOG.info("Resuming tmux session in the container")
            cmd = ["-t", "tmux", "-u", "-CC", "new-session", "-A", "-s", "ad-tmux"]
        elif args.tmux:
            raise AliDockError("already in a tmux session")
        else:
            LOG.info("Starting a shell into the container")
            cmd = []
        aliDock.waitSshUp()
        aliDock.shell(cmd)
    elif args.action == "root":
        LOG.info("Starting a root shell into the container (use it at your own risk)")
        aliDock.rootShell()
    elif not created:
        LOG.info("Container is already running")

def processStatus(aliDock):
    if aliDock.isRunning():
        LOG.info("Container is running")
        exit(0)
    LOG.error("Container is not running")
    exit(1)

def processStop(aliDock):
    LOG.info("Destroying the container")
    aliDock.stop()

def processActions(args):

    if os.getuid() == 0:
        raise AliDockError("refusing to execute as root: use an unprivileged user account")

    aliDock = AliDock()

    try:
        if aliDock.hasUpdates():
            LOG.error("You are using an obsolete version of alidock.")
            LOG.error("Upgrade NOW with:")
            LOG.error("    pip install alidock --upgrade")
    except AliDockError:
        LOG.warning("Cannot check for updates this time")

    if args.action in ["enter", "start", "root"]:
        processEnterStart(aliDock, args)
    elif args.action == "status":
        processStatus(aliDock)
    elif args.action == "stop":
        processStop(aliDock)
    else:
        assert False, "invalid action"
