#!/usr/bin/env python2.7
import sys, time
sys.path.append(sys.path[0]+'/../lib/')
import SelectedConnection
from agent import Agent

EXPECTED_FIBERSHOE_INO_VERSION='Fibershoe v0.4'
SHOE_AGENT_VERSION_STRING='Shoe Agent v0.3'
SHOE_AGENT_VERSION_STRING_SHORT='v0.3'

import serial
import termios
class ShoeSerial(SelectedConnection.SelectedSerial):
    def _postConnect(self):
        """
        Implement the post-connect hook

        With the shoe we need to do a few things prior to actually accepting
        the connection as healthy:
        1) Query the shoe for the software version. If if doesn't match the
        expected version fail with a ConnectError
        """
        #Shoe takes a few seconds to boot
        time.sleep(2)
        self.sendMessageBlocking('PV\n')
        response=self.receiveMessageBlocking().replace(':','')
        if response != EXPECTED_FIBERSHOE_INO_VERSION:
            if 'Powered Down' in response:
                error_message="Shoe locking nut disengaged"
            else:
                error_message=("Incompatible Firmware, Shoe reported '%s' , expected '%s'."  %
                (response,expected_version_string))
            raise SelectedConnection.ConnectError(error_message)
    
    def _implementationSpecificDisconnect(self):
        """ Disconnect the serial connection """
        try:
            self.connection.write('DS\n')
            time.sleep(.25) #just in case the shoe resets on close, 
            #gives time to write to EEPROM
            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except Exception, e:
            pass


class ShoeAgent(Agent):
    def __init__(self):
        Agent.__init__(self,'ShoeAgent')
        #Initialize the shoe
        if not self.args.DEVICE:
            self.args.DEVICE='/dev/shoe'+self.args.SIDE
        self.shoe=ShoeSerial(self.args.DEVICE, 115200, timeout=1)
        self.devices.append(self.shoe)
        self.max_clients=2
        self.command_handlers.update({
            'SLITSRAW':self.RAW_command_handler,
            'SLITS':self.SLITS_command_handler,
            'SLITS_SLITPOS':self.SLITPOS_command_handler,
            'SLITS_CURRENTPOS':self.CURRENTPOS_command_handler,
            'SLITS_ACTIVEHOLD':self.ACTIVEHOLD_command_handler,
            'SLITS_TEMP':self.TEMP_command_handler,
            'SLITS_MOVESTEPS':self.MOVESTEPS_command_handler,
            'SLITS_HARDSTOP':self.HARDSTOP_command_handler})
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the shoe agent. It takes shoe commands via \
        a socket connection or via CLI arguments."
    
    def add_additional_cli_arguments(self):
        """
        Additional CLI arguments may be added by implementing this function.
        
        Arguments should be added as:
        self.cli_parser.add_argument(See ArgumentParser.add_argument for syntax)
        """
        self.cli_parser.add_argument('--side', dest='SIDE',
                                     action='store', required=False, type=str,
                                     help='R or B',
                                     default='R')
        self.cli_parser.add_argument('--device', dest='DEVICE',
                                     action='store', required=False, type=str,
                                     help='the device to control')
        self.cli_parser.add_argument('command',nargs='*',
                                help='Agent command to execute')
    
    def get_version_string(self):
        """ Return a string with the version."""
        return SHOE_AGENT_VERSION_STRING

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
        except IOError, e:
            command.setReply('ERROR: Shoe%s Disconnected'%self.args.SIDE)
            
    def simpleSendWithResponse(self, msg, command):
        try:
            self.shoe.connect()
            self.shoe.sendMessageBlocking(msg)
            response=self.shoe.receiveMessageBlocking()
            if ':' in response:
                command.setReply(response.replace(':','\n'))
            else:
                command.setReply('ERROR: Shoe did not acknowledge command.\n')
        except IOError, e:
            command.setReply('ERROR: Shoe%s Disconnected'%self.args.SIDE)
    
    def RAW_command_handler(self, command):
        """ pass raw data along to the shoe and wait for a response"""
        msg=command.string.partition(' ')
        response=''
        if len(msg)==3:
            try:
                self.shoe.connect()
                self.shoe.sendMessageBlocking(msg[2]+'\n')
                response=self.shoe.receiveMessageBlocking(nBytes=1024)
            except IOError, e:
                command.setReply('!ERROR: Shoe IOError. %s\n'%e)

        if response:
            command.setReply(response+'\n')
        else:
            command.setReply('No Response\n')
    
    def TEMP_command_handler(self, command):
        """ Handle requesting the temperature from the shoe """
        self.simpleSendWithResponse('TE\n', command) 
    
    def SLITS_command_handler(self, command):
        """ Handle geting/setting the slit """
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
        def longTest(s):
            try:
                long(s)
                return True
            except ValueError:
                return False
        command_parts=command.string.split(' ')
        if (len(command_parts)>3 and 
            len(command_parts[1])==1 and command_parts[1] in '12345678' and
            len(command_parts[2])==1 and command_parts[2] in '1234567' and 
            ('?' in command_parts[3] or  longTest(command_parts[3]))):
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
            slit=command_parts[2]
        else:
            command.setReply('!ERROR: Improperly formatted command.\n')
            return
        if '?' in command.string:
            """ Get the position """
            self.simpleSendWithResponse('SD'+tetrisID+slit+'\n', command)
        else:
            """ Set the position """
            pos=command_parts[3]
            self.simpleSend('SS'+tetrisID+slit+pos+'\n',command)
    
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
        if '?' in command.string:
            self.simpleSendWithResponse('GH\n', command)
        else:
            if 'ON' in command.string and 'OFF' not in command.string:
                self.simpleSend('AH\n', command)
            elif 'OFF' in command.string and 'ON' not in command.string:
                self.simpleSend('PH\n', command)
            else:
                command.setReply('!ERROR: Improperly formatted command.\n')
    
    def HARDSTOP_command_handler(self, command):
        """ handle switching between motors on while idle and motors off"""
        command_parts=command.string.split(' ')
        if (len(command_parts)>1 and 
            len(command_parts[1])==1 and 
            command_parts[1] in '12345678'):
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
            self.simpleSend('DH'+tetrisID+'\n', command)
        else:
            command.setReply('!ERROR: Improperly formatted command.\n')
    
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
        """xxxxxx[shieldR][shieldOn] [t7on]...[t0on] [t7calib]...[t0calib] [t7moving]...[t0moving]"""
        try:
            self.shoe.connect()
            self.shoe.sendMessageBlocking('TS\n')
            response=self.shoe.receiveMessageBlocking()
            if ':' in response:
                command.setReply(response.replace(':','\n'))
            else:
                command.setReply('ERROR: Shoe did not acknowledge command.\n')
        except IOError, e:
            command.setReply('Disconnected')

if __name__=='__main__':
    agent=ShoeAgent()
    agent.main()
