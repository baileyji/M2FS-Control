#!/bin/sh

#  program_galils.sh
#  m2fs
#
#  Created by Jeb Bailey on 12/7/12.
#  Copyright (c) 2012 SpaceColonyOne, Inc. All rights reserved.
systemctl stop m2fs_galilR.service
systemctl stop m2fs_galilB.service
./galilProgrammer.py -f ../galil/m2fs.dmc -d /dev/galilR --auto
./galilProgrammer.py -f ../galil/m2fs.dmc -d /dev/galilB --auto
systemctl start m2fs_galilR.service
systemctl start m2fs_galilB.service
