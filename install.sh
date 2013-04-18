#!/bin/bash
easy_install pip
pip install ipython
pip install construct
opkg install ntp.systemd

cp -rv ./etc/* /etc/
#useradd -m -p $(perl -e 'print crypt($ARGV[0], "password")' "m2fsuser") m2fsuser
#useradd -m -p $(perl -e 'print crypt($ARGV[0], "password")' "m2fsadmin") m2fsadmin
systemctl daemon-reload
systemctl enable director.service
systemctl enable ethernet_hack.service
systemctl enable nut-server.service
systemctl condrestart nut-server.service
systemctl condrestart director.service