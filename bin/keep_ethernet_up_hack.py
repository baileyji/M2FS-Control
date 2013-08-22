#!/usr/bin/env python2.7
import sys, dbus, time, logging

public_adapter = "/net/connman/service/ethernet_b88d1255cd7e_cable"

fls_adapter = "/net/connman/service/ethernet_b88d1255d1ee_cable"

logger=logging.getLogger()
if logger.handlers==[]:
    # create console handler
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    ch.setLevel(logging.INFO)
    # add handlers to logger
    logger.addHandler(ch)
    #Set the default logging level
    logger.setLevel(logging.INFO)

bus = dbus.SystemBus()

def make_variant(string):
	return dbus.String(string, variant_level=1)

FLS_ADAPTER_ADDRESS=make_variant('192.168.0.1')
FLS_ADAPTER_NETMASK=make_variant('255.255.255.0')

PUBLIC_ADAPTER_ADDRESS=make_variant('200.28.147.41')
PUBLIC_ADAPTER_NETMASK=make_variant('255.255.255.0')

CONNECT_TIMOUT=10000


def bringPublicUpDHCP():
    adapter = bus.get_object('net.connman', public_adapter)
    service = dbus.Interface(adapter, 'net.connman.Service')
    service.SetProperty("IPv4.Configuration", {"Method": make_variant('dhcp') })
    service.Connect(timeout=CONNECT_TIMOUT)

def bringPublicUpFIXED():
    adapter = bus.get_object('net.connman', public_adapter)
    service = dbus.Interface(adapter, 'net.connman.Service')
    setting_dict={"Method": make_variant('manual'),
                  "Address":PUBLIC_ADAPTER_ADDRESS,
                  "Netmask":PUBLIC_ADAPTER_NETMASK,
                  "Gateway":PUBLIC_ADAPTER_ADDRESS}
    service.SetProperty("IPv4.Configuration", setting_dict)
    service.Connect(timeout=CONNECT_TIMOUT)

def bringFLSUp():
    adapter=bus.get_object('net.connman', fls_adapter)
    service = dbus.Interface(adapter, 'net.connman.Service')
    setting_dict={"Method": make_variant('manual'),
                  "Address":FLS_ADAPTER_ADDRESS,
                  "Netmask":FLS_ADAPTER_NETMASK,
                  "Gateway":FLS_ADAPTER_ADDRESS}
    service.SetProperty("IPv4.Configuration", setting_dict)
    service.Connect(timeout=CONNECT_TIMOUT)

def adapterOffline(adapter_path):
    manager = dbus.Interface(bus.get_object('net.connman', '/'),
                             'net.connman.Manager')
    services = manager.GetServices()
    for entry in services:
        path = entry[0]
        if path == adapter_path:
            properties = entry[1]
            #Check to see if state is listed as ready,
            # if so the we are not online and getOnline() should work
            if properties['State'].lower().strip()==['ready', 'idle']:
                return True
    return False

if __name__=='__main__':
    while True:
        try:
            if adapterOffline(public_adapter):
                bringPublicUpFIXED()
        except Exception as e:
            logger.error(str(e))
        try:
            if adapterOffline(fls_adapter):
                bringFLSUp()
        except Exception as e:
            logger.error(str(e))
        time.sleep(30)

