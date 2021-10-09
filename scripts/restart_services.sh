#!/bin/sh
#  restart_services.sh
#  m2fs
#
#  Created by Jeb Bailey on 7/25/12.
systemctl --system daemon-reload
systemctl restart m2fs_shoeR.service
systemctl restart m2fs_shoeB.service
systemctl restart m2fs_galilR.service
systemctl restart m2fs_galilB.service
systemctl restart m2fs_slitController.service
systemctl restart m2fs_shackhartman.service
systemctl restart m2fs_plugController.service
systemctl restart m2fs_guider.service
systemctl restart m2fs_director.service
systemctl restart m2fs_mcalled.service
systemctl restart m2fs_shutdown_button.service
systemctl restart m2fs_datalogger.service

systemctl restart ifum_selector.service
systemctl restart ifum_occulterH.service
systemctl restart ifum_occulterH.service
systemctl restart ifum_occulterH.service
systemctl restart ifum_shield.service
systemctl restart ifum_shoe.service

systemctl restart redis-server.service
