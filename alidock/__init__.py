"""alidock module"""

from __future__ import print_function
import argparse
from time import time, sleep
from datetime import datetime as dt
from io import open
import errno
import os
import os.path
import posixpath
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
from alidock.argumentparser import AliDockArgumentParser
from alidock.log import Log
from alidock.util import splitEsc, getUserId, getUserName, execReturn, deactivateVenv, \
  getRocmVideoGid

LOG = Log()
INSTALLER_URL = "https://raw.githubusercontent.com/alidock/alidock/master/alidock-installer.sh"

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
        self.userName = getUserName()
        self.conf = self.getDefaultConf()
        self.parseConfig()
        self.overrideConfig(overrideConf)
        self.conf["dockName"] = "{dockName}-{userId}".format(dockName=self.conf["dockName"],
                                                             userId=getUserId())

    @staticmethod
    def getDefaultConf():
        return {
            "dockName"          : "alidock",
            "imageName"         : "alipier/alidock:latest",
            "dirOutside"        : os.path.join("~", "alidock"),
            "updatePeriod"      : 43200,
            "dontUpdateImage"   : False,
            "dontUpdateAlidock" : False,
            "useNvidiaRuntime"  : False,
            "enableRocmDevices" : False,
            "mount"             : [],
            "cvmfs"             : False,
            "web"               : False,
            "debug"             : False
        }

    def parseConfig(self):
        confFile = os.path.join(os.path.expanduser("~"), ".alidock-config.yaml")
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
        runStatus = {}
        try:
            runContainer = self.cli.containers.get(self.conf["dockName"])
            try:
                runStatus["image"] = runContainer.image.attrs["RepoTags"][0]
            except IndexError:
                runStatus["image"] = runContainer.image.attrs["Id"]
        except docker.errors.NotFound:
            pass
        return runStatus

    def getSshCommand(self):
        dockName = self.conf["dockName"].rsplit("-", 1)[0]
        outPath = os.path.expanduser(os.path.join(self.conf["dirOutside"], ".alidock-" + dockName))
        try:
            attrs = self.cli.containers.get(self.conf["dockName"]).attrs
            sshPort = attrs["NetworkSettings"]["Ports"]["22/tcp"][0]["HostPort"]
        except (docker.errors.NotFound, KeyError) as exc:
            outLog = os.path.join(outPath, "log.txt")
            try:
                with open(outLog, "a+"):
                    pass
            except (IOError, OSError) as exc:
                pass
            raise AliDockError("cannot log into the container, maybe it did not start up properly: "
                               "check log file {outLog} for details and make sure your Docker "
                               "version is updated. Error: {msg}"
                               .format(outLog=outLog, msg=exc))

        # Private key path detection. Older versions of alidock use different paths: do not break!
        privKey = os.path.join(outPath, "ssh", "alidock.pem")
        if not os.path.isfile(privKey):
            privKey = os.path.join(os.path.expanduser(self.conf["dirOutside"]),
                                   ".alidock-ssh", "alidock.pem")

        if platform.system() != "Windows":
            # Reuse the same SSH connection for efficiency (not supported by Windows OpenSSH)
            sshControl = ["-oControlPersist=yes", "-oControlMaster=auto",
                          "-oControlPath=" + os.path.join(outPath, "ssh", "control")]
        else:
            sshControl = []

        if self.conf["web"]:
            # No X11 forwarding in web mode
            xForward = []
        else:
            xForward = ["-oForwardX11Trusted=no", "-Y", "-oForwardX11Timeout=596h"]

        logLevel = "-oLogLevel=" + ("DEBUG" if self.conf["debug"] else "QUIET")

        return ["ssh", "localhost", "-p", str(sshPort), "-F/dev/null", "-l", self.userName,
                "-oUserKnownHostsFile=/dev/null", logLevel, "-oStrictHostKeyChecking=no",
                "-oIdentitiesOnly=yes", "-i", privKey] + sshControl + xForward

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
        try:
            attrs = self.cli.containers.get(self.conf["dockName"]).attrs
            xPort = attrs["NetworkSettings"]["Ports"]["14500/tcp"][0]["HostPort"]
        except (docker.errors.NotFound, KeyError):
            xPort = None
        if not xPort and platform.system() == "Windows" and "DISPLAY" not in os.environ:
            # On Windows if no DISPLAY environment is set we assume a sensible default
            os.environ["DISPLAY"] = "127.0.0.1:0.0"
        if xPort:
            LOG.warning("X11 web browser access: http://localhost:{port}".format(port=xPort))
        execReturn("ssh", self.getSshCommand() + (cmd if cmd else []))

    def rootShell(self):
        execReturn("docker", ["docker", "exec", "-it", self.conf["dockName"], "/bin/bash"])

    def getUserMounts(self):
        dockMounts = []
        for mount in self.conf["mount"]:
            src, label, mode = splitEsc(mount, ":", 2)
            src = os.path.expanduser(src).rstrip("/")
            if not src:
                src = "/"
            if os.path.isfile(src):
                raise AliDockError("mount {src} is a file: only dirs allowed".format(src=src))
            if not label:
                label = "root" if src == "/" else os.path.basename(src)
            elif "/" in label or label in [".", ".."]:
                raise AliDockError("mount label {label} is invalid: label cannot contain a slash"
                                   "and cannot be equal to \"..\" or \".\"".format(label=label))
            mnt = posixpath.join("/", "mnt", label)
            if not mode:
                mode = "rw"
            if mode not in ["rw", "ro"]:
                raise AliDockError("supported modes for mounts are \"rw\" and \"ro\", "
                                   "not {mode}".format(mode=mode))
            dockMounts.append(Mount(mnt, src, type="bind", read_only=(mode == "ro"),
                                    consistency="cached"))
        return dockMounts

    def initDarwin(self):
        # macOS only: exclude "sw" directory from indexing and backup
        outDir = os.path.expanduser(self.conf["dirOutside"])
        swDir = os.path.join(outDir, ".sw")
        swNoidx = os.path.join(outDir, ".sw.noindex")
        if os.path.isdir(swDir) and not os.path.islink(swDir) and not os.path.exists(swNoidx):
            # An old installation uses .sw: rename to .sw.noindex
            os.rename(swDir, swNoidx)
        try:
            # Create .sw.noindex (not indexed by Spotlight because of `.noindex`)
            os.mkdir(swNoidx)
        except OSError as exc:
            if not os.path.isdir(swNoidx) or exc.errno != errno.EEXIST:
                raise AliDockError("cannot create {dir}".format(dir=swNoidx))
        try:
            # Symlink .sw -> .sw.noindex
            os.symlink(".sw.noindex", swDir)
        except OSError as exc:
            if not os.path.islink(swDir) or exc.errno != errno.EEXIST:
                raise AliDockError("cannot symlink .sw -> .sw.noindex %s" % str(exc))
        try:
            # Exclude .sw.noindex from Time Machine backups (check with `xattr`)
            nul = open(os.devnull, "w")
            subprocess.check_call(["tmutil", "addexclusion", swNoidx], stdout=nul, stderr=nul)
        except subprocess.CalledProcessError as exc:
            raise AliDockError("cannot exclude {dir} from Time Machine backups, "
                               "tmutil returned {ret}".format(dir=swNoidx, ret=exc.returncode))

    def run(self):
        # Create directory to be shared with the container
        outDir = os.path.expanduser(self.conf["dirOutside"])
        dockName = self.conf["dockName"].rsplit("-", 1)[0]
        runDir = os.path.join(outDir, ".alidock-" + dockName)
        try:
            os.makedirs(runDir)
        except OSError as exc:
            if not os.path.isdir(runDir) or exc.errno != errno.EEXIST:
                raise AliDockError("cannot create directory {dir} to share with container, "
                                   "check permissions".format(dir=self.conf["dirOutside"]))

        dockDevices = []
        # {"groupname": gid} added inside the container (gid=None == I don't care)
        addGroups = {"video": getRocmVideoGid()}
        if self.conf["enableRocmDevices"] and addGroups["video"]:
            dockDevices += ["/dev/kfd", "/dev/dri"]
        elif self.conf["enableRocmDevices"]:
            raise AliDockError("cannot enable ROCm: check your ROCm installation")
        else:
            del addGroups["video"]

        initShPath = os.path.join(runDir, "init.sh")
        initSh = jinja2.Template(
            resource_string("alidock.helpers", "init.sh.j2").decode("utf-8"))
        with open(initShPath, "w", newline="\n") as fil:
            fil.write(initSh.render(sharedDir=self.dirInside,
                                    runDir=posixpath.join(self.dirInside, ".alidock-" + dockName),
                                    dockName=dockName,
                                    userName=self.userName,
                                    userId=getUserId(),
                                    useWebX11=self.conf["web"],
                                    addGroups=addGroups))

        os.chmod(initShPath, 0o700)

        if platform.system() == "Darwin":
            self.initDarwin()

        dockEnvironment = []
        dockRuntime = None

        # Define which mounts to expose to the container. On non-Linux, we need a native volume too
        dockMounts = [Mount(self.dirInside, outDir, type="bind", consistency="cached")]
        if platform.system() != "Linux":
            dockMounts.append(Mount("/persist", "persist-"+self.conf["dockName"], type="volume"))

        if self.conf["cvmfs"]:
            dockMounts.append(Mount(source="/cvmfs",
                                    target="/cvmfs",
                                    type="bind",
                                    propagation="shared" if platform.system() == "Linux" else None))

        dockMounts += self.getUserMounts()  # user-defined mounts

        if self.conf["useNvidiaRuntime"]:
            if self.hasRuntime("nvidia"):
                dockRuntime = "nvidia"
                dockEnvironment = ["NVIDIA_VISIBLE_DEVICES=all"]
            else:
                raise AliDockError("cannot find the NVIDIA runtime in your Docker installation")

        # Ports to forward (None == random port)
        fwdPorts = {"22/tcp": ("127.0.0.1", None)}
        if self.conf["web"]:
            fwdPorts["14500/tcp"] = ("127.0.0.1", None)

        # Start container with that script
        self.cli.containers.run(self.conf["imageName"],
                                command=[self.dirInside + "/.alidock-" + dockName + "/init.sh"],
                                detach=True,
                                auto_remove=True,
                                cap_add=["SYS_PTRACE"],
                                environment=dockEnvironment,
                                hostname=self.conf["dockName"],
                                name=self.conf["dockName"],
                                mounts=dockMounts,
                                ports=fwdPorts,
                                runtime=dockRuntime,
                                devices=dockDevices,
                                group_add=addGroups.keys(),
                                shm_size="1G")

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
        virtualenvPath = os.path.realpath(os.path.expanduser("~/.virtualenvs/alidock"))
        if curModulePath.startswith(virtualenvPath):
            LOG.warning("Updating alidock automatically")
            updateEnv = os.environ
            deactivateVenv(updateEnv)
            updateEnv["ALIDOCK_ARGS"] = " ".join(sys.argv[1:])
            updateEnv["ALIDOCK_RUN"] = "1"
            os.execvpe("bash",
                       ["bash", "-c",
                        "bash <(curl -fsSL {u}) --no-check-docker --quiet".format(u=INSTALLER_URL)],
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
    argp = AliDockArgumentParser(atStartTitle="only valid if container is not running, "
                                              "not effective otherwise")
    argp.addArgument("--quiet", "-q", dest="quiet", default=False, action="store_true",
                     help="Do not print any message")
    argp.addArgument("--version", "-v", dest="version", default=False, action="store_true",
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
    argp.addArgument("--name", dest="dockName", default=None, config=True,
                     help="Override default container name")
    argp.addArgument("--update-period", dest="updatePeriod", default=None, config=True,
                     help="Override update check period")
    argp.addArgument("--no-update-alidock", dest="dontUpdateAlidock", default=None, config=True,
                     action="store_true",
                     help="Do not update alidock automatically")
    argp.addArgument("--debug", dest="debug", default=None, config=True,
                     action="store_true",
                     help="Increase verbosity")

    # Args valid only when starting the container; they can be set in a config file
    argp.addArgumentStart("--image", dest="imageName", default=None, config=True,
                          help="Override default image name")
    argp.addArgumentStart("--shared", dest="dirOutside", default=None, config=True,
                          help="Override host path of persistent home")
    argp.addArgumentStart("--mount", dest="mount", default=None, nargs="+", config=True,
                          help="Host dirs to mount under /mnt inside alidock, in the format "
                               "/external/path[:label[:[rw|ro]]]")
    argp.addArgumentStart("--no-update-image", dest="dontUpdateImage", default=None, config=True,
                          action="store_true",
                          help="Do not update the Docker image")
    argp.addArgumentStart("--nvidia", dest="useNvidiaRuntime", default=None, config=True,
                          action="store_true",
                          help="Use the NVIDIA Docker runtime")
    argp.addArgumentStart("--rocm", dest="enableRocmDevices", default=None, config=True,
                          action="store_true",
                          help="Expose devices needed by ROCm")
    argp.addArgumentStart("--cvmfs", dest="cvmfs", default=None, config=True,
                          action="store_true",
                          help="Mount CVMFS inside the container")
    argp.addArgumentStart("--web", dest="web", default=None, config=True,
                          action="store_true",
                          help="Make X11 available from a web browser")

    argp.add_argument("action", default="enter", nargs="?",
                      choices=["enter", "root", "exec", "start", "status", "stop"],
                      help="What to do")

    argp.add_argument("shellCmd", nargs=argparse.REMAINDER,
                      help="Command to execute in the container (works with exec)")

    argp.genConfigHelp(AliDock.getDefaultConf())
    args = argp.parse_args()

    LOG.setQuiet(args.quiet)

    try:
        processActions(args, argp.argsAtStart)
    except AliDockError as exc:
        LOG.error("Cannot continue: {msg}".format(msg=exc))
        exit(10)
    except docker.errors.APIError as exc:
        LOG.error("Docker error: {msg}".format(msg=exc))
        exit(11)
    except RequestException as exc:
        LOG.error("Cannot communicate to Docker, is it running? Full error: {msg}".format(msg=exc))
        exit(12)

def checkArgsAtStart(args, argsAtStart):
    ignoredArgs = []
    for sta in argsAtStart:
        if args.__dict__[sta.config] is not None:
            ignoredArgs.append(sta.option)
    if ignoredArgs:
        LOG.warning("The following options are being ignored:")
        for ign in ignoredArgs:
            LOG.warning("    " + ign)
        LOG.warning("This is because alidock is already running and they are only valid when a "
                    "new container is started.")
        LOG.warning("You may want to stop alidock first with:")
        LOG.warning("    alidock stop")
        LOG.warning("and try again. Check `alidock --help` for more information")

def processEnterStart(aliDock, args, argsAtStart):
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
    else:
        # Container is running. Check if user has specified parameters that will be ignored and warn
        checkArgsAtStart(args, argsAtStart)

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
    runStatus = aliDock.isRunning()
    if runStatus:
        LOG.info("Container is running (name: {name}, image: {image})".format(
            name=aliDock.conf["dockName"], image=runStatus["image"]))
        exit(0)
    LOG.error("Container is not running")
    exit(1)

def processStop(aliDock):
    LOG.info("Shutting down the container")
    aliDock.stop()

def processActions(args, argsAtStart):

    if args.version:
        ver = str(require(__package__)[0].version)
        if ver == "LAST-TAG":
            ver = "development version"
        print("{prog} {version}".format(prog=__package__, version=ver))
        return

    if getUserId() == 0:
        raise AliDockError("refusing to execute as root: use an unprivileged user account")

    aliDock = AliDock(args.__dict__)

    try:
        hasUpdates = aliDock.hasClientUpdates()
        if hasUpdates and platform.system() == "Windows":
            # No auto update on Windows at the moment
            LOG.error("You are using an obsolete version of alidock. Use pip to upgrade it.")
        elif hasUpdates and not aliDock.conf["dontUpdateAlidock"]:
            aliDock.doAutoUpdate()
            LOG.error("You are using an obsolete version of alidock.")
            LOG.error("Upgrade NOW with:")
            LOG.error("    bash <(curl -fsSL {url})".format(url=INSTALLER_URL))
    except AliDockError:
        LOG.warning("Cannot check for alidock updates this time")

    if args.action in ["enter", "exec", "root", "start"]:
        processEnterStart(aliDock, args, argsAtStart)
    elif args.action == "status":
        processStatus(aliDock)
    elif args.action == "stop":
        processStop(aliDock)
    else:
        assert False, "invalid action"
