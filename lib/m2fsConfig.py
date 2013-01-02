import ConfigParser
import os

class m2fsConfig:
    """" 
    Class to handle reading and writing instrument configuration data 
    
    Class contains only static methods
    
    getPlateDirectory
    getRejectDirectory
    getMisplugAudioFilename
    getUploadDirectory
    getPort
    getAgentPorts
    getGalilDefaults
    setGalilDefaults
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
    def getPlateDirectory():
        """ Get the platefile directory from m2fs_paths.conf """
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_paths.conf','r'))
        return config.get('Directories','plateFileDir')
    
    @staticmethod
    def getRejectDirectory():
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
    def getUploadDirectory():
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
        
        Takes a dict settings. Any settings in the file, but not in the dict
        WILL be erased. 
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
    def getDataloggerLogfileNames():
        """
        Return tuple of temp logfile and acceleration logfile
        
        
        Logfiles returned should exist and have r/w permissions for the 
        process.
        """
        #return ('/var/log/tempLogfile.pickle','/var/log/accelLogfile.pickle')
        return ('/Users/one/Desktop/tempLogfile.pickle','/Users/one/Desktop/accelLogfile.pickle')
