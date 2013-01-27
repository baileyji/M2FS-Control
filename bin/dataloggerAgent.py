#!/usr/bin/env python2.7
import sys, time, threading
sys.path.append(sys.path[0]+'/../lib/')
from agent import Agent
import cPickle
from datalogger import Datalogger
from m2fsConfig import m2fsConfig
import SelectedConnection

DATALOGGER_VERSION_STRING='Datalogger Agent v0.1'

class DataloggerAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'DataloggerAgent')
        self.setupLoggerFiles()
        #Initialize the dataloggers
        #self.dataloggerR=Datalogger('/dev/dataloggerR')
        #self.dataloggerB=Datalogger('/dev/dataloggerB')
        self.dataloggerC=Datalogger('/dev/dataloggerC')
        agent_ports=m2fsConfig.getAgentPorts()
        self.shoeR=SelectedConnection.SelectedSocket('localhost', 
            agent_ports['ShoeAgentR'])
        self.shoeB=SelectedConnection.SelectedSocket('localhost', 
            agent_ports['ShoeAgentB'])
        #self.devices.append(self.shoeR)
        #self.devices.append(self.shoeB)

        self.currentTemps={}
        self.command_handlers.update({
            """ Return a list of the temperature values """
            'TEMPS':self.TEMPS_command_handler})
    
    def setupLoggerFiles(self):
        tempLog,accelLog=m2fsConfig.getDataloggerLogfileNames()
        self.tempsFile=open(tempLog,'a')
        self.accelsFile=open(accelLog,'a')
    
    def on_exit(self, arg):
        """Prepare to exit"""
        self.tempsFile.close()
        self.accelsFile.close()
        Agent.on_exit(self, arg)
    
    def get_version_string(self):
        return DATALOGGER_VERSION_STRING
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the M2FS datalogger"
    
    def TEMPS_command_handler(self, command):
        """ report the current temperatures """
        command.setReply(self.getStringOfCurrentTemps())
    
    def getStringOfCurrentTemps(self):
        """ Return a space delimited list of the current temperatures """
        temps=self.currentTemps.values()
        return ''.join((len(temps)*"%f ")%temps)
    
    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pair name:cookie
        """
        return [(self.get_version_string(),self.cookie)]
    
    def run(self):
        """ execute once per loop, after select has run & before command closeout """
        record=self.dataloggerC.fetch()
    
    def queryShoeTemps(self):
        try:
            self.shoeR.sendMessageBlocking('SLITS_TEMP')
            messageR=self.shoeR.receiveMessageBlocking()
            self.currentTemps['shoeR']=float(messageR)
            self.most_current_shoeR_timestamp=time.time()
        except IOError:
            self.logger.info("Failed to poll shoeR for temp")
        except ValueError:
            pass
        try:
            self.shoeB.sendMessageBlocking('SLITS_TEMP')
            messageB=self.shoeB.receiveMessageBlocking()
            self.currentTemps['shoeB']=float(messageB)
            self.most_current_shoeB_timestamp=time.time()
        except IOError:
            self.logger.info("Failed to poll shoeR for temp")
        except ValueError:
            pass
        self.queryShoesTimer=threading.Timer(60.0, self.queryShoeTemps)
        self.queryShoesTimer.daemon=True
        self.queryShoesTimer.start()
    
    def runSetup(self):
        """ execute before main loop """
        self.most_current_dataloggerR_timestamp=0
        self.most_current_dataloggerC_timestamp=0
        self.most_current_dataloggerB_timestamp=0
        self.most_current_shoeR_timestamp=0
        self.most_current_shoeB_timestamp=0
        self.queryShoesTimer=threading.Timer(60.0, self.queryShoeTemps)
        self.queryShoesTimer.daemon=True
        #self.queryShoesTimer.start()

if __name__=='__main__':
    agent=DataloggerAgent()
    agent.main()

