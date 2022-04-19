#!/bin/sh
#  restart_services.sh
#  m2fs
#
#  Created by Jeb Bailey on 7/25/12.
sudo systemctl --system daemon-reload

sudo systemctl restart m2fs_galilR.service
sudo systemctl restart m2fs_galilB.service
sudo systemctl restart m2fs_director.service
sudo systemctl restart m2fs_shutdown_button.service
sudo systemctl restart m2fs_datalogger.service

sudo systemctl restart redis-server.service

sudo systemctl restart m2fs_shoeR.service
sudo systemctl restart m2fs_shoeB.service
sudo systemctl restart m2fs_slitController.service
sudo systemctl restart m2fs_shackhartman.service
sudo systemctl restart m2fs_plugController.service
sudo systemctl restart m2fs_guider.service
sudo systemctl restart m2fs_mcalled.service

sudo systemctl restart ifum_selector.service
sudo systemctl restart ifum_occulterH.service
sudo systemctl restart ifum_occulterH.service
sudo systemctl restart ifum_occulterH.service
sudo systemctl restart ifum_shield.service
sudo systemctl restart ifum_shoe.service
