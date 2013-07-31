#!/usr/bin/env python2.7
import sys, time
sys.path.append(sys.path[0]+'/../lib/')
import SelectedConnection
from agent import Agent
from m2fsConfig import m2fsConfig

EXPECTED_FIBERSHOE_INO_VERSION='Fibershoe v0.7'
SHOE_AGENT_VERSION_STRING='Shoe Agent v0.4'
SHOE_AGENT_VERSION_STRING_SHORT='v0.4'

DH_TIME=90

def longTest(s):
    """ Return true if s can be cast as a long, false otherwise """
    try:
        long(s)
        return True
    except ValueError:
        return False

def byte2bitNumberString(byte):
    """ Convert '10110000' to '5 6 8' """
    bytestr='{0:08b}'.format(byte)
    return ' '.join([str(8-i) for i,bit in enumerate(bytestr) if bit=='1'][-1::-1])

class ShoeCommandNotAcknowledgedError(IOError):
    """ Shoe fails to acknowledge a command, e.g. didn't respond with ':' """
    pass

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
    def _postConnect(self):
        """
        Implement the post-connect hook

        With the shoe we need verify the firmware version. If if doesn't match
        the expected version fail with a ConnectError. 
        """
        #Shoe takes a few seconds to boot
        time.sleep(2)
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
            time.sleep(.25) #just in case the shoe resets on close, 
            #gives time to write to EEPROM
            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except Exception, e:
            pass

class ShoeAgent(Agent):
    """
    This control program is responsible for controlling the fiber shoe for one
    side of the spectrograph. Two instances are run, one for the R side
    and one for the B side.
    
    Low level device functionality is handled by the Arduino microcontroller 
    embedded in the shoe itself. The C++ code run on the shoe is found in the
    file fibershoe.ino and its libraries in ../Arduino/libraries
    
    The agent supports two simultaneous connections to allow the datalogger to
    request the shoe temperature.
    """
    def __init__(self):
        Agent.__init__(self,'ShoeAgent')
        #Initialize the shoe
        if not self.args.DEVICE:
            self.args.DEVICE='/dev/shoe'+self.args.SIDE
        self.connections['shoe']=ShoeSerial(self.args.DEVICE, 115200, timeout=1)
        #Allow two connections so the datalogger agent can poll for temperature
        self.max_clients=2
        self.command_handlers.update({
            #Send the command string directly to the shoe
            'SLITSRAW':self.RAW_command_handler,
            #Get/Set the active slit on all 8 tetri. The move is carried out
            # openloop based on the defined step positions for each slit.
            'SLITS':self.SLITS_command_handler,
            #Get/Set the step position corresponding to a slit on a tetris
            'SLITS_SLITPOS':self.SLITPOS_command_handler,
            #Get the current step position of a tetris 
            'SLITS_CURRENTPOS':self.CURRENTPOS_command_handler,
            #Turn active holding of the slit position on or off
            'SLITS_ACTIVEHOLD':self.ACTIVEHOLD_command_handler,
            #Get the temperature of the shoe
            'SLITS_TEMP':self.TEMP_command_handler,
            #Tell the shoe to move a tetris a number of steps
            'SLITS_MOVESTEPS':self.MOVESTEPS_command_handler,
            #Tell shoe to drive a tetris to the hardstop, calibrating it
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
    
    def _do_online_only_command(self, command):
        """
        Execute a command that requires the shoe to be online
        
        This command wraps command with an attempt to bring the shoe online.
        If the shoe won't come online an appropriate error response is returned
        and the command is not attempted.
        If the command fails the error is returned.
        If the command succeeds but returns nothing 'OK' is returned.
        """
        try:
            self._send_command_to_shoe('CS')
        except ShoeCommandNotAcknowledgedError:
            return 'ERROR: Tighten locking nuts on cradle %s' % self.args.SIDE
        except IOError:
            return 'ERROR: Shoe not in cradle %s' % self.args.SIDE
        try:
            response=self._send_command_to_shoe(command)
            if not response:
                response='OK'
            return response
        except IOError, e:
            response=str(e)
            if not response.startswith('ERROR: '):
                return 'ERROR: '+response
            else:
                return response
    
    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pairs:
            name:cookie,
            Cradle<color>:Shoe<color> <Error if not responding properly>
            Drivers:[Powered| Off]
            On: string of tetri numbers that are on e.g. '1 4 6' or None
            Moving: string of tetri numbers that are moving
            Calibrated: string of tetri numbers that are calibrated 
            
        Status is reported as 4 bytes with the form
        Byte 1) [DontcareX5][shoeOnline][shieldIsR][shieldIsOn]
        Byte 2) [tetris7on]...[tetris0on]
        Byte 3) [tetris7calibrated]...[tetris0calibrated]
        Byte 4) [tetris7moving]...[tetris0moving]
        NB we dont actually use the shieldIsR bit since udev is checking based
        on serial numbers
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
                self.connections['shoe'].sendMessageBlocking(arg)
                response=self.connections['shoe'].receiveMessageBlocking(nBytes=2048)
                response=response.replace('\r','\\r').replace('\n','\\n')
            except IOError, e:
                response='ERROR: %s' % str(e)
            command.setReply(response)
        else:
            self.bad_command_handler(command)
    
    def TEMP_command_handler(self, command):
        """
        Get the current shoe temperature
        
        Responds with the temp or UNKNOWN
        """
        if self.connections['shoe'].rlock.acquire(False):
            try:
                
                response=self._send_command_to_shoe('TE')
            except IOError, e:
                response='UNKNOWN'
            finally:
                self.connections['shoe'].rlock.release()
        else:
            response='ERROR: Busy, try again'
        command.setReply(response)
    
    def SLITS_command_handler(self, command):
        """
        Get/Set the active slit on all 8 tetri.
        
        Command is of the form
        SLITS {1-7} {1-7} {1-7} {1-7} {1-7} {1-7} {1-7} {1-7} 
        or 
        SLITS ?
        
        If setting, the command instructs the shoe to move each tetris to the 
        requested slit position, openloop, using the defined step position for
        that slit. It is an error to set the slits when they are uncalibrated 
        or a move is in progress. If done the error '!ERROR: Can not set slits at
        this time. will be generated.' TODO integrate with TS command to provide 
        informative reason for falure. NB The shoe just returns ?
        
        If getting, respond in the from TETRIS0, ..., TETRIS7
        where TETRISi is one of UNKNOWN INTERMEDIATE MOVING or {1-7}, 7
        representing the closed position.
        """
        if '?' in command.string:
            #Command the shoe to report the active slit for all 8 tetri
            command.setReply(self._do_online_only_command('SG*'))
        else:
            #Vet the command
            command_parts=command.string.replace(',',' ').split(' ')
            if not (len(command_parts)==9 and
                len(command_parts[1])==1 and command_parts[1] in '1234567' and
                len(command_parts[2])==1 and command_parts[2] in '1234567' and
                len(command_parts[3])==1 and command_parts[3] in '1234567' and
                len(command_parts[4])==1 and command_parts[4] in '1234567' and
                len(command_parts[5])==1 and command_parts[5] in '1234567' and
                len(command_parts[6])==1 and command_parts[6] in '1234567' and
                len(command_parts[7])==1 and command_parts[7] in '1234567' and
                len(command_parts[8])==1 and command_parts[8] in '1234567'):
                self.bad_command_handler(command)
            #First check to make sure the command is allowed (all are
            # calibrated and none are moving
            #Verify all tetri are calibrated and none are moving
            # see documentation of TS command in fibershoe.ino or
            # get_status_list
            status=self._do_online_only_command('TS')
            if status.startswith('ERROR:'):
                command.setReply(status)
                return
            movingByte=''.join(status.split()[3:4])
            if '0' != movingByte:
                command.setReply('ERROR: Move in progress (%s).' % movingByte)
                return
            command.setReply('OK')
            slits=''.join(command_parts[1:9])
            self.startWorkerThread(command, 'MOVING', self.slit_mover,
                args=(slits, status),
                block=('SLITSRAW', 'SLITS_SLITPOS', 'SLITS_MOVESTEPS',
                       'SLITS_HARDSTOP'))
    
    def slit_mover(self, slits, status):
        """
        slits is a 8-tuble or list of number strings '1' - '7'
        status is the response to the command TS
        """
        #Command the shoe to reconfigure the tetrii
        #Determine which are uncalibrated
        uncalByte=status.split(' ')[2]
        if uncalByte!='0':
            calibrated=map(lambda x: int(x)-1,
                             byte2bitNumberString(int(uncalByte)).split(' '))
            uncalibrated=[x for x in range(0,8) if x not in calibrated]
        else:
            uncalibrated=range(0,8)
        with self.connections['shoe'].rlock:
            for i in range(0,8):
                if i in uncalibrated:
                    resp=self._do_online_only_command('DH'+'ABCDEFGH'[i])
                else:
                    cmd='SL'+'ABCDEFGH'[i]+slits[i]
                    resp=self._do_online_only_command(cmd)
                if resp !='OK':
                    self.returnFromWorkerThread('SLITS', finalState=resp)
                    return
            self.logger.debug('sleeping with lock active')
            time.sleep(60)
            self.logger.debug('finished sleeping with lock active')
        if len(uncalibrated) > 0:
            time.sleep(DH_TIME)
        with self.connections['shoe'].rlock:
            for i in uncalibrated:
                cmd='SL'+'ABCDEFGH'[i]+slits[i]
                resp=self._do_online_only_command(cmd)
                if resp !='OK':
                    self.returnFromWorkerThread('SLITS', finalState=resp)
                    return
        self.returnFromWorkerThread('SLITS')
    
    def SLITPOS_command_handler(self, command):
        """
        Retrieve or set the step position of a slit
        
        This command has three arguments: the tetris, 1-8; the slit 1-7
        (7=closed); and the slit position or a question mark.
        
        The set position only affects subsequent moves.
        """
        #Vet the command
        command_parts=command.string.split(' ')
        if (len(command_parts)>3 and 
            len(command_parts[1])==1 and command_parts[1] in '12345678' and
            len(command_parts[2])==1 and command_parts[2] in '1234567' and 
            ('?' in command_parts[3] or  longTest(command_parts[3]))):
            #Extract the tetris ID
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
            #...and the slit
            slit=command_parts[2]
            #If getting
            if '?' in command.string:
                #Get the step position of the slit from the requested tetris
                try:
                    response=self._send_command_to_shoe('SD'+tetrisID+slit)
                except IOError:
                    response='ERROR: Shoe not in cradle %s' % self.args.SIDE
            else:
                """ Set the position """
                pos=command_parts[3]
                try:
                    self._send_command_to_shoe('SS'+tetrisID+slit+pos)
                except IOError:
                    response='ERROR: Shoe not in cradle %s' % self.args.SIDE
            command.setReply(response)
        else:
            self.bad_command_handler(command)

    def CURRENTPOS_command_handler(self, command):
        """
        Respond with the current step position of the tetris
        
        This command has one argument: the tetris, 1-8
        """
        command_parts=command.string.split(' ')
        #Vet the command
        if (len(command_parts)>1 and 
            len(command_parts[1])==1 and 
            command_parts[1] in '12345678'):
            #Extract the tetris ID
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
            #Get the step position from the shoe
            response=self._do_online_only_command('TD'+tetrisID)
            command.setReply(response)
        else:
            self.bad_command_handler(command)
    
    def ACTIVEHOLD_command_handler(self, command):
        """
        Turn active holding on or off or query the state.
        
        ACTIVEHOLD [ON|OFF|?]
        
        Active holding leaves the tetris motors energized after a move is
        completed. Note there is no way for the motors to be backdriven
        (The output shaft will shear off before this will happen), so this
        doesn't really do anything other than waste power though it just might
        possibly help repeatability.
        """
        if '?' in command.string:
            try:
                response=self._send_command_to_shoe('GH')
            except IOError, e:
                response=str(e)
            command.setReply(response)
        else:
            if 'ON' in command.string and 'OFF' not in command.string:
                command.setReply(self._do_online_only_command('AH'))
            elif 'OFF' in command.string and 'ON' not in command.string:
                command.setReply(self._do_online_only_command('PH'))
            else:
                self.bad_command_handler(command)
    
    def HARDSTOP_command_handler(self, command):
        """
        Command a tetris to drive to the hardstop, thus calibrating it
        
        This command has one argument: the tetris, 1-8
        """
        command_parts=command.string.split(' ')
        if (len(command_parts)>1 and 
            len(command_parts[1])==1 and 
            command_parts[1] in '12345678'):
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
            command.setReply(self._do_online_only_command('DH'+tetrisID))
        else:
            self.bad_command_handler(command)
    
    def MOVESTEPS_command_handler(self, command):
        """
        Command a tetris to move a specified number of steps
        
        This command has two argument: the tetris, 1-8, and the number of steps
        to move. The full range of travel of a tetris corresponds to about 
        7000 +/-1000 steps. The hardstop is in the positive direction. The
        spring is compressed in the negative direction
        """
        command_parts=command.string.split(' ')
        #Vet the command
        if (len(command_parts)>2 and 
            len(command_parts[1])==1 and
            command_parts[1] in '12345678' and
            longTest(command_parts[2])):
            tetrisID='ABCDEFGH'[int(command_parts[1])-1]
            steps=command_parts[2]
            command.setReply(self._do_online_only_command('PR'+tetrisID+steps))
        else:
            self.bad_command_handler(command)
        

if __name__=='__main__':
    agent=ShoeAgent()
    agent.main()
