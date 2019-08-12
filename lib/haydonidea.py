import serial
import logging
from logging import getLogger
import lib.SelectedConnection as SelectedConnection
import time

"reset appears not to work if a program is running"
'cant get the drive current'

BAUD = 57600

IFU_DEVICE_MAP = {'lsb': '/dev/occulterLR', 'msb': '/dev/occulterMR', 'hsb': '/dev/occulterHR',
                  'mac': '/dev/tty.usbserial-AL04HIOL'}

logger = getLogger(__name__)
HK_TIMEOUT = 1
ENCODER_CONFIG = (16,0,2000)  #16 64th steps of error allowed (16/64/200*.1" in)

# Bit 8-0
ERRORBITS = ('Over Speed', 'Bad Checksum', 'Current Limit', 'Loop Overflow', 'Int Queue Full', 'Encoder Error',
             'Temperature', 'Stack Overflow', 'Stack Underflow')

# speed must be in units of 1/64 steps  (0.001/64 inches/64thstep)
IN_PER_64THSTEP = .001 / 64
MAX_POSITION = 2.6
MIN_POSITION = -2.6  # Account for a bad 0
MIN_SPEED = .1  # 1 full step / second
MAX_SPEED = 1.6

CALIBRATION_MAX_TIME = 10  # seconds


class IdeaIO(object):
    def __init__(self, byte):
        self.byte = int(byte)

    def __str__(self):
        return '0b{:08b}'.format(self.byte)

    @property
    def home_tripped(self):
        return not bool(self.byte & 0x01)

    @property
    def booted(self):
        return bool(self.byte & 0x10)

    @property
    def calibrated(self):
        return bool(self.byte & 0x80)

    @property
    def errcode(self):
        return (self.byte & 0x60) >> 5


class IdeaFaults(object):
    def __init__(self, byte):
        self.byte = int(byte)

    def __str__(self):
        return ', '.join([b for i, b in enumerate(ERRORBITS) if self.byte & (1 << i)])

    @property
    def faultPresent(self):
        return self.byte != 0


class IdeaState(object):
    def __init__(self, executing, faults, io, encoder, moving, position):
        self.encoder = encoder
        self.program_running = executing
        self.faults = faults
        self.io = io
        self.moving = moving
        self.position = position

    @property
    def calibrated(self):
        return self.io.calibrated

    @property
    def errorPresent(self):
        return self.faults.faultPresent or self.io.errcode

    def faultString(self):
        return bin(self.faults.byte) + bin(self.io.errcode)

class IdeaDrive(SelectedConnection.SelectedSerial):
    def __init__(self, ifu='Not Specified', port=None):

        self.errorFlags = {}
        logger.name = 'Occulter' + ifu
        dev = port if port is not None else IFU_DEVICE_MAP[ifu]
        # Perform superclass initialization, note we implement the _postConnect hook , see below
        SelectedConnection.SelectedSerial.__init__(self, dev, BAUD, timeout=HK_TIMEOUT,
                                                   default_message_received_callback=self._unsolicited_message_handler)
        # Override the default message terminator for consistency.
        self.messageTerminator = '\r'
        self.commanded_position = None

    def _unsolicited_message_handler(self, message_source, message):
        """ Handle any unexpected messages from the drive - > log a warning. """
        logger.warning("Got unexpected, unsolicited message '%s'" % message)

    @property
    def programRunning(self):
        # # See if program is running
        # 'r'-> yes or no "`rYES[cr]`r#[cr]" or "`rNO[cr]`r#[cr]"
        return 'YES' in self.send_command_to_hk('r')

    # def _postConnect(self):
    #     """
    #     Implement the post-connect hook
    #
    #     With the hk we need to do make sure the encoder is online and sync the calibration state
    #     1) Get currently executing program.
    #     2) Verify the encoder.
    #     """
    #     pass
    #     # don't use '
    #
    #     self.sendMessageBlocking('r')
    #     response = self.receiveMessageBlocking()
    #     self.receiveMessageBlocking()  # discard the garbage from the Idea protocol
    #
    #     if 'YES' not in response:
    #         raise SelectedConnection.ConnectError("{}: HK drive did not start properly.".format(self.port))
    #     # state = self.state()
    #     # if not state.encoder == ENCODER_CONFIG:
    #     #     getLogger(__name__).error('Encoder state "{}", expected "{}".'.format(state['encoder'], ENCODER_CONFIG))
    #     #     raise IOError("{}: HK drive did not start properly.".format(self.port))

    def command_has_response(self, cmd):
        return cmd[0] in 'cPlkbrfv:joNK@'

    def send_command_to_hk(self, command_string):
        """
        Send a command string to the idea drive, wait for immediate response if command has response

        Silently ignore an empty command.

        The command_string must not include spurious \r or be otherwise pathological.

        Drive does not necessarily acknowledge commands
        """
        command_string = command_string.strip('\r')  # Make sure no unnecessary \r
        if not command_string:  # No command, return
            return ''

        if '\r' in command_string:
            raise IOError('ERROR: Commands to HK may not contain the carriage return character.')
        if command_string.startswith('@'):
            raise IOError('ERROR: Download of programs not supported')

        # Send the command, do not catch the WriteError as they must bubble up
        self.sendMessageBlocking(command_string, connect=False)

        if not self.command_has_response(command_string):
            return ''
        else:
            # Response will be nothing or  "`<cmdkey><ascii>\r`<cmdkey>#\r", NB that receiveMessageBlocking strips the
            # terminator so a merged response would look like "`<cmdkey><ascii>`<cmdkey>#"
            # Need to do a blocking receive on \r twice
            response = self.receiveMessageBlocking() + self.receiveMessageBlocking()
            try:
                return response.split('`')[1].strip()[1:]
            except Exception as e:
                msg = "HK did not adhere to protocol '%s' got '%s'" % (command_string, response)
                logger.error(msg, exc_info=True)
                return 'ERROR: '+msg

    def abort(self):
        self.send_command_to_hk('A')

    @property
    def io(self):
        return IdeaIO(self.send_command_to_hk(':'))  # 8 bit number O4-1 I4-1 "`:31\r`:#\r"

    @property
    def moving(self):
        return 'YES' in self.send_command_to_hk('o')  # "`oYES[cr]`o#[cr]" or "`oNO[cr]`o#[cr]"

    @property
    def calibrated(self):
        #TODO this seems to remain true even after a reset command to the Idea if the programs on the idea drive
        # include an idle loop, getting rid of the idle loop fixed. I think the issue is that the reset command was
        # silently ignored given that a program was running.
        return self.io.calibrated

    def move_to(self, position, speed=.75, accel=None, decel=None, relative=False):
        """ Position in inches, speed in in per s, accel & decel in full steps"""

        if not self.calibrated:
            self.calibrate()

        speed = int(round(max(min(speed, MAX_SPEED), MIN_SPEED) / IN_PER_64THSTEP))
        position = int(round(max(min(position, MAX_POSITION), MIN_POSITION) / IN_PER_64THSTEP))

        start_speed = end_speed = 0
        run_current = accel_current = decel_current = 175  # 180 MAX
        hold_current = 0
        delay_time = 300
        stepping = 64
        accel = 0 if accel is None else accel  # TODO add minmax
        decel = 0 if decel is None else decel
        params = [position, speed, start_speed, end_speed, accel, decel, run_current, hold_current, accel_current,
                  decel_current, delay_time, stepping]

        if self.commanded_position is None:
            self.commanded_position = self.position(steps=True)

        self.commanded_position = position if not relative else position + self.commanded_position
        cmd = 'I' if relative else 'M'
        self.send_command_to_hk(cmd + ','.join(map(str, map(int, params))))

    def position_error(self):
        """ in inches"""
        if self.commanded_position is None:
            self.commanded_position = self.position()
        return (self.position(steps=True)-self.commanded_position)*IN_PER_64THSTEP

    def position(self, steps=False):
        pos = int(self.send_command_to_hk('l'))
        return pos if steps else pos*IN_PER_64THSTEP

    def calibrate(self, nosleep=False):
        """ TODO flesh out exceptions and make not conditional on nosleep arg"""
        self.sendMessageBlocking('mCalibrate_')
        if not nosleep:
            time.sleep(CALIBRATION_MAX_TIME)
            state = self.state()
            if not state.calibrated:
                raise RuntimeError

    # def config_encoder(self):
    #     DeadBand, StallHunts, Destination, Priority, encoder_res, motor_res
    #     params = [DeadBand, StallHunts, Destination, Priority, encoder_res, motor_res]
    #     self.send_command_to_hk(cmd + ','.join(map(int, params)))

    def encoder_config(self):
        #This appears to return nothing if the encoder is not
        enc = self.send_command_to_hk('b')  # "`b[deadband],[stallhunts],[lines/rev][cr]`b#[cr]"
        if not enc:
            return 0,0,0
        return tuple(map(int, enc.split(',')))

    def stop(self):
        """
        Stop the motor.

        This causes an overextended pulsing shaft to retract fully and pulse, wtf
        This causes a stopped shaft to slowly retract, wtf
        Seems to assume that the internal Idea drive state has been issued a move command and its stopping TO there
        """
        end_speed = 0
        run_current = decel_current = 175  # 180 MAX
        hold_current = 0
        delay_time = 300
        stepping = 64
        decel = 0
        params = [end_speed, decel, run_current, decel_current, hold_current, delay_time, stepping]
        self.send_command_to_hk('H' + ','.join(map(str, map(int, params))))

    def estop(self):
        """
        This also causes a move

        Seems to assume that the internal Idea drive state has been issued a move command and its stopping TO there
        """
        decel_current = 175
        delay_time = 300
        hold_current = 0
        params = [decel_current, hold_current, delay_time]
        self.send_command_to_hk('E' + ','.join(map(str, map(int, params))))

    @property
    def faults(self):
        return IdeaFaults(self.send_command_to_hk('f'))

    def reset(self):
        self.send_command_to_hk('R')

    def state(self):
        return IdeaState(self.programRunning, self.faults, self.io, self.encoder_config(),
                         self.moving, self.position())


if __name__ == '__main__':
    logging.basicConfig()
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    m = self = IdeaDrive('mac')

