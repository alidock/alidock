FROM alisw/slc7-builder
RUN rpmdb --rebuilddb && yum clean all && rm -rf /var/cache/yum && \
    yum -y install xcalc tmux htop bash-completion tig pigz && \
    yum clean all && rm -rf /var/cache/yum
RUN pip install alibuild==v1.5.4rc5
RUN cd /tmp && \
    curl -LO https://bin.equinox.io/c/VdrWdbjqyF/cloudflared-stable-linux-amd64.tgz && \
    tar xzf cloudflared*.tgz && \
    mv -v cloudflared /usr/sbin && \
    which cloudflared && \
    rm -f /tmp/cloudflared*.tgz
RUN cd /tmp && \
    curl -LO https://github.com/github/hub/releases/download/v2.6.0/hub-linux-amd64-2.6.0.tgz && \
    tar xzf hub-linux*.tgz && \
    rm -f hub-linux*.tgz && \
    cd hub-linux* && \
    ./install && \
    cd .. && \
    rm -rf hub-linux*
