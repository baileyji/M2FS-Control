#!/usr/bin/env python2.7
import sys, time
sys.path.append(sys.path[0]+'/../lib/')
import SelectedConnection
from agent import Agent
from m2fsConfig import m2fsConfig
from haydonidea import IdeaDrive

EXPECTED_FIBERSHOE_INO_VERSION='Fibershoe v1.3'
OCCULTER_AGENT_VERSION_STRING='Occulter Agent v1.0'
OCCULTER_AGENT_VERSION_STRING_SHORT='v1.0'

DH_TIME=35
SHOE_BOOT_TIME=2
SHOE_SHUTDOWN_TIME=.25
MAX_SLIT_MOVE_TIME=25

def longTest(s):
    """ Return true if s can be cast as a long, false otherwise """
    try:
        long(s)
        return True
    except ValueError:
        return False

class ShoeSerial(SelectedConnection.SelectedSerial):
    """ 
    Tetris Shoe Controller Connection Class
    
    This class extents the SelectedSerial implementation of SelectedConnection
    with custom implementations of _postConnect and 
    _implementationSpecificDisconnect.
    
    The _postConnect hook is used to verify the shoe is running a compatible 
    firmware version. EXPECTED_FIBERSHOE_INO_VERSION should match the define for
    VERSION_STRING in fibershoe.ino
    
    _implementationSpecificDisconnect is overridden to guarantee the shoe is 
    told to power down whenever the serial connection closes.
    """
    def _preConnect(self):
        """
        Attempt at workaround for 
        https://bugs.launchpad.net/digitemp/+bug/920959
        """
        try:
            from subprocess import call
            s='stty crtscts < {device};stty -crtscts < {device}'.format(
                device=self.port)
            ret=call(s,shell=True)
        except Exception, e:
            raise SelectedConnection.ConnectError(
                    'rtscts hack failed. {}:{}:{}'.format(s,ret,str(e)))

    def _postConnect(self):
        """
        Implement the post-connect hook

        With the shoe we need verify the firmware version. If if doesn't match
        the expected version fail with a ConnectError. 
        """
        #Shoe takes a few seconds to boot
        time.sleep(SHOE_BOOT_TIME)
        #verify the firmware version
        self.sendMessageBlocking('PV')
        response=self.receiveMessageBlocking()
        self.receiveMessageBlocking(nBytes=1) #discard the :
        if response != EXPECTED_FIBERSHOE_INO_VERSION:
            error_message=("Incompatible Firmware, Shoe reported '%s' , expected '%s'."  %
                (response,EXPECTED_FIBERSHOE_INO_VERSION))
            raise SelectedConnection.ConnectError(error_message)
    
    def _implementationSpecificDisconnect(self):
        """ Disconnect the serial connection, telling the shoe to disconnect """
        try:
            self.connection.write('DS\n')
            time.sleep(SHOE_SHUTDOWN_TIME) #just in case the shoe resets on close,
            #gives time to write to EEPROM
            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except Exception, e:
            pass

class OcculterAgent(Agent):
    """
    This control program is responsible for controlling a singler Occulter mask.
    Three instances are run, one for each of the IFUs.
    
    Low level device functionality is handled by the HaydonKerk IDEA driver. The
    proprietary code run on the drive is found in the files in ../haydonkerk/*.idea,
    one per subroutine. (TODO place files!)
    """
    def __init__(self):
        Agent.__init__(self, 'OcculterAgent')
        self.IFU = self.args.IFU
        #Initialize the shoe
        if not self.args.DEVICE:
            self.args.DEVICE = '/dev/occulter'+self.IFU
        self.connections['occulter'] = IdeaDrive(port=self.args.DEVICE)

        self.command_handlers.update({
            #Send the command string directly to the shoe
            'OCCRAW': self.RAW_command_handler,
            #Get/Set the position of the occulter. The move is carried out closedloop by the controller
            'OCC': self.OCC_command_handler,
            #Move by a relative step amount
            'OCC_STEP': self.STEP_command_handler,
            #Calibrate the occulter
            'OCC_CALIBRATE': self.CALIBRATE_command_handler})
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the occulter agent. It takes occulter commands via \
        a socket connection or via CLI arguments."
    
    def add_additional_cli_arguments(self):
        """
        Additional CLI arguments may be added by implementing this function.
        
        Arguments should be added as:
        self.cli_parser.add_argument(See ArgumentParser.add_argument for syntax)
        """
        self.cli_parser.add_argument('--ifu', dest='IFU', action='store', required=False,
                                     type=str, help='H, M, L', default='M')
        self.cli_parser.add_argument('--device', dest='DEVICE', help='the device to control',
                                     action='store', required=False, type=str)
        self.cli_parser.add_argument('command', nargs='*', help='Agent command to execute')
    
    def get_version_string(self):
        """ Return a string with the version."""
        return OCCULTER_AGENT_VERSION_STRING

    def _send_command_to_shoe(self, command_string):
        """
        Send a command string to the shoe, wait for immediate response
        
        Silently ignore an empty command.
        
        Raise ShoeCommandNotAcknowledgedError if the shoe does not acknowledge
        any part of the command.
        
        Procedure is as follows:
        Send the command string to the shoe
        grab a singe byte from the shoe and if it isn't a : or a ? listen for
        a \n delimeted response followed by a :.
        
        Return a string of the response to the commands.
        Note the : ? are not considered responses. ? gets the exception and :
        gets an empty string. The response is stripped of whitespace.
        """
        #No command, return
        if not command_string:
            return ''
        #Send the command(s)
        self.connections['shoe'].sendMessageBlocking(command_string)
        #Get the first byte from the galil, typically this will be it
        response=self.connections['shoe'].receiveMessageBlocking(nBytes=1)
        # 3 cases:, :, ?, or stuff followed by \r\n:
        #case 1, command succeeds but returns nothing, return
        if response ==':':
            return ''
        #command fails
        elif response =='?':
            raise ShoeCommandNotAcknowledgedError(
                "ERROR: Shoe did not acknowledge command '%s' (%s)" %
                (command_string, response) )
        #command is returning something
        else:
            #do a blocking receive on \n
            response=response+self.connections['shoe'].receiveMessageBlocking()
            #...and a single byte read to grab the :
            confByte=self.connections['shoe'].receiveMessageBlocking(nBytes=1)
            if confByte==':':
                return response.strip()
            else:
                #Consider it a failure, but log it. Add the byte to the
                # response for logging
                response+=confByte
                err=("Shoe did not adhere to protocol. '%s' got '%s'" %
                    (command_string, response))
                self.logger.warning(err)
                raise ShoeCommandNotAcknowledgedError('ERROR: %s' % err)
    
    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pairs:
            name:cookie,
            Drivers:[Powered| Off]
            On: string of tetri numbers that are on e.g. '1 4 6' or None
            Moving: string of tetri numbers that are moving
            Calibrated: string of tetri numbers that are calibrated 
            


        """
        #Name & cookie
        status_list=[(self.name+' '+SHOE_AGENT_VERSION_STRING_SHORT,
                      self.cookie)]
        cradleState='Shoe'+m2fsConfig.getShoeColorInCradle(self.args.SIDE)
        try:
            response=self._send_command_to_shoe('TS').split(' ')
            try:
                shieldIsOn=int(response[0]) & 0x01 == 1
                tetriOnStr=byte2bitNumberString(int(response[1]))
                tetriCalibStr=byte2bitNumberString(int(response[2]))
                tetriMovingStr=byte2bitNumberString(int(response[3]))
                status_list.extend([
                    ('Drivers','On' if shieldIsOn else 'Off'),
                    ('On',tetriOnStr if tetriOnStr else 'None'),
                    ('Moving',tetriMovingStr if tetriMovingStr else 'None'),
                    ('Calibrated',tetriCalibStr if tetriCalibStr else 'None')])
            except Exception:
                cradleState+=' not responding properly to status request'
        except IOError, e:
            cradleState='Disconnected'
        status_list.insert(2, ('Cradle'+self.args.SIDE, cradleState))
        return status_list
    
    def RAW_command_handler(self, command):
        """ 
        Send a raw string to the shoe and wait for a response
        
        NB the PC command can generate more than 1024 bytes of data
        """
        arg=command.string.partition(' ')[2]
        if arg:
            try:
                response=self.connections['occulter'].send_command_to_hk(arg)
                response=response.replace('\r','\\r').replace('\n','\\n')
                if not response:
                    response = 'IDEA DRIVE GAVE NO RESPONSE'
            except IOError, e:
                response='ERROR: %s' % str(e)
            command.setReply(response)
        else:
            self.bad_command_handler(command)

    def _stowShutdown(self):
        """
        Perform a stowed shutdown
        """
        if 'occulter' not in self.connections:
            return
        #TODO Robustify
        stow = m2fsConfig.getOcculterDefaults(self.IFU)['stowpos']
        self.connections['occulter'].move_to(stow)

    def OCC_command_handler(self, command):
        """
        Get/Set the occulter position.
        
        Command is of the form
        OCC #
        or 
        OCC ?
        
        If setting, the command instructs the occulter to move to the
        requested position, closedloop. It is an error to set the slits
        when they are uncalibrated or a move is in progress. If done the error
        '!ERROR: Can not set slits at this time. will be generated.'

        
        If getting, respond in the form # or STATE (#) where STATE is one of
        UNCALIBRATED, MOVING, FAULT.
        """
        if '?' in command.string:
            #Fetch state and return status
            state = self.connections['occulter'].state
            if state.moving or not state.calibrated or state.errorPresent:
                s = 'MOVING' if state.moving else 'FAULT' if state.errorPresent else 'UNCALIBRATED'
                command.setReply('{} ({})'.format(s, state.position))
            else:
                command.setReply(str(state.position))
        else:
            #Vet the command
            command_parts = command.string.split(' ')
            try:
                pos = float(command_parts[1])
            except ValueError:
                self.bad_command_handler(command)
            #First check to make sure the command is allowed (all we calibrated and not
            # moving
            state = self.connections['occulter'].state
            if state.errorPresent:
                command.setReply('ERROR: Fault Codes Present ({})'.format(state.faultString))
                return
            if state.moving:  #TODO is this ok like for the selector or no ok like galil
                command.setReply('ERROR: Move in progress.')
                return

            command.setReply('OK')

            self.startWorkerThread(command, 'MOVING', self.occulter_mover,
                                   args=(pos, not state.calibrated, 'PREPARING'),
                                   block=('OCCRAW', 'OCC', 'OCC_STEP', 'OCC_CALIBRATE'))

    def occulter_mover(self, pos, calibrate, status):
        """
        slits is a 8-tuple or list of number strings '1' - '7'
        status is the response to the command TS
        """
        #Command the shoe to reconfigure the tetrii
        #Determine which are uncalibrated
        if calibrate:
            try:
                #TODO do I need to grab the rlock of the occulter,
                # Probably within these functions maybe internally to the Haydonidea,
                # look at existing code with self.connections['occulter'].rlock:
                self.connections['occulter'].calibrate()

            except RuntimeError:  # calibration failed.
                #TODO need to handle disconnection
                failcode = self.connections['occulter'].state.faultString
                self.returnFromWorkerThread('OCC', finalState='ERROR: Calibration failed ({})'.format(failcode))

        with self.connections['shoe'].rlock: #TODO needed?
            self.connections['occulter'].move_to(pos)
            success = True #TODO error fail handling for io? 
            if not success:
                resp = 'ERROR: some description'
                self.returnFromWorkerThread('SLITS', finalState=resp)
                return
        self.returnFromWorkerThread('OCC')
    
    def OCC_CALIBRATE_command_handler(self, command):
        """
        Command the haydon drive to perform the calibration routine. This can ccause motion
        to last for several seconds even though the command will not block.
        
        This command has no arguments
        """
        #TODO error condition checking needed?
        self.connections['occulter'].calibrate()
        command.setReply('OK')
    
    def OCC_STEP_command_handler(self, command):
        """
        Command a relative, uncalibrated move a specified number of steps
        
        This command has one argument: the number of steps
        to move. The full range of travel of an occulter corresponds to about
        ? +/-? steps. Extending is in the positive direction.
        """
        command_parts = command.string.split(' ')
        #Vet the command
        if len(command_parts) > 1 and longTest(command_parts[1]):
            #TODO add limit protections?
            state = self.connections['occulter'].state
            if state.errorPresent:
                command.setReply('ERROR: Fault codes present ({})'.format(state.faultString))
                return
            if state.moving:  #TODO is this ok like for the selector or no ok like galil
                command.setReply('ERROR: Move in progress.')
                return
            self.connections['occulter'].move_to(int(command_parts[1]), relative=True)
            command.setReply('OK')
        else:
            self.bad_command_handler(command)


if __name__=='__main__':
    agent=OcculterAgent()
    agent.main()
