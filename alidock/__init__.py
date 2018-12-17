"""alidock module"""

from __future__ import print_function
import argparse
from argparse import ArgumentParser
from pwd import getpwuid
from time import time, sleep
from datetime import datetime as dt
import errno
import os
import os.path
import sys
import json
import platform
import subprocess
import yaml
from yaml import YAMLError
import docker
from docker.types import Mount
import jinja2
import requests
from requests.exceptions import RequestException
from pkg_resources import resource_string, parse_version, require
from alidock.log import Log
from alidock.util import splitEsc

LOG = Log()

class AliDockError(Exception):
    def __init__(self, msg):
        super(AliDockError, self).__init__()
        self.msg = msg
    def __str__(self):
        return self.msg

class AliDock(object):

    def __init__(self, overrideConf=None):
        self.cli = docker.from_env()
        self.dirInside = "/home/alidock"
        self.conf = {
            "dockName"          : "alidock",
            "imageName"         : "alisw/alidock:latest",
            "dirOutside"        : "~/alidock",
            "updatePeriod"      : 43200,
            "dontUpdateImage"   : False,
            "dontUpdateAlidock" : False,
            "useNvidiaRuntime"  : False,
            "mount"             : []
        }
        self.parseConfig()
        self.overrideConfig(overrideConf)
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

    def overrideConfig(self, override):
        if not override:
            return
        for k in self.conf:
            if not override.get(k) is None:
                self.conf[k] = override[k]

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
            outLog = os.path.join(self.conf["dirOutside"], ".alidock.log")
            raise AliDockError("cannot find container, maybe it did not start up properly: "
                               "check log file {outLog} for details. Error: {msg}"
                               .format(outLog=outLog, msg=exc))
        return ["ssh", "localhost", "-p", str(sshPort), "-Y", "-F/dev/null",
                "-oForwardX11Trusted=no", "-oUserKnownHostsFile=/dev/null", "-oLogLevel=QUIET",
                "-oStrictHostKeyChecking=no", "-oForwardX11Timeout=596h",
                "-i", os.path.join(os.path.expanduser(self.conf["dirOutside"]),
                                   ".alidock-ssh", "alidock.pem")]

    def waitSshUp(self):
        for _ in range(0, 50):
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

    def getUserMounts(self):
        dockMounts = []
        for mount in self.conf["mount"]:
            src, label, mode = splitEsc(mount, ":", 2)
            src = os.path.expanduser(src)
            if os.path.isfile(src):
                raise AliDockError("mount {src} is a file: only dirs allowed".format(src=src))
            if not label:
                label = os.path.basename(src)
            elif "/" in label or label in [".", ".."]:
                raise AliDockError("mount label {label} is invalid: label cannot contain a slash"
                                   "and cannot be equal to \"..\" or \".\"".format(label=label))
            mnt = os.path.join("/", "mnt", label)
            if not mode:
                mode = "rw"
            if mode not in ["rw", "ro"]:
                raise AliDockError("supported modes for mounts are \"rw\" and \"ro\", "
                                   "not {mode}".format(mode=mode))
            dockMounts.append(Mount(mnt, src, type="bind", read_only=(mode == "ro"),
                                    consistency="cached"))
        return dockMounts

    def run(self):
        # Create directory to be shared with the container
        outDir = os.path.expanduser(self.conf["dirOutside"])
        try:
            os.makedirs(outDir)
        except OSError as exc:
            if not os.path.isdir(outDir) or exc.errno != errno.EEXIST:
                raise AliDockError("cannot create directory {dir} to share with container, "
                                   "check permissions".format(dir=self.conf["dirOutside"]))

        # Create initialization scripts: one runs outside the container, the other inside
        userId = os.getuid()
        userName = getpwuid(userId).pw_name

        initShPath = os.path.join(outDir, ".alidock-init.sh")
        initSh = jinja2.Template(
            resource_string("alidock.helpers", "init-inside.sh.j2").decode("utf-8"))
        with open(initShPath, "w") as fil:
            fil.write(initSh.render(logFile=".alidock.log",
                                    sharedDir=self.dirInside,
                                    dockName=self.conf["dockName"].rsplit("-", 1)[0],
                                    userName=userName,
                                    userId=userId))
        os.chmod(initShPath, 0o700)

        initOutsideShPath = os.path.join(outDir, ".alidock-init-host.sh")
        initOutsideSh = jinja2.Template(
            resource_string("alidock.helpers", "init-outside.sh.j2").decode("utf-8"))
        with open(initOutsideShPath, "w") as fil:
            fil.write(initOutsideSh.render(operatingSystem=platform.system(),
                                           logFile=".alidock-host.log",
                                           alidockDir=os.path.expanduser(self.conf["dirOutside"])))
        os.chmod(initOutsideShPath, 0o700)

        # Execute the script on the host immediately: errors are fatal
        try:
            nul = open(os.devnull, "w")
            subprocess.check_call(initOutsideShPath, stdout=nul, stderr=nul)
        except subprocess.CalledProcessError:
            raise AliDockError("the host initialization script failed, "
                               "check {log}".format(
                                   log=os.path.join(self.conf["dirOutside"], ".alidock-host.log")))

        dockEnvironment = []
        dockRuntime = None

        # Define which mounts to expose to the container. On non-Linux, we need a native volume too
        dockMounts = [Mount(self.dirInside, outDir, type="bind", consistency="cached")]
        if platform.system() != "Linux":
            dockMounts.append(Mount("/persist", "persist-"+self.conf["dockName"], type="volume"))

        dockMounts += self.getUserMounts()  # user-defined mounts

        if self.conf["useNvidiaRuntime"]:
            if self.hasRuntime("nvidia"):
                dockRuntime = "nvidia"
                dockEnvironment = ["NVIDIA_VISIBLE_DEVICES=all"]
            else:
                raise AliDockError("cannot find the NVIDIA runtime in your Docker installation")

        # Start container with that script
        self.cli.containers.run(self.conf["imageName"],
                                command=[os.path.join(self.dirInside, ".alidock-init.sh")],
                                detach=True,
                                auto_remove=True,
                                cap_add=["SYS_PTRACE"],
                                environment=dockEnvironment,
                                hostname=self.conf["dockName"],
                                name=self.conf["dockName"],
                                mounts=dockMounts,
                                ports={"22/tcp": None}, # None == random port
                                runtime=dockRuntime)

        return True

    def stop(self):
        try:
            self.cli.containers.get(self.conf["dockName"]).remove(force=True)
        except docker.errors.NotFound:
            pass  # final state is fine, container is gone

    def pull(self):
        try:
            self.cli.images.pull(self.conf["imageName"])
        except docker.errors.APIError as exc:
            raise AliDockError(str(exc))

    def hasRuntime(self, runtime):
        return runtime in self.cli.info()["Runtimes"].keys()

    def hasUpdates(self, stateFileRelative, updatePeriod, nagOnUpdate, updateFunc):
        """Generic function that checks for updates every updatePeriod seconds, saving the state
           on stateFileRelative (relative to the container's home directory). It returns True in
           case there is an update, False in case there is none. A custom function updateFunc is
           ran to determine whether to update. Set nagOnUpdate to True if, upon an update, the
           state file should not be updated in order to trigger another check at the next run (this
           nags users until they update)."""

        tsDir = os.path.expanduser(self.conf["dirOutside"])
        tsFn = os.path.join(tsDir, stateFileRelative)
        try:
            with open(tsFn) as fil:
                lastUpdate = int(fil.read())
        except (IOError, OSError, ValueError):
            lastUpdate = 0

        now = int(time())
        updateAvail = False
        if now - lastUpdate > int(updatePeriod):

            caught = None
            try:
                updateAvail = updateFunc()
            except AliDockError as exc:
                caught = exc

            if not updateAvail or not nagOnUpdate:
                try:
                    os.makedirs(tsDir)
                except OSError as exc:
                    if not os.path.isdir(tsDir) or exc.errno != errno.EEXIST:
                        raise exc
                with open(tsFn, "w") as fil:
                    fil.write(str(now))

            if caught is not None:
                # pylint: disable=raising-bad-type
                raise caught

        return updateAvail

    @staticmethod
    def doAutoUpdate():
        """Perform an automatic update of alidock only if it was installed in the custom virtual
           environment."""
        curModulePath = os.path.realpath(__file__)
        updateUrl = "https://bit.ly/alidock-installer"
        virtualenvPath = os.path.realpath(os.path.expanduser("~/.virtualenvs/alidock"))
        if curModulePath.startswith(virtualenvPath):
            LOG.warning("Updating alidock automatically")
            updateEnv = os.environ
            updateEnv["ALIDOCK_ARGS"] = " ".join(sys.argv[1:])
            updateEnv["ALIDOCK_RUN"] = "1"
            os.execvpe("bash",
                       ["bash", "-c",
                        "bash <(curl -fsSL {url}) --no-check-docker --quiet".format(url=updateUrl)],
                       updateEnv)

    def hasClientUpdates(self):
        """Check for client updates (alidock) without performing them. Returns True if updates are
           found, false otherwise."""

        if str(require(__package__)[0].version) == "LAST-TAG":
            # No check for local development or version from VCS
            return False

        def updateFunc():
            try:
                pyr = requests.get("https://pypi.org/pypi/{pkg}/json".format(pkg=__package__),
                                   timeout=5)
                pyr.raise_for_status()
                pypiData = pyr.json()
                availVersion = parse_version(pypiData["info"]["version"])
                localVersion = parse_version(require(__package__)[0].version)
                uploadTimeUTC = pypiData["releases"][str(availVersion)][0]["upload_time"]
                uploadTimeUTC = dt.strptime(uploadTimeUTC, "%Y-%m-%dT%H:%M:%S")
                updateAge = (dt.utcnow() - uploadTimeUTC).total_seconds()
                if availVersion > localVersion and updateAge > 900:
                    # Update is at least 15 min old to allow all PyPI caches to sync
                    return True
            except (RequestException, ValueError) as exc:
                raise AliDockError(str(exc))
            return False

        return self.hasUpdates(stateFileRelative=".alidock_pip_check",
                               updatePeriod=self.conf["updatePeriod"],
                               nagOnUpdate=True,
                               updateFunc=updateFunc)

    def hasImageUpdates(self):
        """Check for image updates without performing them. Returns True if updates are found, False
           otherwise."""

        if self.conf["dontUpdateImage"]:
            return False

        def updateFunc():
            try:
                try:
                    localHash = self.cli.images.get(
                        self.conf["imageName"]).attrs["RepoDigests"][0].split("@")[1]
                except docker.errors.NotFound:
                    # Image does not exist locally: no updates are available (run will fetch it)
                    return False
                availHash = self.cli.images.get_registry_data(
                    self.conf["imageName"]).attrs["Descriptor"]["digest"]
                return availHash != localHash
            except (IndexError, docker.errors.APIError) as exc:
                raise AliDockError(str(exc))

        return self.hasUpdates(stateFileRelative=".alidock_docker_check",
                               updatePeriod=self.conf["updatePeriod"],
                               nagOnUpdate=False,
                               updateFunc=updateFunc)

def entrypoint():
    argp = ArgumentParser()
    argp.add_argument("--quiet", "-q", dest="quiet", default=False, action="store_true",
                      help="Do not print any message")
    argp.add_argument("--version", "-v", dest="version", default=False, action="store_true",
                      help="Print current alidock version on stdout")

    # tmux: both normal and terminal integration ("control mode")
    tmuxArgs = argp.add_mutually_exclusive_group()
    tmuxArgs.add_argument("--tmux", "-t", dest="tmux", default=False, action="store_true",
                          help="Start or resume a detachable tmux session")
    tmuxArgs.add_argument("--tmux-control", "-T", dest="tmuxControl", default=False,
                          action="store_true",
                          help="Start or resume a detachable tmux session in control mode "
                               "(integration with your terminal)")

    # The following switches can be set in a configuration file
    argp.add_argument("--name", dest="dockName", default=None,
                      help="Override default container name [dockName]")
    argp.add_argument("--image", dest="imageName", default=None,
                      help="Override default image name [imageName]")
    argp.add_argument("--shared", dest="dirOutside", default=None,
                      help="Override host path of persistent home [dirOutside]")
    argp.add_argument("--mount", dest="mount", default=None, nargs="+",
                      help="Host directories to mount under /mnt inside alidock, in the format "
                           "/external/path[:label[:[rw|ro]]] [mount]")
    argp.add_argument("--update-period", dest="updatePeriod", default=None,
                      help="Override update check period [updatePeriod]")
    argp.add_argument("--no-update-image", dest="dontUpdateImage", default=None,
                      action="store_true",
                      help="Do not update the Docker image [dontUpdateImage]")
    argp.add_argument("--no-update-alidock", dest="dontUpdateAlidock", default=None,
                      action="store_true",
                      help="Do not update alidock automatically [dontUpdateAlidock]")
    argp.add_argument("--nvidia", dest="useNvidiaRuntime", default=None,
                      action="store_true",
                      help="Launch container using the NVIDIA Docker runtime [useNvidiaRuntime]")

    argp.add_argument("action", default="enter", nargs="?",
                      choices=["enter", "root", "exec", "start", "status", "stop"],
                      help="What to do")

    argp.add_argument("shellCmd", nargs=argparse.REMAINDER,
                      help="Command to execute in the container (works with exec)")

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

        try:
            if aliDock.hasImageUpdates():
                LOG.info("Updating container image, hold on")
                aliDock.pull()
                LOG.warning("Container updated, you may want to free some space with:")
                LOG.warning("    docker system prune")
        except AliDockError:
            LOG.warning("Cannot update container image this time")

        LOG.info("Creating container, hold on")
        aliDock.run()
    if args.action == "enter":
        if (args.tmux or args.tmuxControl) and os.environ.get("TMUX") is None:
            LOG.info("Resuming tmux session in the container")
            cmd = ["-t", "tmux", "-u", "-CC", "new-session", "-A", "-s", "ad-tmux"]
            if args.tmux:
                cmd.remove("-CC")
        elif args.tmux or args.tmuxControl:
            raise AliDockError("already in a tmux session")
        else:
            LOG.info("Starting a shell into the container")
            cmd = []
        aliDock.waitSshUp()
        aliDock.shell(cmd)
    elif args.action == "exec":
        LOG.info("Executing command in the container")
        aliDock.waitSshUp()
        aliDock.shell(["-t"] + args.shellCmd)
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
    LOG.info("Shutting down the container")
    aliDock.stop()

def processActions(args):

    if args.version:
        ver = str(require(__package__)[0].version)
        if ver == "LAST-TAG":
            ver = "development version"
        print("{prog} {version}".format(prog=__package__, version=ver))
        return

    if os.getuid() == 0:
        raise AliDockError("refusing to execute as root: use an unprivileged user account")

    aliDock = AliDock(args.__dict__)

    try:
        if not aliDock.conf["dontUpdateAlidock"] and aliDock.hasClientUpdates():
            aliDock.doAutoUpdate()
            LOG.error("You are using an obsolete version of alidock.")
            LOG.error("Upgrade NOW with:")
            LOG.error("    bash <(curl -fsSL https://bit.ly/alidock-installer)")
    except AliDockError:
        LOG.warning("Cannot check for alidock updates this time")

    if args.action in ["enter", "exec", "root", "start"]:
        processEnterStart(aliDock, args)
    elif args.action == "status":
        processStatus(aliDock)
    elif args.action == "stop":
        processStop(aliDock)
    else:
        assert False, "invalid action"
