alidock
=======

[![Build Status](https://travis-ci.org/mconcas/alidock.svg?branch=master)](https://travis-ci.org/mconcas/alidock)

Run your ALICE environment from a container easily. For the moment this is under heavy development
and not ready for production.

How to use the Proof of Concept: clone this repository, and then:

    cd etc
    docker build . -t alidock
    cd ..
    bin/alidock-poc

Every other shell can be opened rerunning:

    bin/alidock-poc

The container will run in the background. You can stop the container with:

    bin/alidock-poc stop

For the moment, the project shares a local directory whose location is:

  * `/tmp/alidock_shared` on your laptop,
  * `/shared` inside the container (which is also the container user's home dir)
