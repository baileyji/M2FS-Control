#!/bin/sh

#  restart_services.sh
#  m2fs
#
#  Created by Jeb Bailey on 7/25/12.
#  Copyright (c) 2012 SpaceColonyOne, Inc. All rights reserved.
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
