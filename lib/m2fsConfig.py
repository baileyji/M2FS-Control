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
    def getAgentPorts():
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open('../conf/m2fs_socket.conf','r'))
        agentports=config.items('AgentPorts')
        return dict(agentports)

    @staticmethod
    def getDirectorPort():
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open('../conf/m2fs_socket.conf','r'))
        port=config.item('Director','instrumentPort')
        return int(port)
    
    @staticmethod    
    def getPlateFileDirectory():
        config=ConfigParser.RawConfigParser()
        config.optionxform=str
        config.readfp(open('../conf/m2fs_paths.conf','r'))
        return config.item('Director','plateFileDir')