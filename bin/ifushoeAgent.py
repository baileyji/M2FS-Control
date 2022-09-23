#!/usr/bin/env python2.7
import time
from m2fscontrol.agent import Agent
from m2fscontrol.utils import longTest
from m2fscontrol.shoe import ShoeSerial as _ShoeSerial, ShoeCommandNotAcknowledgedError
from m2fscontrol.selectedconnection import ConnectError, ReadError
import serial

EXPECTED_FIBERSHOE_INO_VERSION = 'IFUShoe v2.0'
SHOE_AGENT_VERSION_STRING = 'IFU Shoe Agent v2.0'
SHOE_AGENT_VERSION_STRING_SHORT = SHOE_AGENT_VERSION_STRING.split()[-1]

SHOE_TIMEOUT=.35
MAX_SLIT_MOVE_TIME = 25
STOWSLIT = 1

SLIT_NAMES = {'1': 'S80', '2': 'S300', '3': 'L180', '4': 'L80', '5': 'L300', '6': 'H180'}
SLIT_NUMBERS = {v: k for k, v in SLIT_NAMES.items()}

# 'SLITSRAW': self.RAW_command_handler,
# # Get/Set the active slit.
# 'SLITS': self.SLITS_command_handler,
# # Get/Set the positions corresponding to a slit
# 'SLITS_SLITPOS': self.SLITPOS_command_handler,
# # Get the temperature of the shoe
# 'SLITS_TEMP': self.TEMP_command_handler,  # B, R, drive
# 'SLITS_HARDHAT': self.HARDHAT_command_handler})

def parseTS(xin):
    """
    ===================
    R connected
    B connected
    ===R Shoe Status===
     (pipe, height)
     ADC: 856, 158
     Servo: 836, 154
     Pos (live): 836 (836), 154 (154)
     Err: 0, 0
     Attached: 0, 0
     Moving: 0, 0
      ms since move: 2494990, 2494990
     SL: 256
      SL Delta: 17, -76
     Toler: 33, 33
    Desired Slit: 256
    Detected Slit: INTERMEDIATE
    Errors: 0 MiP: 0 Safe: 0 Relay: 0 Idleoff: 1 curPipeNdx: 5
    Slit Pos:
     Up:    850 835 543 530 484 230
     Down:  300 300 300 300 300 135
     Pipe:  224 343 462 581 700 819
    Free Mem:724
    ===================
    ===B Shoe Status===
     (pipe, height)
     ADC: 419, 158
     Servo: 409, 154
     Pos (live): 409 (409), 154 (154)
     Err: 0, 0
     Attached: 0, 0
     Moving: 0, 0
      ms since move: 2495030, 2495031
     SL: 3
      SL Delta: -53, -416
     Toler: 33, 33
    Desired Slit: 3
    Detected Slit: INTERMEDIATE
    Errors: 0 MiP: 0 Safe: 0 Relay: 0 Idleoff: 1 curPipeNdx: 255
    Slit Pos:
     Up:    865 843 570 530 500 210
     Down:  300 300 300 300 300 135
     Pipe:  224 343 462 581 700 819
    Free Mem:724
    ===================

    """
    x = '\n'.join([l.strip() for l in xin.split('\n') if
                   not l.startswith('#') and
                   '===================' not in l
                   and l.strip()])

    g, r_b = x.split('===R Shoe Status===')
    rstat, bstat = r_b.split('===B Shoe Status===')
    rstat = rstat.strip()
    bstat = bstat.strip()

    def parse_shoestat(x):
        res = {}
        d = {}
        for l in x.split('\n'):
            k, _, v = l.partition(':')
            if not v:
                continue
            d[k] = v
        res['moving'] = [bool(int(x)) for x in d['Moving'].split(',')]
        res['slit'] = d['Detected Slit']
        res['up'] = [int(x) for x in d['Up'].split()]
        res['down'] = [int(x) for x in d['Down'].split()]
        res['pipe'] = [int(x) for x in d['Pipe'].split()]
        res['debug'] = 'Errors: ' + d['Errors']
        res['tol'] = [int(x) for x in d['Toler'].split(',')]
        res['pos_err'] = [int(x) for x in d['SL Delta'].split(',')]
        res['pos'] = [int(x.split()[0]) for x in d['Pos (live)'].split(',')]
        return res

    rd = parse_shoestat(rstat)
    bd = parse_shoestat(bstat)
    response = {}
    if 'R&B Swapped' in g:
        response['ShoeR'] = 'swapped'
    elif 'R disconnected' in g:
        response['ShoeR'] = 'disconnected'
    else:
        response['ShoeR'] = 'connected'

    if 'R&B Swapped' in g:
        response['ShoeB'] = 'swapped'
    elif 'B disconnected' in g:
        response['ShoeB'] = 'disconnected'
    else:
        response['ShoeB'] = 'connected'

    for x in 'RB':
        d = rd if x == 'R' else bd
        for y in ('up', 'down', 'pipe'):
            response[y + '_pos_'+x.lower()] = d[y]
        response['Slit'+x] = d['slit']
        response['Pipe'+x] = 'MOVING ({})'.format(d['pos'][0]) if d['moving'][0] else d['pos'][0]
        response['Height'+x] = 'MOVING ({})'.format(d['pos'][1]) if d['moving'][1] else d['pos'][1]
        response['pos_err_'+x.lower()] = d['pos_err']
        response['tol_' + x.lower()] = d['tol']
        response['debug_'+x.lower()] = d['debug']

    return response


def parseTS_jrk(xin):
    """
    ===================
    R connected
    B connected
    ===R Shoe Status===
     (pipe, height)
     ADC: 856, 158
     Servo: 836, 154
     Pos: 836, 154
     Err: 0, 0
     Moving: 0, 0
      ms since move: 2494990, 2494990
     SL: 256
      SL Delta: 17, -76
     Toler: 33, 33
    Desired Slit: 256
    Detected Slit: INTERMEDIATE
    Errors: 0 MiP: 0 Safe: 0 Relay: 0 Idleoff: 1 curPipeNdx: 5
    Slit Pos:
     Up:    850 835 543 530 484 230
     Down:  300 300 300 300 300 135
     Pipe:  224 343 462 581 700 819
    Free Mem:724
    ===================
    ===B Shoe Status===
     (pipe, height)
     ADC: 419, 158
     Servo: 409, 154
     Pos (live): 409 (409), 154 (154)
     Err: 0, 0
     Attached: 0, 0
     Moving: 0, 0
      ms since move: 2495030, 2495031
      SL Delta: -53, -416
     Toler: 33, 33
    Desired Slit: 3
    Detected Slit: INTERMEDIATE
    Errors: 0
    Jrk: 0, 0
    MiP: 0 Safe: 0 Relay: 0 curPipeNdx: 255
    Slit Pos:
     Up:    865 843 570 530 500 210
     Down:  300 300 300 300 300 135
     Pipe:  224 343 462 581 700 819
    Free Mem:724
    ===================

    """

    x = '\n'.join([l.strip() for l in xin.split('\n') if
                   not l.startswith('#') and
                   '===================' not in l
                   and l.strip()])

    g, r_b = x.split('===R Shoe Status===')
    rstat, bstat = r_b.split('===B Shoe Status===')
    rstat = rstat.strip()
    bstat = bstat.strip()

    def parse_shoestat(x):
        res = {}
        d = {}
        for l in x.split('\n'):
            k, _, v = l.partition(':')
            if not v:
                continue
            d[k] = v
        res['moving'] = [bool(int(x)) for x in d['Moving'].split(',')]
        res['slit'] = d['Detected Slit']
        res['up'] = [int(x) for x in d['Up'].split()]
        res['down'] = [int(x) for x in d['Down'].split()]
        res['pipe'] = [int(x) for x in d['Pipe'].split()]
        res['debug'] = 'Errors: ' + d['Errors']
        res['jrk'] = [int(x, 2) for x in d['Jrk'].split(',')]
        res['tol'] = [int(x) for x in d['Toler'].split(',')]
        res['pos_err'] = [int(x) for x in d['SL Delta'].split(',')]
        res['pos'] = [int(x) for x in d['Pos'].split(',')]
        return res

    rd = parse_shoestat(rstat)
    bd = parse_shoestat(bstat)
    response = {}
    if 'R&B Swapped' in g:
        response['ShoeR'] = 'swapped'
    elif 'R disconnected' in g:
        response['ShoeR'] = 'disconnected'
    else:
        response['ShoeR'] = 'connected'

    if 'R&B Swapped' in g:
        response['ShoeB'] = 'swapped'
    elif 'B disconnected' in g:
        response['ShoeB'] = 'disconnected'
    else:
        response['ShoeB'] = 'connected'

    for x in 'RB':
        d = rd if x == 'R' else bd
        for y in ('up', 'down', 'pipe'):
            response[y + '_pos_'+x.lower()] = d[y]
        response['Slit'+x] = d['slit']
        response['Pipe'+x] = 'MOVING ({})'.format(d['pos'][0]) if d['moving'][0] else d['pos'][0]
        response['Height'+x] = 'MOVING ({})'.format(d['pos'][1]) if d['moving'][1] else d['pos'][1]
        response['pos_err_'+x.lower()] = d['pos_err']
        response['tol_' + x.lower()] = d['tol']
        response['debug_'+x.lower()] = d['debug']
        response['jrk_'+x.lower()] = d['jrk']

    return response


def shoecmd(connection, command_string, logger):
    with connection.rlock:
        connection.sendMessageBlocking(command_string)
        # Get the first byte, typically this will be it
        errmsg = ''
        while True:
            # 3 cases:, #stuff\r\n, :\r\n, ?\r\n, or stuff followed by \r\n:
            response = connection.receiveMessageBlocking()
            if response.startswith('#'):
                logger.debug('Shoe says: {}'.format(response))
                continue
            # case 1, command succeeds but returns nothing, return
            elif response.startswith('ERROR:'):
                errmsg = response
                continue
            elif response == ':':
                return ''
            # command fails
            elif response == '?':
                if errmsg:
                    msg = errmsg
                else:
                    msg = "ERROR: Shoe rejected command '{}'".format(command_string)
                raise ShoeCommandNotAcknowledgedError(msg)
            # command is returning something
            else:
                # ...and a single byte read to grab the :
                confByte = connection.receiveMessageBlocking()
                if confByte == ':':
                    return response.strip()
                else:
                    # Consider it a failure, but log it. Add the byte to the
                    # response for logging
                    response += confByte
                    err = ("Shoe did not adhere to protocol. '%s' got '%s'" % (command_string, response))
                    logger.warning(err)
                    raise ShoeCommandNotAcknowledgedError('ERROR: %s' % err)


class ShoeSerial(_ShoeSerial):
    SHOE_BOOT_TIME = 3.5
    SHOE_SHUTDOWN_TIME = .25
    EXPECTED_FIBERSHOE_INO_VERSION = EXPECTED_FIBERSHOE_INO_VERSION
    """
    Slit moves generate many intermediate messages starting with #, may trigger an internal tellstatus
    and may end with a ERROR:
    
    If during a move a temps or status command command comes though and is issued then it will be executed 
    atomically e.g. the serial coms will look like
    
    slit command sent
    unsolicited lines received
    status or temp request sent
    temp or status response lines
    unsolicited lines from slit movement
    
    any error that must be kept track of will be in the unsolicited lines, rest of lines mere need logging
    """

    def _implementationSpecificRead(self):
        """  Perform a read by line, raise ReadError if any error."""
        try:
            data = self.connection.readline()
            if not data:
                raise ReadError("Unexpectedly empty read")
            return data
        except serial.SerialException, err:
            raise ReadError(err)
        except IOError, err:
            raise ReadError(err)

    def _postConnect(self):
        """
        Implement the post-connect hook

        With the shoe we need verify the firmware version. If it doesn't match
        the expected version fail with a ConnectError.
        """
        # Shoe takes a few seconds to boot
        time.sleep(self.SHOE_BOOT_TIME)
        self.connection.flushInput()
        # verify the firmware version
        self.sendMessageBlocking('PV')
        response = self.receiveMessageBlocking()
        self.receiveMessageBlocking()  # discard the :
        if response != self.EXPECTED_FIBERSHOE_INO_VERSION:
            error_message = ("Incompatible Firmware, Shoe reported '%s', expected '%s'." %
                             (response, self.EXPECTED_FIBERSHOE_INO_VERSION))
            raise ConnectError(error_message)


class IFUShoeAgent(Agent):
    """
    This control program is responsible for controlling the IFU fiber shoes.

    Low level device functionality is handled by the Arduino microcontroller
    embedded in the shoe control tower itself. The C++ code run on the shoe is found in the
    file ifushoe.ino and its libraries in ../Arduino/libraries

    The agent supports two simultaneous connections to allow the datalogger to
    request the shoe temperature.
    """

    def __init__(self):
        Agent.__init__(self, 'IFUShoeAgent')
        # Initialize the shoe
        if not self.args.DEVICE:
            self.args.DEVICE = '/dev/ifum_shoe'
        self.connections['shoe'] = ShoeSerial(self.args.DEVICE, 115200, timeout=SHOE_TIMEOUT,
                                              default_message_received_callback=self._unsolicited_msg_handler)
        # Allow two connections so the datalogger agent can poll for temperature
        self.max_clients = 2
        self._shoe_error = None
        self.command_handlers.update({
            # Send the command string directly to the shoe
            'SLITSRAW': self.RAW_command_handler,
            # Get/Set the active slit.
            'SLIT': self.SLIT_command_handler,
            # downup cycle
            'SLITS_DOWNUP': self.DOWNUP_command_handler,
            # Get/Set the positions corresponding to a slit
            'SLITS_SLITPOS': self.SLITPOS_command_handler,
            # Get the temperature of the shoe
            'SLITS_TEMP': self.TEMP_command_handler,  #B, R, drive
            'SLITS_HARDHAT': self.HARDHAT_command_handler})

    def _unsolicited_msg_handler(self, message_source, message):
        """
        Handle any unsolicited messages from the shoe, see comments in ShoeSerial

        The only expected unsolicited message would be comments # or runtime errors during a move

        If the message indicates an error occurred, extract the details, and set a flag so the user
        will be notified

        Error messages take the form 'ERROR: ....\n'  WITHOUT quotes

        If the message isn't a comment log it as info.
        """
        if message.startswith('ERROR:'):
            self.logger.error('Shoe: {}'.format(message[6:].strip()))
            self._shoe_error = message.strip()
        if message.startswith('#WARN:'):
            self.logger.warning('Shoe: {}'.format(message[6:].strip()))
        else:
            self.logger.info(message.strip())

    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.

        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return ("This is the IFU shoe agent. It takes shoe commands via"
                "a socket connection or via CLI arguments.")

    def add_additional_cli_arguments(self):
        """
        Additional CLI arguments may be added by implementing this function.

        Arguments should be added as:
        self.cli_parser.add_argument(See ArgumentParser.add_argument for syntax)
        """
        self.cli_parser.add_argument('--device', dest='DEVICE',
                                     action='store', required=False, type=str, help='the device to control')
        self.cli_parser.add_argument('command', nargs='*', help='Agent command to execute')

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
        if not command_string:
            return ''
        else:
            return shoecmd(self.connections['shoe'], command_string, self.logger)

    def get_status_list(self):
        """ Return a list of two element tuples to be formatted into a status reply """
        # Name & cookie
        status = {self.name + ' ' + SHOE_AGENT_VERSION_STRING_SHORT: self.cookie}
        try:
            status['Controller'] = 'Online'
            response = self._TS()
            status['ShoeR'] = response['ShoeR']
            status['ShoeB'] = response['ShoeB']
            status['PipeB'] = response['PipeB']
            status['PipeR'] = response['PipeR']
            status['HeightB'] = response['HeightB']
            status['HeightR'] = response['HeightR']
        except ValueError:
            status['Controller'] = 'ERROR: Bad Data'
        except IOError:
            status['Controller'] = 'Disconnected'
        return zip(status.keys(), map(str, status.values()))

    def RAW_command_handler(self, command):
        """
        Send a raw string to the shoe and wait for a response

        NB the PC command can generate more than 1024 bytes of data
        """
        arg = command.string.partition(' ')[2]
        if arg:
            if self._shoe_error is not None:
                command.setReply(self._shoe_error)
                self._shoe_error = None
                return
            try:
                with self.connections['shoe'].rlock:
                    self.connections['shoe'].sendMessageBlocking(arg)
                    response = self.connections['shoe'].receiveMessageBlocking(nBytes=2048)
                response = response.replace('\r', '\\r').replace('\n', '\\n')
            except IOError as e:
                response = 'ERROR: %s' % str(e)
            command.setReply(response)
        else:
            self.bad_command_handler(command)

    def _stowShutdown(self):
        """
        Perform a stowed shutdown
        """
        if 'shoe' not in self.connections:
            return
        try:
            self._send_command_to_shoe('SLR' + str(STOWSLIT))
            self._send_command_to_shoe('SLB' + str(STOWSLIT))
        except IOError as e:
            self.logger.debug('IOError during stowed shutdown')
        except Exception:
            self.logger.error('Error during stowed shutdown', exc_info=True)

    def TEMP_command_handler(self, command):
        """
        Get the current temperatures: B, R, Drive tower

        Responds with #,#,# where # is the temp or UNKNOWN
        """
        if self.connections['shoe'].rlock.acquire(False):
            try:
                response = self._send_command_to_shoe('TE')
            except IOError:
                response = 'UNKNOWN, UNKNOWN, UNKNOWN'
            finally:
                self.connections['shoe'].rlock.release()
        else:
            response = 'ERROR: Busy, try again'

        response = ','.join(['UNKNOWN' if '999.' in x else x for x in response.split(',')])
        command.setReply(response)

    def SLIT_command_handler(self, command):
        """
        Get/Set the active slit

        Command is of the form
        SLIT R|B {H180,S300,S80,L300,L180,L80,1,2,3,4,5,6}
        or
        SLIT R|B ? -> H180,S300,S80,L300,L180,L80

        If setting, the command instructs the shoe to move to the
        requested slit position, using the defined step positions for
        that slit. It is an error to set the slits when a move is in progress.
        If done the error '!ERROR: Can not set slits at this time.' will be generated

        If getting, respond in the form ERROR|INTERMEDIATE # # |MOVING # #|{H180,S300,S80,L300,L180,L80} # #.
        """
        if self._shoe_error is not None:
            command.setReply(self._shoe_error)
            self._shoe_error = None
            return
        if '?' in command.string:
            # Command the shoe to report the active slit
            resp = self._send_command_to_shoe('SGR' if 'r' in command.string.lower() else 'SGB')
            status, _, pos = resp.partition(' ')
            pos = pos.strip().replace('(', '').replace(')', '').replace(' ', '').replace(',', ' ')
            resp = SLIT_NAMES.get(status, status)+' '+pos
            command.setReply(resp)
            return
        else:
            # Vet the command
            command_parts = command.string.upper().replace(',', ' ').split(' ')
            slit = SLIT_NUMBERS.get(command_parts[2], command_parts[2])
            if not (len(command_parts) == 3 and command_parts[1] in ('R', 'B') and slit in ('1','2','3','4','5','6')):
                self.bad_command_handler(command)
                return
            id = command_parts[1]

        try:
            status = self._TS()
            if status['Shoe'+id] != 'connected':
                command.setReply('ERROR: %s shoe is %s' % (id, status['Shoe'+id]))
            elif 'MOVING' in status['Slit'+id]:
                command.setReply('ERROR: Move in progress')
            else:
                command.setReply('OK')
                self.startWorkerThread(command, 'MOVING', self.slit_mover, args=(id, slit),
                                       block=('SLITS_SLITPOS', 'SLITS_HARDHAT', 'SLITSRAW'))
        except IOError as e:
            command.setReply(e)

    def DOWNUP_command_handler(self, command):
        """
        Move the assembly down then back up.

        Command is of the form
        SLITS R|B

        It is an error to set the slits when a move is in progress.
        If done the error '!ERROR: Can not set slits at this time. will be generated.'
        """
        if self._shoe_error is not None:
            command.setReply(self._shoe_error)
            self._shoe_error = None
            return
        # Vet the command
        command_parts = command.string.upper().replace(',', ' ').split(' ')
        if not (len(command_parts) == 2 and command_parts[1] in ('R', 'B')):
            self.bad_command_handler(command)
            return
        _, id = command_parts

        try:
            status = self._TS()
            if status['Shoe'+id] != 'connected':
                command.setReply('ERROR: %s shoe is %s' % (id, status['Shoe'+id]))
            elif 'MOVING' in status['Slit'+id]:
                command.setReply('ERROR: Move in progress')
            else:
                try:
                    self._send_command_to_shoe('DU' + id)
                    resp = 'OK'
                except ShoeCommandNotAcknowledgedError:
                    resp = 'ERROR: Shoe rejected command, is a move in progress?'
                except IOError:
                    resp = 'ERROR: IFU shoe control tower offline'
                command.setReply(resp)
        except IOError as e:
            command.setReply(e)

    def commandIsQuery(self, command):
        """ Return true if the command is a query """
        try:
            return command.string.strip()[-1] == '?'
        except IndexError:
            return False

    def slit_mover(self, shoe, slit):
        """ shoe is R|B, slit a number string '1'-'6' """
        # Command the shoe
        shoe = shoe.upper()
        final_state = ''
        # with self.connections['shoe'].rlock:
        try:
            self._send_command_to_shoe('SL' + shoe + slit)
            resp = 'OK'
        except ShoeCommandNotAcknowledgedError:
            resp = 'ERROR: Shoe rejected command, is a move in progress?'
        except IOError:
            resp = 'ERROR: IFU shoe control tower offline'

        if resp != 'OK':
            self.returnFromWorkerThread('SLITS', finalState=resp)
            return
        else:
            self.returnFromWorkerThread('SLITS')

    def HARDHAT_command_handler(self, command):
        """Return engineering status of shoes at a glance
        arg shoe, R|B
        returns 6 numbers  pipe_pos  err tol  height_pos  err tol  OR ERROR: xxxxx
        """
        # Vet the command
        if self._shoe_error is not None:
            command.setReply(self._shoe_error)
            self._shoe_error = None
            return
        command_parts = command.string.lower().split(' ')
        if len(command_parts) < 2 or command_parts[1] not in ('b', 'r'):
            self.bad_command_handler(command)
            return

        id = command_parts[1]

        try:
            x = self._TS()

            if x['Shoe'+id.upper()] != 'connected':
                response = 'U U U'
            else:
                ppos = x['Pipe'+id.upper()]
                hpos = x['Height' + id.upper()]
                ptol, htol = x['tol_'+id]
                ppose, hpose = x['pos_err_'+id]
                response = '{} {} {} {} {} {}'.format(ppos, ppose, ptol, hpos, hpose, htol)

        except IOError:
            response = 'ERROR: IFU shoe control tower offline'

        command.setReply(response)

    def _TS(self):
        with self.connections['shoe'].rlock:
            self.connections['shoe'].sendMessageBlocking('TS')
            TS_LINES=47
            l = [self.connections['shoe'].receiveMessageBlocking() for _ in range(TS_LINES)]
        response = '\n'.join(l)
        try:
            return parseTS_jrk(response)
        except Exception:
            self.logger.error('Failed to parse {}.\n\n'.format(response), exc_info=True)

    def SLITPOS_command_handler(self, command):
        """
        Retrieve or set the position of a slit up/down/pipe location

        This command has 4 arguments:
            - shoe, R|B
            - place, up, down, pipe
            - slit 1-6, * (not for setting)
            - value or a question mark.

        The set position only affects subsequent moves.
        """
        if self._shoe_error is not None:
            command.setReply(self._shoe_error)
            self._shoe_error = None
            return
        # Vet the command
        command_parts = command.string.lower().split(' ')
        if len(command_parts) < 4:
            self.bad_command_handler(command)
            return
        elif len(command_parts) < 5:
            id, place, pos = command_parts[1:4]
            slit='*'
        else:
            id, place, slit, pos = command_parts[1:5]

        if (id not in ('b', 'r') or place not in ('pipe', 'up', 'down') or
            slit not in ('1','2','3','4','5','6', '*') or not ('?' in pos or longTest(pos))):
            self.bad_command_handler(command)
            return

        if '?' in pos:  # Get the step position of the slit
            try:
                x = self._TS()
                pos = x[place+'_pos_'+id]
                response = ' '.join(map(str,pos)) if slit == '*' else str(pos[int(slit)-1])
            except IOError:
                response = 'ERROR: IFU shoe control tower offline'
        else:  #if setting
            if slit == '*':
                self.bad_command_handler(command)
                return
            try:
                base = ('SS' + id) if place == 'pipe' else ('HS' + id + place[0].upper())
                self._send_command_to_shoe(base + slit + pos)
                response = 'OK'
            except ShoeCommandNotAcknowledgedError:
                response = 'ERROR: Shoe controller rejected command, is a move in progress?'
            except IOError:
                response = 'ERROR: IFU shoe control tower offline'

        command.setReply(response)


if __name__ == '__main__':
    agent = IFUShoeAgent()
    agent.main()
