alidock
=======

[![Build Status](https://travis-ci.com/dberzano/alidock.svg?branch=master)](https://travis-ci.com/dberzano/alidock)
[![PyPI version](https://badge.fury.io/py/alidock.svg)](https://badge.fury.io/py/alidock)

Run your ALICE environment from a container. Install [Docker](https://docs.docker.com/install/),
then:

    pip install alidock
    alidock

You are instantly dropped in a shell with a consistent ALICE environment from a Docker container.
From there you can directly run, for example:

    aliBuild build init O2
    aliBuild build O2 --defaults o2

and it will download the precompiled binaries for you.

Your home directory in the container, called `/home/alidock`, is available from outside the
container in `~/alidock`. This means you can use your favourite text editor or IDE from your laptop,
no need to edit from inside the container.
