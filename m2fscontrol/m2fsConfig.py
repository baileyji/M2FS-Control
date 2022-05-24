import ConfigParser
import os
import time
import yaml
from pkg_resources import resource_filename

N_IFU_TEMPS = 4

def ifuProbeTempsToDict(ifuProbeTempsList):
    ret={'ifuentrance': None, 'ifufiberexit': None, 'ifutop': None, 'ifuhoffman':None }
    if ifuProbeTempsList is not None:
        if len(ifuProbeTempsList) != N_IFU_TEMPS:
            raise ValueError('Incorrect number of probe temperatures')
        ret['ifuentrance'] = ifuProbeTempsList[0]
        ret['ifutop'] = ifuProbeTempsList[1]
        ret['ifufiberexit'] = ifuProbeTempsList[2]
        ret['ifuhoffman'] = ifuProbeTempsList[3]
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

class M2FSConfig(object):
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

        Works if conf is in the same directory that contains the m2fscontrol package
        """
        return resource_filename('m2fscontrol', '../conf/')

    @staticmethod
    def m2fs_devices_present():
        return (os.path.exists("/dev/m2fs_shoeA172") or
                os.path.exists("/dev/m2fs_shoeF0A2") or
                os.path.exists("/dev/m2fs_shoeF171") or
                os.path.exists("/dev/m2fs_shoe3280") or
                os.path.exists("/dev/m2fs_shLED") or
                os.path.exists("/dev/m2fs_shLenslet") or
                os.path.exists("/dev/m2fs_guider"))

    @staticmethod
    def ifum_devices_present():
        """Excludes ifum_shoe as the control tower is always present"""
        return (os.path.exists("/dev/ifum_occulterS") or
                os.path.exists("/dev/ifum_occulterL") or
                os.path.exists("/dev/ifum_occulterH") or
                os.path.exists("/dev/ifum_shield") or
                # os.path.exists("/dev/ifum_shoe") or
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
    def load_conf(conf_name):
        config = ConfigParser.RawConfigParser()
        config.optionxform = str
        with open(M2FSConfig.getConfDir() + conf_name, 'r') as fb:
            config.readfp(fb)
        return config

    @staticmethod
    def getPlateDir():
        """ Get the platefile directory from m2fs_paths.conf """
        config = M2FSConfig.load_conf('m2fs_paths.conf')
        return config.get('Directories','plateFileDir')

    @staticmethod
    def getPlateRejectDir():
        """ Get the directory for bad platefiles from m2fs_paths.conf """
        config = M2FSConfig.load_conf('m2fs_paths.conf')
        return config.get('Directories', 'plateRejectDir')

    @staticmethod
    def getMisplugAudioFilename():
        """ Get the misplug sound effect file """
        config = M2FSConfig.load_conf('m2fs_paths.conf')
        return config.get('Directories','misplugSound')

    @staticmethod
    def getPlateUploadDir():
        """ Get the directory where users upload new plates """
        config = M2FSConfig.load_conf('m2fs_paths.conf')
        return config.get('Directories','uploadDir')

    @staticmethod
    def getPort(string):
        """ Retrieve the port for Agent named string from m2fs_socket.conf """
        config = M2FSConfig.load_conf('m2fs_socket.conf')
        return config.getint('Ports',string)

    @staticmethod
    def getAgentPorts():
        """ Retrieve a dict of all agent ports as name:port pairs """
        config = M2FSConfig.load_conf('m2fs_socket.conf')
        return {x[0]:int(x[1]) for x in config.items('Ports')}

    @staticmethod
    def getGalilDefaults(side):
        """ Get dict of galil parameter defaults for galil R or B per side """
        file = 'm2fs_galilB.conf' if side == 'B' else 'm2fs_galilR.conf'
        try:
            config = M2FSConfig.load_conf(file)
            return dict(config.items('Defaults'))
        except Exception:
            return {}

    @staticmethod
    def getAgentForPort(port):
        """ Return the agent on port or an empty string """
        portAgentMapping={v:k for k, v in M2FSConfig.getAgentPorts().items()}
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
                agentName=M2FSConfig.getAgentForPort(int(port))
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
        with open(M2FSConfig.getConfDir() + file, 'w') as configfile:
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
        defaults=M2FSConfig.getGalilDefaults(side)
        #Update/Add the value of the setting
        defaults[setting]=value
        #Update the defaults file
        M2FSConfig.setGalilDefaults(side, defaults)

    @staticmethod
    def setGalilLastPosition(side, axis, value):
        """
        Write the position of the axis to a temp file

        Takes an axis name string and a string value. If value is None then
        it is removed from the set of recorded positions.
        """
        #Get a dict with all the values
        positions=M2FSConfig.getGalilLastPositions(side)
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
        with open(M2FSConfig.getConfDir() + file, 'w') as configfile:
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
        with open(M2FSConfig.getConfDir() + file, 'w') as configfile:
            config.write(configfile)
            configfile.close()

    @staticmethod
    def getGalilLastPositions(side):
        """ Get dict of last known galil positions for the R or B side """
        file = 'm2fs_galilBLastKnown.conf' if side == 'B' else 'm2fs_galilRLastKnown.conf'
        try:
            config = M2FSConfig.load_conf(file)
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
            return M2FSConfig.getGalilLastPositions(side)[axis]
        except KeyError:
            raise ValueError

    @staticmethod
    def getSelectorDefaults():
        """ Get dict of selector parameter defaults for IFUM """
        try:
            config = M2FSConfig.load_conf('ifum_selector.conf')
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
        with open(M2FSConfig.getConfDir() + 'ifum_selector.conf', 'w') as configfile:
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
        defaults = M2FSConfig.getSelectorDefaults()
        # Update/Add the value of the setting
        defaults[setting] = value
        # Update the defaults file
        M2FSConfig.setSelectorDefaults(defaults)

    @staticmethod
    def getDataloggerLogfileName():
        """
        Return the fully qualified datalogger logfile path

        Files returned should have r/w permissions for the process.
        """
        config = M2FSConfig.load_conf('m2fs_paths.conf')
        monthyear=time.strftime("%b%Y", time.localtime(time.time()))
        dir=config.get('Directories','dataloggerDir')
        return dir+'datalogger_'+monthyear+'.log'

    @staticmethod
    def getLogfileDir():
        """
        Return the fully qualified log file directory

        string ends in a path seperator.
        """
        config = M2FSConfig.load_conf('m2fs_paths.conf')
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
        if not os.path.exists('/dev/m2fs_shoe'+color):
            return ''
        #Determine if what is in the cradle is matching
        if color == 'R':
            return 'B' if os.path.exists('/dev/m2fs_shoeBincradleR') else 'R'
        if color == 'B':
            return 'R' if os.path.exists('/dev/m2fs_shoeRincradleB') else 'B'

    @staticmethod
    def getAgentLogConfig(name):
        """ Get the configured logging level for agent """
        path = os.path.join(M2FSConfig.getConfDir(), 'm2fs_logging.yml')
        if os.path.exists(path):
            with open(path, 'rt') as f:
                config = yaml.safe_load(f.read())

        # postprocess loggers
        # loggers - the corresponding value will be a dict in which each key is a logger name
        # and each value is a dict describing how to configure the corresponding Logger instance.        #
        # The configuring dict is searched for the following keys:
        #     level (optional). The level of the logger.
        #     propagate (optional). The propagation setting of the logger.
        #     filters (optional). A list of ids of the filters for this logger.
        #     handlers (optional). A list of ids of the handlers for this logger.
        cfg = config['loggers'][name]  #extract one we care about
        if isinstance(cfg, str):
            config['loggers'] = {name: {'level': cfg.upper()}}
        else:
            loggers = {}
            for k, v in cfg.items():
                loggers[k] = {'level': v.upper()} if isinstance(v, str) else v
            config['loggers'] = loggers

        return config

    @staticmethod
    def getIPinfo():
        """ Get the configured logging level for agent """
        config = M2FSConfig.load_conf('m2fs_ip.conf')
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
        config = M2FSConfig.load_conf('m2fs_ip.conf')
        return config.get('AXISIP','ip').lower()

    @staticmethod
    def getMCalLEDAddress():
        """ Get the configured logging level for agent """
        config = M2FSConfig.load_conf('m2fs_ip.conf')
        return config.get('MCLED', 'ip').lower(), int(config.get('MCLED', 'port').lower())

    @staticmethod
    def getIPmethod():
        """ Get the configured logging level for agent """
        config = M2FSConfig.load_conf('m2fs_ip.conf')
        return config.get('IP', 'method').lower()

    @staticmethod
    def getOcculterDefaults(ifu):
        """ Get dict of ifu occulter parameter defaults for H, M, or L"""
        try:
            config = M2FSConfig.load_conf(getOcculterConfFile(ifu))
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
        with open(M2FSConfig.getConfDir() + getOcculterConfFile(ifu), 'w') as configfile:
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
        defaults = M2FSConfig.getOcculterDefaults(ifu)
        # Update/Add the value of the setting
        defaults[setting] = value
        # Update the defaults file
        M2FSConfig.setOcculterDefaults(ifu, defaults)
