FROM alisw/slc7-builder
ADD alonid-llvm-3.9.0.repo /etc/yum.repos.d/alonid-llvm-3.9.0.repo
RUN rpmdb --rebuilddb && yum clean all && rm -rf /var/cache/yum && \
    yum -y install xcalc tmux htop bash-completion tig pigz nano ninja-build clang-3.9.0 && \
    ln -nfs /usr/bin/ninja-build /usr/local/bin/ninja && \
    ln -nfs /opt/llvm-3.9.0/bin/* /usr/local/bin/ && \
    yum clean all && rm -rf /var/cache/yum
RUN curl -Lo /usr/local/bin/git-clang-format https://llvm.org/svn/llvm-project/cfe/tags/RELEASE_701/final/tools/clang-format/git-clang-format && \
    chmod 0755 /usr/local/bin/git-clang-format
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
RUN pip install alibuild==v1.5.4
