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
from pkg_resources import resource_string
from alidock.log import info, error

class AliDock(object):
    def __init__(self):
        self.cli = docker.from_env()
        self.dockName = "/alidock"
        self.imageName = "alidock"
        self.dirOutside = os.path.expanduser("~/alidock")
        self.dirInside = "/home/alidock"

    def isRunning(self):
        try:
            self.cli.containers.get(self.dockName)
        except docker.errors.NotFound:
            return False
        return True

    def getSshCommand(self):
        attrs = self.cli.containers.get(self.dockName).attrs
        sshPort = attrs["NetworkSettings"]["Ports"]["22/tcp"][0]["HostPort"]
        return ["ssh", "localhost", "-p", str(sshPort), "-Y", "-F/dev/null",
                "-oForwardX11Trusted=no", "-oUserKnownHostsFile=/dev/null",
                "-oStrictHostKeyChecking=no", "-oLogLevel=QUIET",
                "-i", os.path.join(self.dirOutside, ".ssh", "id_rsa")]

    def waitSshUp(self):
        for _ in range(0, 10):
            try:
                nul = open(os.devnull, "w")
                subprocess.check_call(self.getSshCommand() + ["/bin/true"], stdout=nul, stderr=nul)
            except subprocess.CalledProcessError:
                sleep(0.5)
            else:
                return True
        return False

    def shell(self):
        os.execvp("ssh", self.getSshCommand())

    def run(self):
        # Create directory to be shared with the container
        try:
            os.mkdir(self.dirOutside)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                error("Cannot create directory {dir}".format(dir=self.dirOutside))
                return False

        # Create initialisation script
        initSh = jinja2.Template(resource_string("alidock.helpers", "init.sh.j2"))
        userId = os.getuid()
        userName = getpwuid(userId).pw_name
        initShPath = os.path.join(self.dirOutside, ".init.sh")
        with open(initShPath, "w") as fil:
            fil.write(initSh.render(sharedDir=self.dirInside,
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
        self.cli.containers.get(self.dockName).remove(force=True)

def entrypoint():
    argp = ArgumentParser()
    argp.add_argument("--debug", dest="debug", default=False, action="store_true",
                      help="Enable debug messages")
    argp.add_argument("action", default="enter", nargs="?",
                      choices=["enter", "start", "status", "stop"],
                      help="What to do")
    args = argp.parse_args()
    aliDock = AliDock()

    if args.action in ["enter", "start"]:
        if not aliDock.isRunning():
            info("Creating container, hold on")
            aliDock.run()
            if args.action == "enter":
                aliDock.waitSshUp()
        if args.action == "enter":
            info("Starting a shell into the container")
            aliDock.shell()
    elif args.action == "status":
        error("status not implemented")
    elif args.action == "stop":
        info("Destroying the container")
        aliDock.stop()
    else:
        assert False, "invalid action"
