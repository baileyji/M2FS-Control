#!/bin/bash

#Set the login shell to bash
chsh -s /bin/bash

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
mkdir -p /var/state/ups
chmod 0770 /var/state/ups
groupadd nut
chown root:nut /var/state/ups
systemctl enable nut-server.service
systemctl start nut-server.service
systemctl enable nut-monitor.service
systemctl start nut-monitor.service

#Get ntp installed
opkg install coreutils
opkg install ntp
cp ./etc/ntp.conf /etc/

#Get pip
#easy_install -U setuptools #needed by astropy
easy_install pip

#install ipython and needed python packages
pip install pyserial==2.6
pip install construct==2.0.6
pip install ipython
pip install flask
pip install flask_wtf
pip install ipdb
#pip install astropy #needs numpy >1.8 which bombed on install

#useradd -m -p $(perl -e 'print crypt($ARGV[0], "password")' "m2fsuser") m2fsuser
#useradd -m -p $(perl -e 'print crypt($ARGV[0], "password")' "m2fsadmin") m2fsadmin

#Enable and start the director
systemctl enable director.service
systemctl start director.service
