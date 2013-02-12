import ConfigParser
import os

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
    def getShoeColorInCradle(color):
        """
        Return 'R', 'B', or '' debending on the she in the specified cradle
        """
        if color=='R':
            if os.path.exists('/dev/shoeR'):
                if not os.path.exists('/dev/shoeBincradleR'):
                    return 'R'
                else:
                    return 'B'
            else:
                return ''
        elif color=='B':
            if os.path.exists('/dev/shoeB'):
                if not os.path.exists('/dev/shoeRincradleB'):
                    return 'B'
                else:
                    return 'R'
            else:
                return ''

