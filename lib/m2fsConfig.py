import ConfigParser

class m2fsConfig:
    fileName='./m2fs/conf/m2fs.conf'    
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
        config.readfp(open(m2fsConfig.fileName,'r'))
        agentports=config.items('AgentPorts')
        return dict(agentports)
