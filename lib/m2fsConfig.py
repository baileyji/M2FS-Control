import ConfigParser
_CONFIG_DIRECTORY='./conf/'
class m2fsConfig:
    
    def __init__(self):
        pass
    
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
    def getPlateFileDirectory():
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(_CONFIG_DIRECTORY+'m2fs_paths.conf','r'))
        return config.item('Director','plateFileDir')
    
    @staticmethod
    def getPort(string):
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(_CONFIG_DIRECTORY+'m2fs_socket.conf','r'))
        port=config.getint('Ports',string)
        return port
        
    @staticmethod
    def getAgentPorts():
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open(_CONFIG_DIRECTORY+'m2fs_socket.conf','r'))
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
            config.readfp(open(_CONFIG_DIRECTORY+file,'r'))
        except Exception:
            return {}
        return dict(config.items('Defaults'))
    
    @staticmethod
    def setGalilDefaults(side, defaults):
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        if side=='B':
            file='m2fs_galilB.conf'
        else:
            file='m2fs_galilR.conf'
        with open(_CONFIG_DIRECTORY+file,'w') as configfile:
            for setting, value in defaults:
                config.set('Defaults', setting, value)
                config.write(configfile)
                configfile.close()
    
