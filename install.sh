#!/bin/bash

#Set password
passwd

#Update the system and install dependencies
sudo mkdir -p /var/log/journal
sudo systemd-tmpfiles --create --prefix /var/log/journal
sudo systemctl restart systemd-journald
sudo apt update
sudo apt full-upgrade
sudo apt-get auto remove
sudo apt install python-scipy python-astropy python-matplotlib nut python-flask zsh samba python-pip curl
sudo pip install --upgrade pip
sudo apt remove python-serial
sudo pip install ipython pyserial==2.6 construct==2.0.6 flask_wtf
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"


#Install M2FS-Control
cd /
sudo git clone https://github.com/YSAS/M2FS-Control.git /M2FS-Control --recurse-submodules --branch develop
sudo chown -R pi /M2FS-Control
cd /M2FS-Control

#Set the login shell to zsh
cp -v ./zshrc ~/.zshrc
chsh -s /bin/zsh

#Install M2FS system config files
sudo cp -v ./etc/ups/* /etc/nut/
sudo cp -v ./etc/hostname /etc/
sudo cp -v ./etc/hosts /etc/
sudo cp -v ./etc/dhcpcd.conf /etc/
sudo cp -v ./etc/udev/rules.d/m2fs.rules /etc/udev/rules.d/
sudo cp -v ./etc/systemd/system/* /etc/systemd/system/ 
sudo cp -v ./etc/systemd/timesyncd.conf /etc/systemd/
sudo cp -v ./etc/avahi/services/smb.service /etc/avahi/services/
sudo mv -v /etc/samba/smb.conf /etc/samba/smb.conf.stock
sudo cp -v ./etc/samba/smb.conf /etc/samba/
sudo cp -v ./nut-driver.service /lib/systemd/system/nut-driver.service
#cp -v ./vimrc /home/root/.vimrc
#cp ./etc/ntp.conf /etc/

#Ensure systemd loads the new units
sudo systemctl daemon-reload
sudo systemctl enable shutdown_button.service
sudo systemctl start shutdown_button.service

#Bring ethernet online
#sudo systemctl enable ethernet_hack.service
#sudo systemctl start ethernet_hack.service

#Bring UPS monitoring online
sudo systemctl restart nut-server.service
sudo systemctl restart nut-monitor.service

#Enable and start the director
sudo systemctl enable director.service
sudo systemctl start director.service

#Enable and start the director
sudo systemctl enable targetlist.service
sudo systemctl start targetlist.service

sudo systemctl reboot now
