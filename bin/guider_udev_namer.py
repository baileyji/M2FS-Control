#!/usr/bin/env python2.7
import os
f=open('/udevtest.log','a')
#f.write(str(os.environ))
isGuider=os.environ.get('ID_USB_INTERFACE_NUM',None)=='00'
#f.close()
if isGuider:
        exit(0)
else:
        exit(1)


