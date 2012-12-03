#!/bin/bash
cp -rv ./etc /etc
useradd -m -p $(perl -e 'print crypt($ARGV[0], "password")' "m2fsuser") m2fsuser
useradd -m -p $(perl -e 'print crypt($ARGV[0], "password")' "m2fsadmin") m2fsadmin
mkdir -p /home/m2fs/plates
mkdir -p /home/m2fsuser/copy_platefiles_into_me
ln -s /home/m2fs/plates /home/m2fsuser/plates
systemctl daemon-reload
systemctl enable director.service
systemctl condrestart director.service