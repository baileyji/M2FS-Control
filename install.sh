#!/bin/bash

#Install M2FS system config files
cp -rv ./etc/* /etc/
cp -v ./bashrc /home/root/.bashrc
cp -v ./bashrc /home/root/.bash_login
cp -v ./vimrc /home/root/.vimrc
#Ensure systemd loads the new units
systemctl daemon-reload

#Bring ethernet online
systemctl enable ethernet_hack.service
systemctl start ethernet_hack.service

#Bring UPS monitoring online
mkdir /var/state/ups
chmod 0770 /var/state/ups
chown root:run /var/state/ups
systemctl enable nut-server.service
systemctl start nut-server.service

#Get ntp installed
opkg install ntp

#Get pip
easy_install pip

#install ipython and needed python packages
pip install ipython
pip install construct

#useradd -m -p $(perl -e 'print crypt($ARGV[0], "password")' "m2fsuser") m2fsuser
#useradd -m -p $(perl -e 'print crypt($ARGV[0], "password")' "m2fsadmin") m2fsadmin

#Enable and start the director
systemctl enable director.service
systemctl start director.service