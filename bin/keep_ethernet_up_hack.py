#!/usr/bin/env python2.7
import sys, dbus, time, logging
sys.path.append(sys.path[0]+'/../lib/')
from m2fsConfig import m2fsConfig

public_adapter = "/net/connman/service/ethernet_b88d1255cd7e_cable"

fls_adapter = "/net/connman/service/ethernet_b88d1255d1ee_cable"

fixed_mac_adapters = (public_adapter,)

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

def dbus_array(x):
    return dbus.Array(x, signature=dbus.Signature('s'))

FLS_ADAPTER_ADDRESS=dbus_string('192.168.0.1')
FLS_ADAPTER_NETMASK=dbus_string('255.255.255.0')
FLS_ADAPTER_GATEWAY=dbus_string('192.168.0.1')
FLS_IPV4_SETTINGS={"Method": dbus_string('manual'),
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
PUBLIC_DOMAINS=dbus_array(['lco.cl'])
PUBLIC_TIMESERVERS=dbus_array(['200.28.147.16','200.28.147.17',
                               '200.28.147.1'])
PUBLIC_NAMESERVERS=dbus_array(['200.28.147.2', '200.28.147.4',
                               '139.229.97.50','139.229.97.26'])
 
CONNECT_TIMEOUT=10000

########################### Script Starts #############################

bus = dbus.SystemBus()
manager = dbus.Interface(bus.get_object('net.connman', '/'), 'net.connman.Manager')


def bbxm_adapter():
    adapters = [str(e[0]) for e in manager.GetServices()]
    bb = [a for a in adapters if a not in fixed_mac_adapters]
    if len(bb)==0:
        return ''
    elif len(bb)>1:
        logger.warning('More that one adapter found when looking for the BB eth '
                       'Did you forget to add all the USB eth to the list in '
                       'keep_ethernet_up_hack.py?')
    else:
        return bb[0]

def disconnect(service):
    try:
        service.Disconnect()
    except Exception:
        pass

def bringPublicUpDHCP():
    adapter = bus.get_object('net.connman', public_adapter)
    service = dbus.Interface(adapter, 'net.connman.Service')
    
    logger.info('Connecting public adapter via DHCP')
    
    disconnect(service)
    service.SetProperty("IPv4.Configuration", {"Method": dbus_string('dhcp') })
    service.Connect(timeout=CONNECT_TIMEOUT)

def bringPublicUpFIXED():
    adapter = bus.get_object('net.connman', public_adapter)
    service = dbus.Interface(adapter, 'net.connman.Service')
    
    logger.info('Connecting public adapter via static config')
    
    disconnect(service)
    logger.info('IPV4')
    service.SetProperty("IPv4.Configuration", PUBLIC_IPV4_SETTINGS)
    logger.info('domain')
    service.SetProperty("Domains.Configuration", PUBLIC_DOMAINS)
    logger.info('time')
    service.SetProperty("Timeservers.Configuration", PUBLIC_TIMESERVERS)
    logger.info('name')
    service.SetProperty("Nameservers.Configuration", PUBLIC_NAMESERVERS)
    service.Connect(timeout=CONNECT_TIMEOUT)

def bringFLSUp():
    adapter=bus.get_object('net.connman', bbxm_adapter())
    service = dbus.Interface(adapter, 'net.connman.Service')
    
    logger.info('Connecting FLS adapter via static config')
                      
    disconnect(service)
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
    try:
        bringFLSUp()
    except Exception as e:
        logger.error(str(e))
    while True:
        try:
            desiredMethod=m2fsConfig.getIPmethod()
            if desiredMethod!=method or adapterOffline(public_adapter):
                if desiredMethod!=method:
                    logger.info('Switching to {} IP'.format(desiredMethod))
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

