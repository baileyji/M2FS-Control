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
sys.path.append('../lib/')
import SelectedConnection
from agent import Agent
from command import Command

MAX_CLIENTS=1

class ShoeFirmwareError(SelectedConnection.ConnectError):
    pass

import termios
class PluggingDisplaySerial(SelectedConnection.SelectedSerial):
    def connect(self):
        if self.connection is None:
            expected_version_string='Sharck-Hartman v0.1'
            try:
                self.connection=serial.Serial(self.port, self.baudrate, 
                    timeout=self.timeout)
                time.sleep(1)
                self.sendMessageBlocking('PV\n')
                response=self.receiveMessageBlocking().replace(':','')
                #response=expected_version_string #DEBUGGING LINE OF CODE
                if response != expected_version_string:
                    error_message=("Incompatible Firmware. Shoe reported '%s' , expected '%s'." %
                        (response,expected_version_string))
                    self.connection.close()
                    self.connection=None
                    raise ShoeFirmwareError(error_message)
            except serial.SerialException,e:
                error_message="Failed initialize serial link. Exception: %s"% e 
                self.logger.error(error_message)
                #self.connection.close()
                self.connection=None
                raise SelectedConnection.ConnectError(error_message)
            except IOError,e :
                if type(e)==type(ShoeFirmwareError):
                  raise e
                error_message="Shoe failed to handshake. %s"%e
                self.logger.error(error_message)
                #self.connection.close()
                self.connection=None
                raise SelectedConnection.ConnectError(error_message)

class ShackhartmanAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'PluggingAgent')
        #Initialize the shoe
        self.shackhart=PluggingDisplaySerial(self.args.DEVICE, 115200, self.logger, timeout=1)
        self.devices.append(self.shackhart)
        self.max_clients=1
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def get_version_string(self):
        return 'Plugging Agent Version 0.1'
    
    def socket_message_received_callback(self, source, message_str):
        """Create and execute a Command from the message"""
        """Dispatch message to from the appropriate handler"""
        command_handlers={
            'PLUGBUTTON':self.not_implemented_command_handler,
            'PLUGERR':self.not_implemented_command_handler,
            'PLUG_STATUS':self.status_command_handler,
            'PLUG_VERSION':self.version_request_command_handler}
        command_name=message_str.partition(' ')[0]
        command=Command(source, message_str)
        existing_commands_from_source=filter(lambda x: x.source==source, self.commands)
        if existing_commands_from_source:
            self.logger.warning('Command %s received before command %s finished.' %
                (message_str, existing_commands_from_source[0].string))
        else:
            self.commands.append(command)
            command_handlers.get(command_name.upper(), self.bad_command_handler)(command)

    def simpleSend(self, msg, command):
        """ Try sending msg to the shoe, close out command. 
            Good for commands which have a simple confirmation and nothing more"""
        try:
            self.shoe.connect()
            self.shoe.sendMessageBlocking(msg)
            response=self.shoe.receiveMessageBlocking(nBytes=2)
            self.logger.debug("SimpleSend got:'%s'"%response.replace('\n','\\n'))
            if response == ':':
                command.setReply('OK\n')
            else:
                command.setReply('!ERROR: Shoe did not acknowledge command.\n')
        except IOError:
            command.setReply('!ERROR: Shoe IOError. Was shoe unplugged?\n')
        except ShoeFirmwareError:
            command.setReply('!ERROR: Shoe has incorrect firmware.\n')
            
    def simpleSendWithResponse(self, msg, command):
        try:
            self.shoe.connect()
            self.shoe.sendMessageBlocking(msg)
            response=self.shoe.receiveMessageBlocking()
            if ':' in response:
                command.setReply(response.replace(':','\n'))
            else:
                command.setReply('!ERROR: Shoe did not acknowledge command.\n')
        except IOError:
            command.setReply('!ERROR: Shoe IOError. Was shoe unplugged?\n')
        except ShoeFirmwareError:
            command.setReply('!ERROR: Shoe has incorrect firmware.\n')
    
    def status_command_handler(self, command):
      """report status"""
      self.not_implemented_command_handler(command)
      

if __name__=='__main__':
    agent=ShackhartmanAgent()
    agent.main()
