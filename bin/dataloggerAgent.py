#!/opt/local/bin/python2.7
import time
import argparse
import socket
import signal
import logging
import logging.handlers
import atexit
import sys
import select
sys.path.append('../lib/')
from agent import Agent
from command import Command
import sqlite3
import datalogger
import m2fsConfig

class DataloggerAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'DataloggerAgent')
        
        #Initialize the dataloggers
        self.dataloggerR=datalogger.Datalogger('/dev/dataloggerR', 115200, self.logger)
        self.dataloggerB=datalogger.Datalogger('/dev/dataloggerB', 115200, self.logger)
        self.dataloggerC=datalogger.Datalogger('/dev/dataloggerC', 115200, self.logger)
        self.devices.append(self.dataloggerR)
        self.devices.append(self.dataloggerB)
        self.devices.append(self.dataloggerC)
        self.currentTemps={}
        self.command_handlers={
                    'TEMPS':self.TEMPS_command_handler,
                    'VERSION':self.version_request_command_handler,
                    'STATUS':self.status_command_handler}
        #self.temp_database_file=m2fsConfig.getTempDatafile()
        #open the logging database TODO
        #self.database=sqlite3.connect(self.database_file)
        #self.initialize_database()
    
    def initialize_database(self):
        dataloggerR_temp_column_names='HiRes R, LoRes R, Prism R'
        dataloggerC_temp_column_names='CaF R, Triplet R, Ambient R, Triplet B, CaF B, Ambient B'
        dataloggerB_temp_column_names='HiRes B, LoRes B, Prism B'
        shoeB_temp_column_name='Shoe B'
        shoeR_temp_column_name='Shoe R'
        temps_table_definition=(
            "Temps(Time timestamp primary key, " +
                (''.join(map(lambda x: "Temp %i real, " % x,
                range(self.num_temps))))[:-2])
        accel_table_definition=(
            "Accels(Time timestamp primary key, " +
            "Rx int, Ry int, Rz int, "+
            "Cx int, Cy int, Cz int, "+
            "Bx int, By int, Bz int")
        #self.database.execute("create table if not exists "+temps_table_definition)
        #self.database.execute("create table if not exists "+accel_table_definition)
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def on_exit(self, arg):
        """Prepare to exit"""
        #TODO close and save data file
        Agent.on_exit(self, arg)
    
    def get_version_string(self):
        return 'Datalogger Agent Version 0.1'
    
    def TEMPS_command_handler(self, command):
        """ report the current temperatures """
        #gather current temps, expiring any older than XXX
        command.setReply(''.join((len(temps)*"%f ")%temps))
    
    def status_command_handler(self, command):
        """ report status info """
        #TODO: compile status info
        command.setReply('TODO: current state of the dataloggers.')
    
    def insert_dataloggerR_temps_in_database(self, timestamp, temps):
        try:
            with self.database:
                self.database.execute("INSERT OR IGNORE INTO Temps(Time, "+dataloggerR_temp_column_names+" VALUES(?, ?, ?, ?)",
                    timestamp_IN_MINUTES.join(temps))
                self.database.execute("UPDATE Temps SET ?=?, ?=?, ?=? WHERE changes()=0 AND Time=?" ,
                    thread(dataloggerR_temp_column_names, temps).append(timestamp.IN_MINUTES))
        except sqlite3.IntegrityError:
            pass
    
    def run(self):
        """ execute once per loop, after select has run & before command closeout """
        
        #Temp handling
        if self.dataloggerR.have_unfetched_temps():
            timestamps,temps=self.dataloggerR.fetch_temps()
            if timestamps[0]>self.most_current_dataloggerR_timestamp:
                self.most_current_dataloggerR_timestamp=timestamps[0]
                self.currentTemps['R']=temps
            self.insert_dataloggerR_temps_in_database(timestamps[0],temps)
        if self.dataloggerC.have_unfetched_temps():
            timestamps,temps=self.dataloggerC.fetch_temps()
            if timestamps[0]>self.most_current_dataloggerC_timestamp:
                self.most_current_dataloggerC_timestamp=timestamps[0]
                self.currentTemps['C']=temps
            self.logger.debug("TempsC: %s:%s" % 
                (time.asctime(time.localtime(long(timestamps[0]))), temps))
            #self.insert_dataloggerC_temps_in_database(timestamps[0],temps)
        if self.dataloggerB.have_unfetched_temps():
            timestamps,temps=self.dataloggerB.fetch_temps()
            if timestamps[0]>self.most_current_dataloggerB_timestamp:
                self.most_current_dataloggerB_timestamp=timestamps[0]
                self.currentTemps['B']=temps
            self.insert_dataloggerB_temps_in_database(timestamps[0],temps)
        #once per minute start a query to the shoes for temps
        if False:
            self.shoeR.sendMessage('TEMP', 
                responseCallback=self.recieveFromRShoe,
                errorCallback=self.recieveFromRShoe)
            self.shoeB.sendMessage('TEMP',
                responseCallback=self.recieveFromBShoe,
                errorCallback=self.recieveFromBShoe)
            #reset time to query shoe
        
        #Accelerometer handling
        if self.dataloggerC.have_unfetched_accels():
            timestamps,accels=self.dataloggerC.fetch_accels()
            self.logger.debug("AccelsC: %s:%s" % 
                (time.asctime(time.localtime(long(timestamps[0]))), len(accels)))
        
        #check that the dataloggers are online
        #TODO
        
        
        

    def recieveFromBShoe(self, message):
        try:
            self.currentTemps['shoeB']=float(message)
            self.most_current_shoeB_timestamp=time.time()
        except ValueError:
            pass

    def recieveFromRShoe(self, message):
        try:
            self.currentTemps['shoeR']=float(message)
            self.most_current_shoeR_timestamp=time.time()
        except ValueError:
            pass         

    def runSetup(self):
        """ execute before main loop """
        self.most_current_dataloggerR_timestamp=0
        self.most_current_dataloggerC_timestamp=0
        self.most_current_dataloggerB_timestamp=0
        self.most_current_shoeR_timestamp=0
        self.most_current_shoeB_timestamp=0
    

if __name__=='__main__':
    agent=DataloggerAgent()
    agent.main()

