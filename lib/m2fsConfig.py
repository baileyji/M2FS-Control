import ConfigParser
import os
_CONFIG_DIRECTORY='./conf/'
class m2fsConfig:
    
    def __init__(self):
        pass
    
    @staticmethod
    def getConfDir():
        if os.path.isdir('./conf'):
            return './conf/'
        else:
            return '../conf/'
    
    @staticmethod
    def writePositionDefault(positionName, value):
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        with open(m2fsConfig.fileName,'r') as configfile:
            config.readfp(configfile)
            configfile.close()
        with open(m2fsConfig.fileName,'w') as configfile:
            config.set('PositionDefaults', setting, value)
            config.write(configfile)
            configfile.close()
    
    @staticmethod    
    def getPlateDirectory():
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_paths.conf','r'))
        return config.get('Director','plateFileDir')
    
    @staticmethod
    def getPort(string):
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_socket.conf','r'))
        port=config.getint('Ports',string)
        return port
        
    @staticmethod
    def getAgentPorts():
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(m2fsConfig.getConfDir()+'m2fs_socket.conf','r'))
        return {x[0]:int(x[1]) for x in config.items('Ports')}
    
    @staticmethod
    def getGalilDefaults(side):
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
