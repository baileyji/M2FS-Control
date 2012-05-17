#!/opt/local/bin/python2.7
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
from SelectedConnection import SelectedSerial
from agent import Agent
from command import Command

MAX_CLIENTS=2

class ShoeFirmwareError(Exception):
    pass

class ShoeSerial(SelectedSerial):
    def connect(self):
        if not self.isOpen():
            expected_version_string='foobar v0.1'
            critical_error_message=''
            try:
                self.serial=serial.Serial(self.port, self.baudrate, timeout=.5)
                self.sendMessageBlocking('CV')
                response=self.receiveMessageBlocking(delim='\n')
                #response=expected_version_string #DEBUGGING LINE OF CODE
                if response != expected_version_string:
                    error_message=("Incompatible Firmware. Shoe reported '%s' , expected '%s'." %
                        (response,expected_version_string))
                    self.serial.close()
                    raise ShoeFirmwareError(error_message)
            except serial.SerialException,e:
                error_message="Failed initialize serial link. Exception: %s"%str(e)
            except IOError:
                error_message="Shoe failed to handshake."
            if error_message !='':
                self.logger.error(error_message)
                self.serial.close()
                raise IOError(error_message)

class ShoeAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'Shoe Agent')
        #Initialize the shoe
        try:
            self.shoe=ShoeSerial(self.args.DEVICE, 115200, self.logger)
        except ShoeContactException:
            pass
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
        cli_parser.add_argument('-p','--port', dest='PORT',
                                action='store', required=False, type=int,
                                help='the port on which to listen')
        cli_parser.add_argument('command',nargs='*',
                                help='Agent command to execute')
        self.cli_parser=cli_parser
    
    def get_version_string(self):
        return 'Shoe Agent Version 0.2'
    
    def socket_message_recieved_callback(self, source, message_str):
        """Create and execute a Command from the message"""
        """Dispatch message to from the appropriate handler"""
        command_handlers={
            'SLITS':SLITS_comand_handler,
            'SLITS_SLITPOS':SLITPOS_command_handler,
            'SLITS_CURRENTPOS':CURRENTPOS_command_handler,
            'ACTIVEHOLDON':ACTIVEHOLD_command_handler,
            'ACTIVEHOLDOFF':ACTIVEHOLD_command_handler,
            'SLITS_MOVSTEPS':MOVESTEPS_command_handler,
            'SLITS_HARDSTOP':HARDSTOP_command_handler,
            'SLITS_STATUS':self.status_command_handler,
            'SLITS_VERSION':self.version_request_command_handler}
        command_name=message_str.partition(' ')[0]
        command=Command(source, message_str)
        if filter(lambda x: x.source==source, self.commands):
            self.logger.warning('Command %s recieved before command %s finished.' %
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
            response=self.shoe.recieveMessageBlocking(nBytes=1)
            if response == ':':
                command.setReply('OK\n')
            else:
                command.setReply('!ERROR: Shoe did not acknowledge command.\n')
        except IOError:
            command.setReply('!ERROR: Shoe IOError. Was shoe unplugged?\n')
        except ShoeFirmwareError:
            command.setReply('!ERROR: Shoe has incorrect firmware.\n')
            
    def SLITS_command_handler(self, command):
        """ Handle geting/setting the nominal slit position in steps """
        if '?' in command.string:
            """ retrieve the current slit position """
            msg='SG\n' #SLIT GET TODO decide the command, this is a placeholder
            try:
                self.shoe.connect()
                self.shoe.sendMessageBlocking(msg)
                response=self.shoe.recieveMessageBlocking(delim='\n')
                if ':' in response:
                    command.setReply(response.replace(':','\n')
                else:
                    command.setReply('!ERROR: Shoe did not acknowledge command.\n')
            except IOError:
                command.setReply('!ERROR: Shoe IOError. Was shoe unplugged?\n')
            except ShoeFirmwareError:
                command.setReply('!ERROR: Shoe has incorrect firmware.\n')
        else:
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
            else:
                command.setReply('!ERROR: Improperly formatted command.\n')
                return
            self.simpleSend('TD'+tetrisID+slit+pos+'\n',command)            

    def SLITPOS_command_handler(self, command):
        """ Handle geting/setting the nominal slit position in steps """
        if '?' in command.string:
            """ retrieve the current slit position """
            command_parts=command.string.split(' ')
            if (len(command_parts)>2 and 
                len(command_parts[1])==1 and command_parts[1] in '12345678' and
                len(command_parts[2])==1 and command_parts[2] in '1234567'):
                tetrisID='ABCDEFGH'[int(command_parts[1])-1]
                slit=command_parts[2]
            else:
                command.setReply('!ERROR: Improperly formatted command.\n')
                return
            msg='TD'+tetrisID+slit+'\n'
            try:
                self.shoe.connect()
                self.shoe.sendMessageBlocking(msg)
                response=self.shoe.recieveMessageBlocking(delim='\n')
                if ':' in response:
                    command.setReply(response.replace(':','\n')
                else:
                    command.setReply('!ERROR: Shoe did not acknowledge command.\n')
            except IOError:
                command.setReply('!ERROR: Shoe IOError. Was shoe unplugged?\n')
            except ShoeFirmwareError:
                command.setReply('!ERROR: Shoe has incorrect firmware.\n')
        else:
            command_parts=command.string.split(' ')
            if (len(command_parts)>3 and 
                len(command_parts[1])==1 and command_parts[1] in '12345678' and
                len(command_parts[2])==1 and command_parts[2] in '1234567' and
                command_parts[3].isdigit()):
                tetrisID='ABCDEFGH'[int(command_parts[1])-1]
                slit=command_parts[2]
                pos=command_parts[3]
            else:
                command.setReply('!ERROR: Improperly formatted command.\n')
                return
            self.simpleSend('TD'+tetrisID+slit+pos+'\n',command)
    
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
        try:
            self.shoe.connect()
            self.shoe.sendMessageBlocking(msg)
            response=self.shoe.recieveMessageBlocking(delim='\n')
            if ':' in response:
                command.setReply(response.replace(':','\n')
            else:
                command.setReply('!ERROR: Shoe did not acknowledge command.\n')
        except IOError:
            command.setReply('!ERROR: Shoe IOError. Was shoe unplugged?\n')
        except ShoeFirmwareError:
            command.setReply('!ERROR: Shoe has incorrect firmware.\n')

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



if __name__=='__main__':
    agent=ShoeAgent()
    agent.main()
