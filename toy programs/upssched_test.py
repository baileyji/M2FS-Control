#!/usr/bin/env python2.7
import sys
sys.path.append(sys.path[0]+'/M2FS-Control/lib/')
import PyNUT

NUT_LOGIN="monitor"
NUT_PASSWORD="1"
#Get the battery backup state
try:
    nut=PyNUT.PyNUTClient(login=NUT_LOGIN, password=NUT_PASSWORD)
    upsstate=nut.GetUPSVars('myups')
    status='Battery:'+upsstate['ups.status']+' Runtime(s):'+upsstate['battery.runtime']
except Exception:
    status='Faild to query NUT for status'
f=open('/upssched_test.log','a')
f.write(status)
f.close()