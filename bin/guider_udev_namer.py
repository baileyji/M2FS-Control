#!/usr/bin/env python2.7
import os, sys
isGuider=os.environ.get('ID_USB_INTERFACE_NUM',None)=='00'
if isGuider:
        sys.exit(0)
else:
        sys.exit(1)


