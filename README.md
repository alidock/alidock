alidock
=======

[![Build Status](https://travis-ci.com/alidock/alidock.svg?branch=master)](https://travis-ci.com/alidock/alidock)
[![PyPI version](https://badge.fury.io/py/alidock.svg)](https://badge.fury.io/py/alidock)
[![Docker pulls](https://img.shields.io/docker/pulls/alisw/alidock.svg?logo=docker&label=pulls)](https://hub.docker.com/r/alisw/alidock)

Run your ALICE environment from a container. Install [Docker](https://docs.docker.com/install/),
then:

    bash <(curl -fsSL https://raw.githubusercontent.com/alidock/alidock/master/alidock-installer.sh)

Windows users can [install the package with pip](https://pypi.org/pypi/alidock) instead.

You may need to close and reopen your terminal as advised. Run alidock now:

    alidock

You are instantly dropped in a shell with a consistent ALICE environment from a Docker container.
From there you can directly run, for example:

    aliBuild init O2@dev --defaults o2
    aliBuild build O2 --defaults o2

and it will download the precompiled binaries for you.

Your home directory in the container, called `/home/alidock`, is available from outside the
container in `~/alidock`. This means you can use your favourite text editor or IDE from your laptop,
no need to edit from inside the container.

📜 Full documentation available [on the Wiki](https://github.com/alidock/alidock/wiki).
