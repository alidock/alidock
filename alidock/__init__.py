"""alidock module"""

from __future__ import print_function
from argparse import ArgumentParser
from pwd import getpwuid
from time import sleep
import errno
import os
import os.path
import json
import subprocess
import docker
import jinja2
from requests.exceptions import RequestException
from pkg_resources import resource_string
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
        self.dockName = "/alidock"
        self.imageName = "alidock"
        self.dirOutside = os.path.expanduser("~/alidock")
        self.dirInside = "/home/alidock"
        self.logRelative = ".init.log"

    def isRunning(self):
        try:
            self.cli.containers.get(self.dockName)
        except docker.errors.NotFound:
            return False
        return True

    def getSshCommand(self):
        try:
            attrs = self.cli.containers.get(self.dockName).attrs
            sshPort = attrs["NetworkSettings"]["Ports"]["22/tcp"][0]["HostPort"]
        except (docker.errors.NotFound, KeyError) as exc:
            raise AliDockError("cannot find container, maybe it did not start up properly: "
                               "check log file {logOutside} for details. Error: {msg}"
                               .format(logOutside=os.path.join(self.dirOutside, self.logRelative),
                                       msg=exc))
        return ["ssh", "localhost", "-p", str(sshPort), "-Y", "-F/dev/null",
                "-oForwardX11Trusted=no", "-oUserKnownHostsFile=/dev/null",
                "-oStrictHostKeyChecking=no", "-oLogLevel=QUIET",
                "-i", os.path.join(self.dirOutside, ".ssh", "id_rsa")]

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
        os.execvp("docker", ["docker", "exec", "-it", self.dockName, "/bin/bash"])

    def run(self):
        # Create directory to be shared with the container
        try:
            os.mkdir(self.dirOutside)
        except OSError as exc:
            if not os.path.isdir(self.dirOutside) or exc.errno != errno.EEXIST:
                raise AliDockError("cannot create directory {dir} to share with container, "
                                   "check permissions".format(dir=self.dirOutside))

        # Create initialisation script
        initSh = jinja2.Template(resource_string("alidock.helpers", "init.sh.j2"))
        userId = os.getuid()
        userName = getpwuid(userId).pw_name
        initShPath = os.path.join(self.dirOutside, ".init.sh")
        with open(initShPath, "w") as fil:
            fil.write(initSh.render(sharedDir=self.dirInside,
                                    logRelative=self.logRelative,
                                    userName=userName,
                                    userId=userId))
        os.chmod(initShPath, 0o755)

        # Start container with that script
        self.cli.containers.run(self.imageName,
                                command=[os.path.join(self.dirInside, ".init.sh")],
                                detach=True,
                                auto_remove=True,
                                cap_add=["SYS_PTRACE"],
                                name=self.dockName,
                                mounts=[docker.types.Mount(self.dirInside,
                                                           self.dirOutside, type="bind")],
                                ports={"22/tcp": None})  # None == random port

        return True

    def stop(self):
        try:
            self.cli.containers.get(self.dockName).remove(force=True)
        except docker.errors.NotFound:
            pass  # final state is fine, container is gone

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
        if args.tmux:
            LOG.info("Resuming tmux session in the container")
            cmd = ["-t", "tmux", "-u", "-CC", "new-session", "-A", "-s", "ad-tmux"]
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
    aliDock = AliDock()

    if args.action in ["enter", "start", "root"]:
        processEnterStart(aliDock, args)
    elif args.action == "status":
        processStatus(aliDock)
    elif args.action == "stop":
        processStop(aliDock)
    else:
        assert False, "invalid action"
