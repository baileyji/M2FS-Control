#!/opt/local/bin/python2.7
import time
import argparse
import socket
import signal
import logging
import logging.handlers
import atexit
import serial
import sys
import select
sys.path.append('./Galil/')
import galil
from HandledSocket import HandledSocket
from agent import Agent
from command import Command
import sqlite3

MAX_CLIENTS=2

class DataloggerAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'Datalogger Agent')
        
        #Initialize the dataloggers
        self.dataloggerR=datalogger.Datalogger('/dev/dataloggerR', self.logger)
        self.dataloggerB=datalogger.Datalogger('/dev/dataloggerB', self.logger)
        self.dataloggerC=datalogger.Datalogger('/dev/dataloggerC', self.logger)
        self.devices.append(dataloggerR)
        self.devices.append(dataloggerB)
        self.devices.append(dataloggerC)
        

        
        #open the logging database TODO
        self.num_temps=5
        self.database=sqlite3.connect(self.database_file)
        self.initialize_database()
        #open the connection to the fiber shoes
        #shoeR=
        #shoeB=

    def initialize_database(self)
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
        self.database.execute("create table if not exists "+temps_table_definition)
        self.database.execute("create table if not exists "+accel_table_definition)
        
    
    def listenOn(self):
        return ('localhost', self.PORT)
      
    def get_version_string(self):
        return 'Datalogger Agent Version 0.1'
    
    def socket_message_recieved_callback(self, source, message_str):
        """Create and execute a Command from the message"""
        if False:#message_str is malformed:
            command=Command(source, message_str, state='complete',
                reply='!ERROR: Malformed Command', callback=None)
        else:
            command=Command(source, message_str, callback=None)
            existing_commands_from_source=filter(lambda x: x.source==source, self.commands)
            if not existing_commands_from_source:
                command_handlers={
                    'TEMPS':self.report_current_temps_command_handler,
                    'STATUS':self.report_status_command_handler}
                command_class=message_str.partition(' ')[0].partition('_')[0]
                command_handlers.get(command_class.upper(), self.bad_command_handler)(command)
            else:
                #...ignore and log error
                self.logger.warning(
                    'Command %s recieved before command %s finished.' %
                    (message_str, existing_commands_from_source[0].string))
    
    def report_current_temps_command_handler(self, command):
        """ report the current temperatures """
        temps=self.get_current_temps()
        command.state='complete'
        command.reply=''.join((len(temps)*"%f ")%temps)+'\n'
    
    def report_status_command_handler(self, command):
        """ report status info """
        #compile status info
        #TODO
        command.state='complete'
        command.reply='TODO: current state of the dataloggers \n' #TODO
    
    def get_current_temps(self):
        return self.current_temps

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
        num_R_temps=3
        num_C_temps=6
        num_B_temps=3
        if self.dataloggerR.have_unfetched_temps():
            timestamp,temps=self.dataloggerR.fetch_temps()
            #self.insert_dataloggerR_temps_in_database(timestamp,temps)
            if timestamp[0]>self.most_current_dataloggerR_timestamp:
                self.most_current_dataloggerR_timestamp=timestamp[0]
                self.current_temps[0:num_R_temps]=temps
        if self.dataloggerC.have_unfetched_temps():
            timestamp,temps=self.dataloggerC.fetch_temps()
            #self.insert_dataloggerC_temps_in_database(timestamp,temps)
            if timestamp[0]>self.most_current_dataloggerC_timestamp:
                self.most_current_dataloggerC_timestamp=timestamp[0]
                self.current_temps[num_R_temps:
                    num_R_temps+num_C_temps]=temps
        if self.dataloggerB.have_unfetched_temps():
            timestamp,temps=self.dataloggerB.fetch_temps()
            #self.insert_dataloggerB_temps_in_database(timestamp,temps)
            if timestamp[0]>self.most_current_dataloggerB_timestamp:
                self.most_current_dataloggerB_timestamp=timestamp[0]
                self.current_temps[num_R_temps+num_C_temps:
                    num_R_temps+num_C_temps+num_B_temps]=temps

        #once per minute start a query to the shoes for temps
        #TODO
        
        
        #check that the dataloggers are online
        #TODO


    def runSetup(self):
        """ execute before main loop """
        self.most_current_dataloggerR_timestamp=0
        self.most_current_dataloggerC_timestamp=0
        self.most_current_dataloggerB_timestamp=0


if __name__=='__main__':
    agent=GalilAgent()
    agent.main()

