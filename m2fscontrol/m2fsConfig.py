import ConfigParser
import os

N_IFU_TEMPS = 5

def ifuProbeTempsToDict(ifuProbeTempsList):
    ret={'ifuHTemp':None,'ifuSTemp':None,'ifuLTemp':None}  #TODO finish once all are known
    if ifuProbeTempsList is not None:
        if len(ifuProbeTempsList) != N_IFU_TEMPS:
            raise ValueError('Incorrect number of probe temperatures')
        ret['ifuHTemp']=ifuProbeTempsList[0]
        ret['ifuSTemp']=ifuProbeTempsList[1]
        ret['ifuLTemp']=ifuProbeTempsList[2]
    return ret

def getOcculterConfFile(ifu):
    ifu = ifu.upper()[0]
    if ifu == 'H':
        return 'ifum_occulterH.conf'
    elif ifu == 'S':
        return 'ifum_occulterS.conf'
    elif ifu == 'L':
        return 'ifum_occulterL.conf'
    else:
        raise ValueError('"{}" is not an occulter specifier (H, S, L)'.format(ifu))

class m2fsConfig:
    """" 
    Class to handle reading and writing instrument configuration data 
    
    Class contains only static methods
    
    disableStowedShutdown
    enableStowedShutdown
    doStowedShutdown
    getPlateDir
    getPlateRejectDir
    getMisplugAudioFilename
    getPlateUploadDir
    getPort
    getAgentPorts
    getGalilDefaults
    setGalilDefaults
    setGalilLastPosition
    clearGalilLastPositions
    getGalilLastPositions
    getGalilLastPosition
    getDataloggerLogfileNames
    """
    def __init__(self):
        pass
    
    @staticmethod
    def getConfDir():
        """
        Get the config directory.
        
        Works if working directory is ./M2FS-Control or ./M2FS-Control/bin 
        """
        if os.path.isdir('./conf'):
            return './conf/'
        else:
            return '../conf/'

    @staticmethod
    def m2fs_devices_present():
        return (os.path.exists("/dev/shoeA172") or
                os.path.exists("/dev/shoeF0A2") or
                os.path.exists("/dev/shoeF171") or
                os.path.exists("/dev/shoe3280") or
                os.path.exists("/dev/shLED") or
                os.path.exists("/dev/shLenslet") or
                os.path.exists("/dev/guider"))

    @staticmethod
    def ifum_devices_present():
        return (os.path.exists("/dev/ifum_occulterS") or
                os.path.exists("/dev/ifum_occulterL") or
                os.path.exists("/dev/ifum_occulterH") or
                os.path.exists("/dev/ifum_shield") or
                os.path.exists("/dev/ifum_shoe") or
                os.path.exists("/dev/ifum_selector"))

    @staticmethod
    def disableStowedShutdown():
        """ Disable Stowed Shutdown """
        if os.path.exists('/var/run/M2FS_do_stowed_shutdown'):
            os.system('rm /var/run/M2FS_do_stowed_shutdown')
    
    @staticmethod
    def enableStowedShutdown():
        """ Enable Stowed Shutdown """
        os.system('touch /var/run/M2FS_do_stowed_shutdown')
    
    @staticmethod
    def doStowedShutdown():
        """
        Return true if agents should perform a stowed shutdown
        """
        return os.path.exists('/var/run/M2FS_do_stowed_shutdown')
    
    @staticmethod    
    def getPlateDir():
        """ Get the platefile directory from m2fs_paths.conf """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_paths.conf','r'))
        return config.get('Directories','plateFileDir')
    
    @staticmethod
    def getPlateRejectDir():
        """ Get the directory for bad platefiles from m2fs_paths.conf """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_paths.conf','r'))
        return config.get('Directories','plateRejectDir')
    
    @staticmethod
    def getMisplugAudioFilename():
        """ Get the misplug sound effect file """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_paths.conf','r'))
        return config.get('Directories','misplugSound')
    
    @staticmethod    
    def getPlateUploadDir():
        """ Get the directory where users upload new plates """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_paths.conf','r'))
        return config.get('Directories','uploadDir')
    
    @staticmethod
    def getPort(string):
        """ Retrieve the port for Agent named string from m2fs_socket.conf """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_socket.conf','r'))
        port=config.getint('Ports',string)
        return port
        
    @staticmethod
    def getAgentPorts():
        """ Retrieve a dict of all agent ports as name:port pairs """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_socket.conf','r'))
        return {x[0]:int(x[1]) for x in config.items('Ports')}
    
    @staticmethod
    def getGalilDefaults(side):
        """ Get dict of galil parameter defaults for galil R or B per side """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        if side=='B':
            file='m2fs_galilB.conf'
        else:
            file='m2fs_galilR.conf'
        try:
            config.readfp(open(m2fsConfig.getConfDir()+file,'r'))
            return dict(config.items('Defaults'))
        except Exception:
            return {}
    
    @staticmethod
    def getAgentForPort(port):
        """ Return the agent on port or an empty string """
        portAgentMapping={v:k for k, v in m2fsConfig.getAgentPorts().items()}
        return portAgentMapping.get(port, '')
    
    @staticmethod
    def nameFromAddrStr(addr_str):
        """
        Report the agent name for the address string if extant
        
        addr_str must be in the form of address:port for sucessful processing
        
        return addr_str if it doesn't correspond to an agent
        """
        try:
            addr,port=addr_str.partition(':')[::2]
            if addr=='localhost':
                agentName=m2fsConfig.getAgentForPort(int(port))
                if agentName:
                    return agentName
        except Exception:
           pass
        return addr_str
    
    @staticmethod
    def setGalilDefaults(side, defaults):
        """ 
        Write the Galil defaults for side to the config galil file
        
        Takes a dictionary of settings. Any settings in the file but not in the
        dict WILL be erased.
        """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.add_section('Defaults')
        if side=='B':
            file='m2fs_galilB.conf'
        else:
            file='m2fs_galilR.conf'
        with open(m2fsConfig.getConfDir()+file,'w') as configfile:
            for setting, value in defaults.items():
                config.set('Defaults', setting, value)
            config.write(configfile)
            configfile.close()
    
    @staticmethod
    def setGalilDefault(side, setting, value):
        """
        Write the Galil default setting for side to the galil config file
        
        Takes a setting name string and a string value.
        """
        #Get a dict with all the settings
        defaults=m2fsConfig.getGalilDefaults(side)
        #Update/Add the value of the setting
        defaults[setting]=value
        #Update the defaults file
        m2fsConfig.setGalilDefaults(side, defaults)

    @staticmethod
    def setGalilLastPosition(side, axis, value):
        """
        Write the position of the axis to a temp file
        
        Takes an axis name string and a string value. If value is None then 
        it is removed from the set of recorded positions.
        """
        #Get a dict with all the values
        positions=m2fsConfig.getGalilLastPositions(side)
        #Update/Add/remove the value of the setting
        if value:
            positions[axis]=value
        else:
            positions.pop(axis,None)
        #Update the defaults file
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.add_section('LastKnown')
        if side=='B':
            file='m2fs_galilBLastKnown.conf'
        else:
            file='m2fs_galilRLastKnown.conf'
        with open(m2fsConfig.getConfDir()+file,'w') as configfile:
            for setting, value in positions.items():
                config.set('LastKnown', setting, value)
            config.write(configfile)
            configfile.close()
    
    @staticmethod
    def clearGalilLastPositions(side):
        """ Clear the recorded axis positions from the temp file """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.add_section('LastKnown')
        with open(m2fsConfig.getConfDir()+file,'w') as configfile:
            config.write(configfile)
            configfile.close()
    
    @staticmethod
    def getGalilLastPositions(side):
        """ Get dict of last known galil positions for the R or B side """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        if side=='B':
            file='m2fs_galilBLastKnown.conf'
        else:
            file='m2fs_galilRLastKnown.conf'
        try:
            config.readfp(open(m2fsConfig.getConfDir()+file,'r'))
            return dict(config.items('LastKnown'))
        except Exception:
            return {}
    
    @staticmethod
    def getGalilLastPosition(side, axis):
        """
        Get the last known value of the axis per setGalilLastPosition 
        
        Raise ValueError if no recorded positon for axis
        """
        try:
            return m2fsConfig.getGalilLastPositions(side)[axis]
        except KeyError:
            raise ValueError

    @staticmethod
    def getSelectorDefaults():
        """ Get dict of selector parameter defaults for IFUM """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        try:
            with open(os.path.join(m2fsConfig.getConfDir(), 'ifum_selector.conf'), 'r') as f:
                config.readfp(f)
            return dict(config.items('Defaults'))
        except Exception:
            return {}

    @staticmethod
    def setSelectorDefaults(defaults):
        """
        Write the Selector defaults to the selector config file

        Takes a dictionary of settings. Any settings in the file but not in the
        dict WILL be erased.
        """
        config = ConfigParser.RawConfigParser()
        config.optionxform = str
        config.add_section('Defaults')
        with open(m2fsConfig.getConfDir() + 'ifum_selector.conf', 'w') as configfile:
            for setting, value in defaults.items():
                config.set('Defaults', setting, value)
            config.write(configfile)
            configfile.close()

    @staticmethod
    def setSelectorDefault(setting, value):
        """
        Write the selector default setting to the selector config file

        Takes a setting name string and a string value.
        """
        # Get a dict with all the settings
        defaults = m2fsConfig.getSelectorDefaults()
        # Update/Add the value of the setting
        defaults[setting] = value
        # Update the defaults file
        m2fsConfig.setSelectorDefaults(defaults)

    @staticmethod
    def getDataloggerLogfileName():
        """
        Return the fully qualified datalogger logfile path
        
        Files returned should have r/w permissions for the process.
        """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_paths.conf','r'))
        import time
        monthyear=time.strftime("%b%Y", time.localtime(time.time()))
        dir=config.get('Directories','dataloggerDir')
        return dir+'datalogger_'+monthyear+'.log'
    
    @staticmethod
    def getLogfileDir():
        """
        Return the fully qualified log file directory
            
        string ends in a path seperator.
        """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_paths.conf','r'))
        dir=config.get('Directories','dataloggerDir')
        return dir
    
    @staticmethod
    def getShoeColorInCradle(color):
        """
        Return 'R', 'B', or '' debending on the she in the specified cradle
        """
        if color not in ['R', 'B']:
            raise ValueError
        #Path only exists when something is in the cradle
        if not os.path.exists('/dev/shoe'+color):
            return ''
        #Determine if what is in the cradle is matching
        if color == 'R':
            if os.path.exists('/dev/shoeBincradleR'):
                return 'B'
            else:
                return 'R'
        if color == 'B':
            if os.path.exists('/dev/shoeRincradleB'):
                return 'R'
            else:
                return 'B'

    @staticmethod
    def getAgentLogLevel(name):
        """ Get the configured logging level for agent """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_logging.conf','r'))
        def str2loglevel(lls):
            import logging
            s=lls.lower()
            if s == 'info':
                return logging.INFO
            elif s== 'debug':
                return logging.DEBUG
            elif s=='error':
                return logging.ERROR
            elif s=='warning':
                return logging.WARNING
            else:
                return logging.INFO
        return str2loglevel(config.get('LogLevels',name))

    @staticmethod
    def getIPinfo():
        """ Get the configured logging level for agent """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_ip.conf','r'))
        ts=config.get('IP','timeserver').lower().split(',')
        ts=[ip.strip() for ip in config.get('IP','timeserver').lower().split(',')]
        ns=[ip.strip() for ip in config.get('IP','nameserver').lower().split(',')]
        ret = {'ip':config.get('IP','ip').lower(),
               'mask':config.get('IP','mask').lower(),
               'gateway':config.get('IP','gateway').lower(),
               'timeserver':ts,
               'nameserver':ns,
               'domain':config.get('IP','domain').lower()}
        return ret

    @staticmethod
    def getAXISip():
        """ Get the configured logging level for agent """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_ip.conf','r'))
        return config.get('AXISIP','ip').lower()

    @staticmethod
    def getMCalLEDAddress():
        """ Get the configured logging level for agent """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_ip.conf','r'))
        return (config.get('MCLED','ip').lower(),
                int(config.get('MCLED','port').lower()))

    @staticmethod
    def getIPmethod():
        """ Get the configured logging level for agent """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_ip.conf','r'))
        return config.get('IP','method').lower()

    @staticmethod
    def getOcculterDefaults(ifu):
        """ Get dict of ifu occulter parameter defaults for H, M, or L"""
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        try:
            config.readfp(open(m2fsConfig.getConfDir()+getOcculterConfFile(ifu), 'r'))
            return dict(config.items('Defaults'))
        except Exception:
            return {}

    @staticmethod
    def setOcculterDefaults(ifu, defaults):
        """
        Write the occulter defaults for the ifu to the config file

        Takes a dictionary of settings. Any settings in the file but not in the
        dict WILL be erased.
        """
        config = ConfigParser.RawConfigParser()
        config.optionxform = str
        config.add_section('Defaults')
        with open(m2fsConfig.getConfDir() + getOcculterConfFile(ifu), 'w') as configfile:
            for setting, value in defaults.items():
                config.set('Defaults', setting, value)
            config.write(configfile)
            configfile.close()

    @staticmethod
    def setOcculterDefault(ifu, setting, value):
        """
        Write the occulter default setting for the ifu to the config file

        Takes a setting name string and a string value.
        """
        # Get a dict with all the settings
        defaults = m2fsConfig.getOcculterDefaults(ifu)
        # Update/Add the value of the setting
        defaults[setting] = value
        # Update the defaults file
        m2fsConfig.setOcculterDefaults(ifu, defaults)

def getMCalLEDAddress():
    """Return the IP and port for the MCalLED unit"""
    # config = ConfigParser.RawConfigParser()
    # config.optionxform = str
    # config.readfp(open(m2fsConfig.getConfDir() + 'm2fs_mcalled.conf', 'r'))
    return ('192.168.0.177',8888)
