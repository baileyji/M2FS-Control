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

MAX_CLIENTS=2

class ShoeFirmwareError(SelectedConnection.ConnectError):
    pass

class ShoeSerial(SelectedConnection.SelectedSerial):
    def connect(self):
        if self.connection is None:
            expected_version_string='Fibershoe v0.1'
            try:
                self.connection=serial.Serial(self.port, self.baudrate, 
                    timeout=self.timeout)
                time.sleep(1)
                self.sendMessageBlocking('PV\n')
                response=self.receiveMessageBlocking()
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
                  print 'type match'
                  raise e
                error_message="Shoe failed to handshake. %s"%e
                self.logger.error(error_message)
                #self.connection.close()
                self.connection=None
                raise SelectedConnection.ConnectError(error_message)

class ShoeAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'ShoeAgent')
        #Initialize the shoe
        self.shoe=ShoeSerial(self.args.DEVICE, 115200, self.logger, timeout=.5)
        self.devices.append(self.shoe)
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def initialize_cli_parser(self):
        """Configure the command line interface"""
        #Create a command parser with the default agent commands
        helpdesc="This is the shoe agent. It takes shoe commands via \
            a socket connection (if started as a daemon) or via \
            CLI arguments."
        cli_parser = argparse.ArgumentParser(
                    description=helpdesc,
                    add_help=True)
        cli_parser.add_argument('--version',
                                action='version',
                                version=self.get_version_string())
        cli_parser.add_argument('-d','--daemon',dest='DAEMONIZE',
                                action='store_true', default=False,
                                help='Run agent as a daemon')
        cli_parser.add_argument('--device', dest='DEVICE',
                                action='store', required=False, type=str,
                                help='the device to control',
                                default='/dev/shoeR')
        cli_parser.add_argument('--side', dest='SIDE',
                                action='store', required=False, type=str,
                                help='R or B',
                                default='R')
        cli_parser.add_argument('-p','--port', dest='PORT',
                                action='store', required=False, type=int,
                                help='the port on which to listen')
        cli_parser.add_argument('command',nargs='*',
                                help='Agent command to execute')
        self.cli_parser=cli_parser
    
    def get_version_string(self):
        return 'Shoe Agent Version 0.2'
    
    def socket_message_received_callback(self, source, message_str):
        """Create and execute a Command from the message"""
        """Dispatch message to from the appropriate handler"""
        command_handlers={
            'SLITS':self.SLITS_command_handler,
            'SLITS_SLITPOS':self.SLITPOS_command_handler,
            'SLITS_CURRENTPOS':self.CURRENTPOS_command_handler,
            'ACTIVEHOLDON':self.ACTIVEHOLD_command_handler,
            'ACTIVEHOLDOFF':self.ACTIVEHOLD_command_handler,
            'SLITS_TEMP':self.TEMP_command_handler,
            'SLITS_MOVSTEPS':self.MOVESTEPS_command_handler,
            'SLITS_HARDSTOP':self.HARDSTOP_command_handler,
            'SLITS_STATUS':self.status_command_handler,
            'SLITS_VERSION':self.version_request_command_handler}
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
            response=self.shoe.receiveMessageBlocking(nBytes=1)
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
    
    def TEMP_command_handler(self, command):
        """ Handle requesting the temperature from the shoe """
        self.simpleSendWithResponse('TE\n', command) 
    
    def SLITS_command_handler(self, command):
        """ Handle geting/setting the nominal slit position in steps """
        if '?' in command.string:
            """ retrieve the current slits """
            self.simpleSendWithResponse('SG*\n', command)
        else:
            """ command tetri to move to set slit positions """
            command_parts=command.string.replace(',',' ').split(' ')
            if (len(command_parts)==9 and 
                len(command_parts[1])==1 and command_parts[1] in '1234567' and
                len(command_parts[2])==1 and command_parts[2] in '1234567' and
                len(command_parts[3])==1 and command_parts[3] in '1234567' and
                len(command_parts[4])==1 and command_parts[4] in '1234567' and
                len(command_parts[5])==1 and command_parts[5] in '1234567' and
                len(command_parts[6])==1 and command_parts[6] in '1234567' and
                len(command_parts[7])==1 and command_parts[7] in '1234567' and
                len(command_parts[8])==1 and command_parts[8] in '1234567'):
                self.simpleSend('SL'+''.join(command_parts[1:])+'\n', command)
            else:
                command.setReply('!ERROR: Improperly formatted command.\n')
                return
    
    def SLITPOS_command_handler(self, command):
        """ Handle geting/setting the nominal slit position in steps """
        command_parts=command.string.split(' ')
        if (len(command_parts)>2 and 
            len(command_parts[1])==1 and command_parts[1] in '12345678' and
            len(command_parts[2])==1 and command_parts[2] in '1234567' and 
            ('?' in command.string or (len(command_parts)>3 and
                                       command_parts[3].isdigit()))):
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
            slit=command_parts[2]
        else:
            command.setReply('!ERROR: Improperly formatted command.\n')
            return
        if len(command_parts)>3:
            """ Set the position """
            pos=command_parts[3]
            self.simpleSend('SS'+tetrisID+slit+pos+'\n',command)
        else:
            """ Get the position """
            self.simpleSendWithResponse('SD'+tetrisID+slit+'\n', command)
    
    def CURRENTPOS_command_handler(self, command):
        """ handle command to fetch the current step position of the tetris"""
        command_parts=command.string.split(' ')
        if (len(command_parts)>1 and 
            len(command_parts[1])==1 and 
            command_parts[1] in '12345678'):
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
        else:
            command.setReply('!ERROR: Improperly formatted command.\n')
            return
        msg='TD'+tetrisID+'\n'
        self.simpleSendWithResponse('TD'+tetrisID+'\n', command)

    def ACTIVEHOLD_command_handler(self, command):
        """ handle switching between motors on while idle and motors off"""
        msg='AH\n' if 'ON' in command.string else 'PH\n'
        self.simpleSend(msg, command)
     
    def HARDSTOP_command_handler(self, command):
        """ handle switching between motors on while idle and motors off"""
        command_parts=command.string.split(' ')
        if (len(command_parts)>1 and 
            len(command_parts[1])==1 and 
            command_parts[1] in '12345678'):
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
        else:
            command.setReply('!ERROR: Improperly formatted command.\n')
            return
        self.simpleSend('DH'+tetrisID+'\n', command)
    
    def MOVESTEPS_command_handler(self, command):
        """ handle commanding a single tetris to move X steps"""
        command_parts=command.string.split(' ')
        if (len(command_parts)>2 and 
            len(command_parts[1])==1 and command_parts[1] in '12345678' and
            command_parts[2].isdigit()):
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
            steps=command_parts[2]
        else:
            command.setReply('!ERROR: Improperly formatted command.\n')
            return
        self.simpleSend('PR'+tetrisID+steps+'\n', command)

    def status_command_handler(self, command):
      """report status"""
      self.simpleSendWithResponse('TS\n', command)
      

if __name__=='__main__':
    agent=ShoeAgent()
    agent.main()
