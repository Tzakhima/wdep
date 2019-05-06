#!/bin/bash

# Install required tools
yum install python36 python3-pip git -y

# Download Scripts
git clone https://github.com/Tzakhima/wdep.git

# move files
cp ./wdep/server/server.py /root/

# Create Unit file
cat <<EOT >> /etc/systemd/system/tm_daemon.service
[Unit]
Description=AWS Deployment Server

[Service]
Type=simple
ExecStart=/usr/bin/python3 /root/server.py
WorkingDirectory=/root/
Environment=AWS_ACCESS_KEY_ID=A
Environment=AWS_SECRET_ACCESS_KEY=A
Restart=always
RestartSec=2

[Install]
WantedBy=sysinit.target
EOT

# Register and start the service
systemctl daemon-reload && systemctl enable tm_daemon && systemctl start tm_daemon --no-block
