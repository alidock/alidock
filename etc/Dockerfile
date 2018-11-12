FROM alisw/slc7-builder
RUN rpmdb --rebuilddb && yum clean all && rm -rf /var/cache/yum && \
    yum -y install xcalc tmux && \
    yum clean all && rm -rf /var/cache/yum
RUN ssh-keygen -t rsa -f /etc/ssh/ssh_host_rsa_key -N ''
ADD sshd_config /etc/ssh/sshd_config
RUN pip install git+https://github.com/alisw/alibuild

#RUN yum install -y openssh-server
#RUN yum groupinstall -y 'X Window System'
