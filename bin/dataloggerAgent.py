#!/usr/bin/env python2.7
import sys, time, threading
sys.path.append(sys.path[0]+'/../lib/')
import logging
import logging.handlers
import atexit
from agent import Agent
from command import Command
import cPickle
import datalogger
from m2fsConfig import m2fsConfig
import SelectedConnection

class DataloggerAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'DataloggerAgent')
        #Initialize the dataloggers
        self.dataloggerR=datalogger.Datalogger('/dev/dataloggerR', 115200)
        self.dataloggerB=datalogger.Datalogger('/dev/dataloggerB', 115200)
        self.dataloggerC=datalogger.Datalogger('/dev/dataloggerC', 115200)
        self.devices.append(self.dataloggerR)
        self.devices.append(self.dataloggerB)
        self.devices.append(self.dataloggerC)
        agent_ports=m2fsConfig.getAgentPorts()
        self.shoeR=SelectedConnection.SelectedSocket('localhost', 
            agent_ports['ShoeAgentR'])
        self.shoeB=SelectedConnection.SelectedSocket('localhost', 
            agent_ports['ShoeAgentB'])
        #self.devices.append(self.shoeR)
        #self.devices.append(self.shoeB)
        self.setupLoggerFiles()
        self.currentTemps={}
        self.command_handlers.update({
            """ Return a list of the temperature values """
            'TEMPS':self.TEMPS_command_handler})
    
    def setupLoggerFiles(self):
        tempLog,accelLog=m2fsConfig.getDataloggerLogfileNames()
        self.tempsFile=open(tempLog,'a')
        self.accelsFile=open(accelLog,'a')

    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def on_exit(self, arg):
        """Prepare to exit"""
        #TODO close and save data file
        self.tempsFile.close()
        self.accelsFile.close()
        Agent.on_exit(self, arg)

    
    def get_version_string(self):
        return 'Datalogger Agent Version 0.1'
    
    def TEMPS_command_handler(self, command):
        """ report the current temperatures """
        #gather current temps
        temps=self.currentTemps.values()
        command.setReply(''.join((len(temps)*"%f ")%temps))
    
    def status_command_handler(self, command):
        """ report status info """
        #TODO: compile status info
        command.setReply('TODO: current state of the dataloggers.')
    
    def run(self):
        """ execute once per loop, after select has run & before command closeout """
        #Temp handling
        if self.dataloggerR.have_unfetched_temps():
            data=self.dataloggerR.fetch_temps()
            self.currentTemps['dataloggerR']=data
            timestamps,temps=data
            if timestamps[0]>self.most_current_dataloggerR_timestamp:
                self.most_current_dataloggerR_timestamp=timestamps[0]
                self.currentTemps['R']=temps
            self.logger.debug("TempsR: %s:%s" % 
                (time.asctime(time.localtime(long(timestamps[0]))), temps))
            cPickle.dump(('R',data), self.tempsFile, -1)
        
        if self.dataloggerC.have_unfetched_temps():
            data=self.dataloggerC.fetch_temps()
            self.currentTemps['dataloggerC']=data
            timestamps,temps=data
            if timestamps[0]>self.most_current_dataloggerC_timestamp:
                self.most_current_dataloggerC_timestamp=timestamps[0]
                self.currentTemps['C']=temps
            self.logger.debug("TempsC: %s:%s" % 
                (time.asctime(time.localtime(long(timestamps[0]))), temps))
            cPickle.dump(('C',data), self.tempsFile, -1)
        
        if self.dataloggerB.have_unfetched_temps():
            data=self.dataloggerB.fetch_temps()
            self.currentTemps['dataloggerB']=data
            timestamps,temps=data
            if timestamps[0]>self.most_current_dataloggerB_timestamp:
                self.most_current_dataloggerB_timestamp=timestamps[0]
                self.currentTemps['B']=temps
            self.logger.debug("TempsB: %s:%s" % 
                (time.asctime(time.localtime(long(timestamps[0]))), temps))
            cPickle.dump(('B',data), self.tempsFile, -1)
        
        #Accelerometer handling
        if self.dataloggerC.have_unfetched_accels():
            data=self.dataloggerC.fetch_accels()
            timestamps,accels=data
            self.logger.debug("AccelsC: %s:%s" % 
                (time.asctime(time.localtime(long(timestamps[0]))), len(accels)))
            cPickle.dump(('C',data), self.accelsFile,-1)
            
        if self.dataloggerR.have_unfetched_accels():
            data=self.dataloggerR.fetch_accels()
            timestamps,accels=data
            self.logger.debug("AccelsR: %s:%s" %
                              (time.asctime(time.localtime(long(timestamps[0]))), len(accels)))
            cPickle.dump(('R',data), self.accelsFile,-1)
        if self.dataloggerB.have_unfetched_accels():
            data=self.dataloggerB.fetch_accels()
            timestamps,accels=data
            self.logger.debug("AccelsB: %s:%s" %
                              (time.asctime(time.localtime(long(timestamps[0]))), len(accels)))
            cPickle.dump(('B',data), self.accelsFile,-1)
        
        #check that the dataloggers are online
        try:
            self.dataloggerR.connect()
            self.dataloggerB.connect()
            self.dataloggerC.connect()
        except IOError:
            pass
    
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

