#!/usr/bin/env python2.7
import time
from m2fscontrol.agent import Agent
from m2fscontrol.m2fsConfig import M2FSConfig
from m2fscontrol.utils import longTest
from m2fscontrol.shoe import ShoeSerial as _ShoeSerial, ShoeCommandNotAcknowledgedError


EXPECTED_FIBERSHOE_INO_VERSION = 'IFUshoe v1.3'
SHOE_AGENT_VERSION_STRING = 'IFU Shoe Agent v1.0'
SHOE_AGENT_VERSION_STRING_SHORT = SHOE_AGENT_VERSION_STRING.split()[-1]

SHOE_BOOT_TIME = .5
SHOE_SHUTDOWN_TIME = .25
MAX_SLIT_MOVE_TIME = 25
STOWSLIT = 1

# todo write files with shoe inserted color based on presence of temp sensors?

def parseTS(x):
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
    x = '\n'.join([l.strip() for l in x.split('\n') if
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
        res['pos_err'] = [int(x) for x in d['SL Delta'].split(',')]
        res['pos'] = [int(x.split()[0]) for x in d['Pos (live)'].split(',')]
        return res

    rd = parse_shoestat(rstat)
    bd = parse_shoestat(bstat)
    response = {}
    if 'R disconnected' in g:
        response['ShoeR'] = 'disconnected'
    elif 'R&B Swapped' in g:
        response['ShoeR'] = 'swapped'
    else:
        response['ShoeR'] = 'connected'

    if 'B disconnected' in g:
        response['ShoeB'] = 'disconnected'
    elif 'R&B Swapped' in g:
        response['ShoeB'] = 'swapped'
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
        response['debug_'+x.lower()] = d['debug']

    return response


class ShoeSerial(_ShoeSerial):
    def _implementationSpecificDisconnect(self):
        """ Disconnect the serial connection"""
        try:
            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except Exception:
            self.logger.error('Error on shoe serial disconnect: ', exc_info=True)
            pass


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
        self.connections['shoe'] = ShoeSerial(self.args.DEVICE, 115200, timeout=1)
        # Allow two connections so the datalogger agent can poll for temperature
        self.max_clients = 2
        self.command_handlers.update({
            # Send the command string directly to the shoe
            'SLITSRAW': self.RAW_command_handler,
            # Get/Set the active slit.
            'SLITS': self.SLITS_command_handler,
            # Get/Set the positions corresponding to a slit
            'SLITS_SLITPOS': self.SLITPOS_command_handler,
            # Get the temperature of the shoe
            'SLITS_TEMP': self.TEMP_command_handler})

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
        # No command, return
        if not command_string:
            return ''
        # Send the command(s)
        self.connections['shoe'].sendMessageBlocking(command_string)
        # Get the first byte, typically this will be it
        response = self.connections['shoe'].receiveMessageBlocking(nBytes=1)
        # 3 cases:, :, ?, or stuff followed by \r\n:
        # case 1, command succeeds but returns nothing, return
        if response == ':':
            return ''
        # command fails
        elif response == '?':
            raise ShoeCommandNotAcknowledgedError("ERROR: Shoe did not acknowledge command '%s' (%s)" %
                                                  (command_string, response))
        # command is returning something
        else:
            # do a blocking receive on \n
            response = response + self.connections['shoe'].receiveMessageBlocking()
            # ...and a single byte read to grab the :
            confByte = self.connections['shoe'].receiveMessageBlocking(nBytes=1)
            if confByte == ':':
                return response.strip()
            else:
                # Consider it a failure, but log it. Add the byte to the
                # response for logging
                response += confByte
                err = ("Shoe did not adhere to protocol. '%s' got '%s'" % (command_string, response))
                self.logger.warning(err)
                raise ShoeCommandNotAcknowledgedError('ERROR: %s' % err)

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
        #TODO
        """
        # Name & cookie
        status = {self.name + ' ' + SHOE_AGENT_VERSION_STRING_SHORT: self.cookie}
        try:
            status['Controller'] = 'Online'
            response = parseTS(self._send_command_to_shoe('TS').split(' '))
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
        return status.items()

    def RAW_command_handler(self, command):
        """
        Send a raw string to the shoe and wait for a response

        NB the PC command can generate more than 1024 bytes of data
        """
        arg = command.string.partition(' ')[2]
        if arg:
            try:
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
        self._send_command_to_shoe('SLR'+ str(STOWSLIT))
        self._send_command_to_shoe('SLB' + str(STOWSLIT))

        #TODO look at other agents for process

    #
    #       failmsg="Stowed shutdown of {} failed: {}"
    # wait here until the shoe connection is free. Any threads running
    # will then stall if they need the shoe, program will be unresponsive
    # to socket interface
    # self.connections['shoe'].rlock.acquire(blocking=True)

    def TEMP_command_handler(self, command):
        """
        Get the current shoe temperature

        Responds with the temp or UNKNOWN
        """
        if self.connections['shoe'].rlock.acquire(False):
            try:
                response = self._send_command_to_shoe('TE')
            except IOError as e:
                response = 'UNKNOWN UNKNOWN UNKNOWN'
            finally:
                self.connections['shoe'].rlock.release()
        else:
            response = 'ERROR: Busy, try again'
        command.setReply(response)

    def SLITS_command_handler(self, command):
        """
        Get/Set the active slit

        Command is of the form
        SLITS R|B {1-6}
        or
        SLITS R|B ?

        If setting, the command instructs the shoe to move to the
        requested slit position, using the defined step positions for
        that slit. It is an error to set the slits when a move is in progress.
        If done the error '!ERROR: Can not set slits at this time. will be generated.'

        If getting, respond in the form INTERMEDIATE|MOVING|{1-6}.
        """
        if '?' in command.string:
            # Command the shoe to report the active slit
            command.setReply(self._send_command_to_shoe('SGR' if 'r' in command.string.lower() else 'SGB'))
            return
        else:
            # Vet the command
            command_parts = command.string.upper().replace(',', ' ').split(' ')
            if not (len(command_parts) == 3 and command_parts[1] in ('R', 'B') and
                    command_parts[2] in ('1','2','3','4','5','6')):
                self.bad_command_handler(command)
                return
            _, id, slit = command_parts

        try:
            status = parseTS(self._send_command_to_shoe('TS'))
            if status['Shoe'+id] != 'connected':
                command.setReply('ERROR: %s shoe is %s'  % (id, status['Shoe'+id]))
            elif 'MOVING' in status['Slit'+id]:
                command.setReply('ERROR: Move in progress')
            else:
                command.setReply('OK')
                self.startWorkerThread(command, 'MOVING', self.slit_mover, args=(id, slit),
                                       block=('SLITS_SLITPOS', ))
        except IOError as e:
            command.setReply(e)

    def slit_mover(self, shoe, slit):
        """ shoe is R|B, slit a number string '1'-'6' """
        # Command the shoe
        shoe = shoe.upper()
        final_state = ''
        with self.connections['shoe'].rlock:
            cmd = 'SL' + shoe + slit
            resp = self._send_command_to_shoe(cmd)
            if resp != 'OK':
                self.returnFromWorkerThread('SLITS', finalState=resp)
                return
            self.logger.debug('sleeping with lock active')
            time.sleep(MAX_SLIT_MOVE_TIME)
            self.logger.debug('finished sleeping with lock active')

            #TODO now the question is did we get there
            pos = self._send_command_to_shoe('SG'+shoe)
            if pos != slit:
                final_state = 'ERROR: Did not attain requested slit'
        self.returnFromWorkerThread('SLITS', finalState=final_state)

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
        # Vet the command
        command_parts = command.string.lower().split(' ')
        if len(command_parts) < 5:
            self.bad_command_handler(command)
            return

        id, place, slit, pos = command_parts[1:5]
        if (id not in ('b', 'r') or place not in ('pipe', 'up', 'down') or
            slit not in ('1','2','3','4','5','6', '*') or not ('?' in pos or longTest(pos))):
            self.bad_command_handler(command)
            return

        if '?' in pos:  # Get the step position of the slit
            try:
                x = parseTS(self._send_command_to_shoe('TS').split(' '))
                pos = x[place+'_pos_'+id]
                response = ' '.join(pos) if slit == '*' else str(pos[int(slit)-1])
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
