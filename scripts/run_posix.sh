#!/bin/bash

#Get pip
easy_install pip

#install ipython and needed python packages
pip install pyserial==2.6
pip install construct==2.0.6
pip install ipython

#You must figure out these by plugging and unplugging usb cables
# and looking at what appears in /dev. I've set them to way appears on my mac
GUIDER='tty.usbmodem00'
SHLED='tty.usbserial-'
SHLENSLET='tty.usbmodem'
GALILB='tty.usbserial-'
GALILR='tty.usbserial-'
SHOER='tty.usbmodem'
SHOEB='tty.usbmodem'

sudo ln -s /dev/$GUIDER /dev/m2fs_guider
sudo ln -s /dev/$SHLED /dev/m2fs_shLED
sudo ln -s /dev/$SHLENSLET /dev/m2fs_shLenslet
sudo ln -s /dev/$GALILB /dev/m2fs_galilR
sudo ln -s /dev/$GALILR /dev/m2fs_galilB
sudo ln -s /dev/$SHOER /dev/m2fs_shoeR
sudo ln -s /dev/$SHOEB /dev/m2fs_shoeB
