#!/bin/sh

#  restart_services.sh
#  m2fs
#
#  Created by Jeb Bailey on 7/25/12.
#  Copyright (c) 2012 SpaceColonyOne, Inc. All rights reserved.
systemctl --system daemon-reload
systemctl restart shoeR.service
systemctl restart shoeB.service
systemctl restart galilR.service
systemctl restart galilB.service
systemctl restart slitController.service
systemctl restart shackhartman.service
systemctl restart plugController.service
systemctl restart guider.service
systemctl restart director.service
