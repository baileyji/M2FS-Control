import ConfigParser

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
        config.readfp(open('../conf/m2fs_paths.conf','r'))
        return config.item('Director','plateFileDir')
    
    @staticmethod
    def getPort(string):
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open('../conf/m2fs_socket.conf','r'))
        port=config.getint('Ports',string)
        return port
    
    @staticmethod
    def getGalilDefaults(side):
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        file='../conf/m2fs_galilB.conf' if side=='B' else '../conf/m2fs_galilR.conf'
        try:
            config.readfp(open(file,'r'))
        except Exception:
            return {}
        return dict(config.items('Defaults'))
    
    @staticmethod
    def setGalilDefaults(side, defaults):
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        file='../conf/m2fs_galilB.conf' if side=='B' else '../conf/m2fs_galilR.conf'
        with open(file,'w') as configfile:
            for setting, value in defaults:
                config.set('Defaults', setting, value)
                config.write(configfile)
                configfile.close()
    
