#!/bin/sh

#  download_galil_code.sh
#  Run to obtain a listing of the code running on the Galils. When debugging one
#  can not refrence the line numbers in m2fs.dmc as some lines are stripped 
#  during programming.
#
#  Created by Jeb Bailey on 1/22/13.
#  Copyright
systemctl stop galilR.service
systemctl stop galilB.service
./galilDownloader.py -f ./galilRdownload.dmc -d /dev/galilR
./galilDownloader.py -f ./galilBdownload.dmc -d /dev/galilB
systemctl start galilR.service
systemctl start galilB.service
