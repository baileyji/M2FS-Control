#!/bin/bash

#Set password
passwd

#Update the system and install dependencies
sudo systemctl set-default multi-user.target
sudo apt update
sudo apt full-upgrade
sudo apt-get auto remove
sudo apt install python-scipy python-astropy python-matplotlib nut python-flask zsh samba
sudo pip install --upgrade pip
sudo pip install ipython pyserial==2.6 construct==2.0.6 flask flask_wtf
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
cp -v zshrc ~/.zshrc
cd /
git clone https://github.com/YSAS/M2FS-Control.git

#Set the login shell to bash
chsh -s /bin/zsh

#Install M2FS system config files
sudo cp -v ./etc/ups/* /etc/nut/
sudo cp -v ./etc/hostname /etc/hostname
sudo cp -v ./etc/udev/rules.d/m2fs.rules /etc/udev/rules.d/
sudo cp -v ./etc/systemd/system/* /etc/systemd/system/ 
sudo cp -v ./etc/avahi/services/smb.service /etc/avahi/services/
sudo mv -v /etc/samba/smb.conf /etc/samba/smb.conf.stock
sudo cp -v ./etc/samba/smb.conf /etc/samba/
#cp -v ./vimrc /home/root/.vimrc

#Ensure systemd loads the new units
systemctl daemon-reload

#Bring ethernet online
systemctl enable ethernet_hack.service
systemctl start ethernet_hack.service

#Bring UPS monitoring online
systemctl restart nut-server.service
systemctl restart nut-monitor.service

#cp ./etc/ntp.conf /etc/

#Enable and start the director
systemctl enable director.service
systemctl start director.service
