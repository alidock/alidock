FROM alisw/slc7-builder
RUN rpmdb --rebuilddb && yum clean all && rm -rf /var/cache/yum && \
    yum -y install xcalc tmux htop && \
    yum clean all && rm -rf /var/cache/yum
ADD sshd_config /etc/ssh/sshd_config
RUN pip install alibuild==v1.5.4rc4
RUN cd /tmp && \
    curl -LO https://bin.equinox.io/c/VdrWdbjqyF/cloudflared-stable-linux-amd64.tgz && \
    tar xzf cloudflared*.tgz && \
    mv -v cloudflared /usr/sbin && \
    which cloudflared && \
    rm -f /tmp/cloudflared*.tgz
