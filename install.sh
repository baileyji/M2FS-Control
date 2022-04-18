#!/bin/bash

#do manually first
# sudo git clone https://github.com/baileyji/M2FS-Control.git /M2FS-Control --recurse-submodules --branch ifum

#Set password
passwd

#Update the system and install dependencies
sudo mkdir -p /var/log/journal
sudo systemd-tmpfiles --create --prefix /var/log/journal
sudo systemctl restart systemd-journald
sudo apt update
sudo apt full-upgrade
sudo apt-get auto-remove
curl -sL https://deb.nodesource.com/setup_13.x | sudo -E bash -
sudo apt install python-scipy python-matplotlib nut python-flask zsh samba python-pip curl vim python-redis redis nodejs
sudo apt remove python-serial
#no to samba wins servers dhcp modification
#sudo pip install --upgrade pip
sudo pip install 'astropy<3' ##will get v 2
sudo pip install walrus pyyaml flask_wtf ipython pyserial==2.6 construct==2.0.6 pymodbus==1.5.2 bitstring==3.1.6 'quantities<0.13'
sudo npm install -g redis-commander --unsafe
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"


#Install M2FS-Control
cd /
#sudo git clone https://github.com/baileyji/M2FS-Control.git /M2FS-Control --recurse-submodules --branch ifum
sudo chown -R pi /M2FS-Control
sudo pip install -e /M2FS-Control/jbastro
sudo pip install -e /M2FS-Control/hole_mapper
sudo pip install -e /M2FS-Control

#Set the login shell to zsh
cd /M2FS-Control
cp -v ./zshrc ~/.zshrc
chsh -s /bin/zsh

#Install M2FS system config files
sudo cp -v ./etc/ups/* /etc/nut/
sudo cp -v ./etc/hostname /etc/
sudo cp -v ./etc/hosts /etc/
sudo cp -v ./etc/dhcpcd.conf /etc/
sudo cp -v ./etc/udev/rules.d/* /etc/udev/rules.d/
sudo cp -v ./etc/systemd/system/* /etc/systemd/system/
sudo cp -v ./etc/systemd/timesyncd.conf /etc/systemd/
sudo cp -v ./etc/avahi/services/smb.service /etc/avahi/services/
sudo mv -v /etc/samba/smb.conf /etc/samba/smb.conf.stock
sudo cp -v ./etc/samba/smb.conf /etc/samba/
sudo cp -v ./etc/redis/redis.conf /etc/redis/redis.conf
sudo cp -v ./redis/redis-server.service /lib/systemd/system/

#cp ./etc/ntp.conf /etc/

sudo udevadm control --reload-rules
sudo udevadm trigger

#Ensure systemd loads the new units
sudo systemctl daemon-reload
sudo systemctl enable m2fs_shutdown_button.service

#Bring UPS monitoring online
sudo systemctl enable nut-server.service

#Enable and start the director
sudo systemctl enable m2fs_director.service

sudo systemctl reboot now
