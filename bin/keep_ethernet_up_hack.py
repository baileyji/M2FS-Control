#!/usr/bin/env python2.7
import sys, dbus, time

service_path = "/net/connman/service/ethernet_b88d1255cd7e_cable"

bus = dbus.SystemBus()

def make_variant(string):
	return dbus.String(string, variant_level=1)

def getOnline():
    service = dbus.Interface(bus.get_object('net.connman', service_path),
                             'net.connman.Service')
    service.SetProperty("IPv4.Configuration", {"Method": make_variant('dhcp') })

def needToGetOnline():
    manager = dbus.Interface(bus.get_object('net.connman', '/'),
                             'net.connman.Manager')
    services = manager.GetServices()
    for entry in services:
        path = entry[0]
        if path == service_path:
            properties = entry[1]
            #Check to see if state is listed as ready,
            # if so the we are not online and getOnline() should work
            if properties['State'].lower().strip()=='ready':
                return True
    return False

if __name__=='__main__':
    while True:
        try:
            if needToGetOnline():
                getOnline()
        except Exception as e:
            print str(e)
        time.sleep(30)

