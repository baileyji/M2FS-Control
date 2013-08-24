#!/usr/bin/env python2.7
import sys, dbus, time, logging
sys.path.append(sys.path[0]+'/../lib/')
from m2fsConfig import m2fsConfig

public_adapter = "/net/connman/service/ethernet_b88d1255cd7e_cable"

fls_adapter = "/net/connman/service/ethernet_b88d1255d1ee_cable"

#Set up logging
logger=logging.getLogger()
# create console handler
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
ch.setLevel(logging.INFO)
# add handlers to logger
logger.addHandler(ch)
#Set the default logging level
logger.setLevel(logging.INFO)


def dbus_string(string):
	return dbus.String(string, variant_level=1)

def dbus_Array(list):
    return dbus.Array(x, signature=dbus.Signature('s')

FLS_ADAPTER_ADDRESS=dbus_string('192.168.0.1')
FLS_ADAPTER_NETMASK=dbus_string('255.255.255.0')
FLS_ADAPTER_GATEWAY=dbus_string('192.168.0.1')
IPV4_SETTINGS={"Method": dbus_string('manual'),
               "Address":FLS_ADAPTER_ADDRESS,
               "Netmask":FLS_ADAPTER_NETMASK,
               "Gateway":FLS_ADAPTER_GATEWAY}


PUBLIC_ADAPTER_ADDRESS=dbus_string('200.28.147.41')
PUBLIC_ADAPTER_NETMASK=dbus_string('255.255.255.0')
PUBLIC_ADAPTER_GATEWAY=dbus_string('200.28.147.1')
PUBLIC_IPV4_SETTINGS={"Method": dbus_string('manual'),
                      "Address":PUBLIC_ADAPTER_ADDRESS,
                      "Netmask":PUBLIC_ADAPTER_NETMASK,
                      "Gateway":PUBLIC_ADAPTER_GATEWAY}
PUBLIC_DOMAIN=dbus_string('lco.cl')
PUBLIC_TIMESERVERS=dbus_array(['200.28.147.16','200.28.147.17',
                               '200.28.147.1'])
PUBLIC_NAMESERVERS=dbus.Array(['200.28.147.2', '200.28.147.4',
                               '139.229.97.50','139.229.97.26'])
 
CONNECT_TIMEOUT=10000

########################### Script Starts #############################

bus = dbus.SystemBus()
manager = dbus.Interface(bus.get_object('net.connman', '/'), 'net.connman.Manager')

def bringPublicUpDHCP():
    adapter = bus.get_object('net.connman', public_adapter)
    service = dbus.Interface(adapter, 'net.connman.Service')
    
    logger.info('Connecting public adapter via DHCP')
    
    service.Disconnect()
    service.SetProperty("IPv4.Configuration", {"Method": dbus_string('dhcp') })
    service.Connect(timeout=CONNECT_TIMEOUT)

def bringPublicUpFIXED():
    adapter = bus.get_object('net.connman', public_adapter)
    service = dbus.Interface(adapter, 'net.connman.Service')
    
    logger.info('Connecting public adapter via static config')
    
    service.Disconnect()
    service.SetProperty("IPv4.Configuration", PUBLIC_IPV4_SETTINGS)
    service.SetProperty("Domains.Configuration", PUBLIC_DOMAIN)
    service.SetProperty("Timeservers.Configuration", PUBLIC_TIMESERVERS)
    service.SetProperty("Nameservers.Configuration", PUBLIC_NAMESERVERS)
    service.Connect(timeout=CONNECT_TIMEOUT)

def bringFLSUp():
    adapter=bus.get_object('net.connman', fls_adapter)
    service = dbus.Interface(adapter, 'net.connman.Service')
    
    logger.info('Connecting FLS adapter via static config')
                      
    service.Disconnect()
    service.SetProperty("IPv4.Configuration", FLS_IPV4_SETTINGS)
    service.Connect(timeout=CONNECT_TIMEOUT)

def adapterOffline(adapter_path):
    services = manager.GetServices()
    for entry in services:
        path = entry[0]
        if path == adapter_path:
            properties = entry[1]
            #Check to see if state is listed as ready,
            # if so the we are not online and getOnline() should work
            if properties['State'].lower().strip()=='idle':
                return True
    return False

if __name__=='__main__':
    method=''
    while True:
        try:
            desiredMethod=m2fsConfig.getIPmethod()
            if desiredMethod!=method or adapterOffline(public_adapter):
                if desiredMethod!=method:
                    logger.info('Switching to {} IP'.format(method))
                if desiredMethod == 'dhcp':
                    bringPublicUpDHCP()
                else:
                    bringPublicUpFIXED()
                method=desiredMethod
        except Exception as e:
            logger.error(str(e))
        try:
            if adapterOffline(fls_adapter):
                bringFLSUp()
        except Exception as e:
            logger.error(str(e))
        time.sleep(30)

