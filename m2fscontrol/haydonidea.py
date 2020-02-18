import logging
from logging import getLogger
import selectedconnection as SelectedConnection
import time
import threading
from collections import namedtuple


"""SOME VERY EARLY NOTES
P28H41-12-A01
0.18 MAX
.001"/step
200step/rev
250,000 rad/sec2 39789 rev/s2 7958 in/s2 MAX
"""


# Contact HK: this seems to remain true even after a reset command to the Idea if the programs on the idea drive
# include an idle loop, getting rid of the idle loop fixed. I think the issue is that the reset command was
# silently ignored given that a program was running.
"reset appears not to work if a program is running"
'cant get the drive current'
"E175,0,50' doesn't stop the effing thing"

# Without power the drive opens a serial connection but just stops responding. No IO error
# is raised.


#~16kHz max toggle rate

#2000 count/rev encoder
#steps are in microsteps
#0.180mA ABSOLUTE MAX
#.001"/fullstep
#200step/rev

#a 1" relative test move
#I64000,48000,0,0,960000,960000,175,0,175,175,300,64

BAUD = 57600

IFU_DEVICE_MAP = {'lsb': '/dev/occulterLR', 'msb': '/dev/occulterMR', 'hsb': '/dev/occulterHR',
                  'mac1': '/dev/tty.usbserial-AL04HIOL', 'mac2': '/dev/tty.usbserial-AL04HJ3G',
                  'mac': '/dev/tty.usbserial-AL04HIOL'}

logger = getLogger(__name__)
HK_TIMEOUT = 1
ENCODER_CONFIG = (16, 0, 2000)  #16 64th steps of error allowed (16/64/200*.1" in ~3um)



# Bit 8-0
ERRORBITS = ('Over Speed', 'Bad Checksum', 'Current Limit', 'Loop Overflow', 'Int Queue Full', 'Encoder Error',
             'Temperature', 'Stack Overflow', 'Stack Underflow')

# speed must be in units of 1/64 steps  (0.001/64 inches/64thstep)
IN_PER_64THSTEP = .001 / 64
MAX_TRAVEL = int(2.6/IN_PER_64THSTEP)
HARD_LIMITS = (0, int(2.6/IN_PER_64THSTEP))

MAX_POSITION = 2.6 #TODO note units throughout
MIN_POSITION = -2.6  # Account for a bad 0
MIN_SPEED = .1  # 1 full step / second
MAX_SPEED = 1.6  #in/s

# Probably in 64th/s^2, motor allows 39789 rev/s2 7958 in/s2 MAX
MAX_ACCEL = MAX_DECEL = 16777215  # 0 forces default drive value, driver supports 0, 500-16777215 (~1300rev/s^2)
DEFAULT_ACCEL = 960000
DEFAULT_DECEL = 960000
CALIBRATION_MAX_TIME = 10  # seconds

MoveInfo = namedtuple('MoveInfo', ('start_time', 'duration'))

def movetime(distance, speed, accel, decel):
    speed = float(abs(speed))
    accel = float(abs(accel))
    decel = float(abs(decel))
    distance = float(abs(distance))
    return speed/accel/2 + speed/decel/2 + distance/speed

class IdeaIO(object):
    def __init__(self, byte):
        self.byte = int(byte)

    def __str__(self):
        return '0b{:08b}'.format(self.byte)

    @property
    def inputs(self):
        """NC NC NC Home"""
        self.byte & 0b00001111

    @property
    def outputs(self):
        """Calibrated err err booted"""
        self.byte & 0b11110000

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
        """ error codes are 1-3, 3=Sensorfail 1&2 not presently used """
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
    def __init__(self, executing, faults, io, encoder, moving, position, position_error):

        self.encoder = encoder
        self.program_running = executing
        self.faults = faults
        self.io = io
        self.moving = moving
        self.position = position
        self.position_error = position_error

    @property
    def calibrated(self):
        return self.io.calibrated

    @property
    def errorPresent(self):
        return self.faults.faultPresent or self.io.errcode

    @property
    def position_error_str(self):
        """Positve position_error indicates overshoot"""
        return '{:.1f}um ({})'.format(self.position_error*IN_PER_64THSTEP*1000, self.position_error)

    @property
    def faultString(self):
        """
        Returns a string of the form 0bXXXXXXXX0bXX. The first 8 bits correspond to the
        drive error codes 'Over Speed', 'Bad Checksum', 'Current Limit', 'Loop Overflow', 'Int Queue Full', 'Encoder Error',
             'Temperature', 'Stack Overflow', 'Stack Underflow'; i.e. 0b1... would indicate 'Over Speed'.
        The last 2 bits indicate a custom error code 1-3 (see IdeaIO.errcode) 3 indicates a sensor fail.
        """
        return '0b{:08b}0b{:02b}'.format(self.faults.byte, self.io.errcode)

class IdeaDrive(SelectedConnection.SelectedSerial):
    def __init__(self, ifu='Not Specified', port=None, preventstall=True):

        self.errorFlags = {}
        logger.name = 'Occulter' + ifu
        dev = port if port is not None else IFU_DEVICE_MAP[ifu]
        # Perform superclass initialization, note we implement the _postConnect hook , see below
        SelectedConnection.SelectedSerial.__init__(self, dev, BAUD, timeout=HK_TIMEOUT,
                                                   default_message_received_callback=self._unsolicited_message_handler)
        # Override the default message terminator for consistency.
        self.messageTerminator = '\r'
        self.commanded_position = None

        self.move_info = None
        self.prevent_stall = preventstall
        self.prevented_hammerstall = False
        self._antistall_thread = threading.Thread(target=self._antistall_main, name='Stall Prevention')#, args=args, kwargs=kwargs)
        self._antistall_thread.daemon = True
        self._antistall_thread.start()

    def _unsolicited_message_handler(self, message_source, message):
        """ Handle any unexpected messages from the drive - > log a warning. """
        logger.warning("Got unexpected, unsolicited message '%s'" % message)

    def _antistall_main(self):
        while True:
            time.sleep(.2)
            if not self.prevent_stall:
                continue
            with self.rlock:  # ensure atomicity
                if not self.isOpen() or self.move_info is None: #TODO verify that ANY movement command including raw sets move_info
                    continue
                try:
                    elapsed = time.time()-self.move_info.start_time
                    if (elapsed-.5) > max(self.move_info.duration, 1) and self.moving:
                        # The .5 and max(x, 1) are to allow for a bit of slop and a minimum execution time
                        msg = ('Detected potential hammerstall ({:.1f} s elapsed, {:.1f} s expected) '
                               'aborting move and restarting drive.')
                        getLogger(__name__).critical(msg.format(elapsed, self.move_info.duration))
                        self.abort()
                        self.reset()
                        self.move_info = None
                        self.prevented_hammerstall = True
                except IOError:
                    pass
#After turning off power
# OcculterNot Specified:DEBUG: Sending o to HK
# lib.SelectedConnection:DEBUG: Attempted write 'o\r', wrote 'o\r' to /dev/tty.usbserial-AL04HIOL@57600 @ 1573348235.01
# lib.SelectedConnection:DEBUG: BlockingReceive got: ''
# lib.SelectedConnection:WARNING: Blocking receive on /dev/tty.usbserial-AL04HIOL@57600 timed out
# lib.SelectedConnection:DEBUG: BlockingReceive got: ''
# lib.SelectedConnection:WARNING: Blocking receive on /dev/tty.usbserial-AL04HIOL@57600 timed out
# OcculterNot Specified:ERROR: HK did not adhere to protocol 'o' got ''
# Traceback (most recent call last):
#   File "/Users/one/Dropbox/M2FS-Dropbox/M2FS-Control/lib/haydonidea.py", line 230, in send_command_to_hk
#     return response.split('`')[1].strip()[1:]
# IndexError: list index out of range

    @property
    def programRunning(self):
        # # See if program is running
        # 'r'-> yes or no "`rYES[cr]`r#[cr]" or "`rNO[cr]`r#[cr]"
        return 'YES' in self.send_command_to_hk('r')

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
        getLogger(__name__).debug('Sending {} to HK'.format(command_string))
        self.sendMessageBlocking(command_string, connect=True)  #TODO think about if we should or shouldn't connect and

        if not self.command_has_response(command_string):
            return ''  #NB this is also the response we would expect from a powered down HK, gross
        else:
            # Response will be nothing or  "`<cmdkey><ascii>\r`<cmdkey>#\r", NB that receiveMessageBlocking strips the
            # terminator so a merged response would look like "`<cmdkey><ascii>`<cmdkey>#"
            # Need to do a blocking receive on \r twice
            response = self.receiveMessageBlocking() + self.receiveMessageBlocking()
            if not response:
                if command_string == 'b':  # Encoder command can return something OR nothing, UGH!
                    logger.info('HK encoder query did not get response, this sometimes happens')
                    return ''
                else:
                    e = 'HK did not respond to "{}", is it powered?'.format(command_string)
                    self.handle_error(e)
                    raise SelectedConnection.ReadError(e)
            try:
                return response.split('`')[1].strip()[1:]
            except Exception:
                e = "HK did not adhere to protocol '%s' got '%s'" % (command_string, response)
                #logger.error(msg, exc_info=True)
                self.handle_error(e)
                raise SelectedConnection.ReadError(e)
                # raise IOError('ERROR: '+msg)  #Give up, something is wrong!

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
        return self.io.calibrated

    def move_to(self, position, speed=None, accel=None, decel=None, relative=False, steps=True):
        """
        Move to a position.

        Position and speed are in units of steps or inches as per steps=True|False
        speed is in units of in/s
        accel & decel are always in full steps (64x a position step).

        Calibration will be performed if uncalibrated and relative is not True
        """
        if not self.calibrated and not relative:
            self.calibrate()

        if speed is None:
            speed = .75  # in/s

        speed = max(min(speed, MAX_SPEED), MIN_SPEED)
        speed = int(round(speed / IN_PER_64THSTEP))

        if not steps:
            position = int(round(position / IN_PER_64THSTEP))

        position = max(min(position, MAX_TRAVEL), -MAX_TRAVEL)

        start_speed = end_speed = 0
        run_current = accel_current = decel_current = 175  # 180 MAX
        hold_current = 0
        delay_time = 300
        stepping = 64
        accel = DEFAULT_ACCEL if accel is None else int(round(max(min(accel, MAX_ACCEL), 0)))
        decel = DEFAULT_DECEL if decel is None else int(round(max(min(decel, MAX_DECEL), 0)))
        params = [position, speed, start_speed, end_speed, accel, decel, run_current, hold_current, accel_current,
                  decel_current, delay_time, stepping]

        if self.commanded_position is None:
            self.commanded_position = self.position(steps=True)
            distance = abs(position-self.commanded_position) if not relative else position
        else:
            distance = abs(position - self.position(steps=True)) if not relative else position

        cmd = 'I' if relative else 'M'
        with self.rlock:
            self.send_command_to_hk(cmd + ','.join(map(str, map(int, params))))
            self.commanded_position = position if not relative else position + self.commanded_position
            self.move_info = MoveInfo(start_time=time.time(), duration=movetime(distance, speed, accel, decel))

    def position_error(self, steps=True):
        if self.commanded_position is None:
            self.commanded_position = self.position(steps=True)
        err = self.position()-self.commanded_position
        return err if steps else err*IN_PER_64THSTEP

    def position(self, steps=True):
        pos = int(self.send_command_to_hk('l'))
        return pos if steps else pos*IN_PER_64THSTEP

    def calibrate(self, nosleep=False):
        with self.rlock:
            self.send_command_to_hk('mCalibrate_')
            self.sendMessageBlocking('mCalibrate_')
            self.commanded_position = 0
            self.move_info = MoveInfo(start_time=time.time(), duration=CALIBRATION_MAX_TIME)
        if not nosleep:
            timeout = CALIBRATION_MAX_TIME
            while not self.calibrated and timeout > 0:
                time.sleep(.2)
                timeout -= .2
            state = self.state()
            if not state.calibrated:
                raise RuntimeError('ERROR: Calibration Failed ({})'.format(self.state().faultString))

    # def config_encoder(self):
    #     DeadBand, StallHunts, Destination, Priority, encoder_res, motor_res
    #     params = [DeadBand, StallHunts, Destination, Priority, encoder_res, motor_res]
    #     self.send_command_to_hk(cmd + ','.join(map(int, params)))

    def encoder_config(self):
        #This appears to return nothing if the encoder is not configured
        enc = self.send_command_to_hk('b')  # "`b[deadband],[stallhunts],[lines/rev][cr]`b#[cr]"
        if not enc:
            return 0, 0, 0
        return tuple(map(int, enc.split(',')))

    def stop(self):
        """
        Stop the motor. Should probably use abort instead

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
        This also causes a move, should use abort instead

        Seems to assume that the internal Idea drive state has been issued a move command and its stopping TO there
        """
        decel_current = 175
        delay_time = 300
        hold_current = 0
        params = [decel_current, hold_current, delay_time]
        self.send_command_to_hk('E' + ','.join(map(str, map(int, params))))

    def abort(self):
        """ Command drive to abort """
        self.send_command_to_hk('A')

    @property
    def faults(self):
        s = self.send_command_to_hk('f')
        try:
            int(s)
        except ValueError:
            raise IOError(s)
        return IdeaFaults(s)

    def reset(self):
        self.send_command_to_hk('R')

    def state(self):
        pos = self.position()
        io = self.io
        perr = pos - self.commanded_position if self.commanded_position is not None and io.calibrated else 0
        return IdeaState(self.programRunning, self.faults, io, self.encoder_config(), self.moving, pos, perr)


if __name__ == '__main__':
    logging.basicConfig()
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    m = self = IdeaDrive('mac')
