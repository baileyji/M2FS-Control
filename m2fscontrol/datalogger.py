import time, select

import redis
from serial import Serial, SerialException
from datetime import datetime, timedelta
from construct import UBInt32, StrictRepeater, LFloat32, SLInt16, ULInt32
import numpy as np
import threading
import logging
import logging.handlers
# from m2fsConfig import M2FSConfig
from redis import RedisError

SELECT_TIMEOUT = 5

SYS_FILE_OK = 0x01
SYS_SD_OK = 0x02
SYS_RTC_OK = 0x04
SYS_TEMP_OK = 0x08
SYS_ADXL_OK = 0x10
SYS_HEADER_OK = 0x20
SYS_HEADER_NEW = 0x40

# Temp sensor quantity and order
N_TEMP_SENSORS = 3

ECHELLE_INDEX_B = 2
PRISM_INDEX_B = 1
LORES_INDEX_B = 0

ECHELLE_INDEX_R = 1
PRISM_INDEX_R = 2
LORES_INDEX_R = 0

ECHELLE_OFFSET_B = -0.3125
PRISM_OFFSET_B = -0.125
LORES_OFFSET_B = -0.0625

ECHELLE_OFFSET_R = -0.125
PRISM_OFFSET_R = -0.125
LORES_OFFSET_R = -0.0625

# Lengths of the message parts in bytes
TEMPERATURE_BYTES = 4
ACCELERATION_BYTES = 2
TIMESTAMP_LENGTH = 8
ADXL_FIFO_LENGTH = 32
NUM_AXES = 3
ACCELS_TO_GEES = 0.00390625
ACCEL_RECORD_LENGTH = TIMESTAMP_LENGTH + NUM_AXES * ACCELERATION_BYTES * ADXL_FIFO_LENGTH
TEMP_RECORD_LENGTH = TIMESTAMP_LENGTH + TEMPERATURE_BYTES * N_TEMP_SENSORS
COMPOSITE_RECORD_LENGTH = ACCEL_RECORD_LENGTH + TEMP_RECORD_LENGTH - TIMESTAMP_LENGTH

# These are constructs which take the raw binary data for the accelerations or
# temps and parse them into lists of numbers
tempsParser = StrictRepeater(N_TEMP_SENSORS, LFloat32("temps")).parse
accelsParser = StrictRepeater(ADXL_FIFO_LENGTH * NUM_AXES, SLInt16("accel")).parse
unsigned32BitParser = ULInt32("foo").parse


def translateErrorByte(byteStr):
    err = int(byteStr, 16)
    errors = []
    if not SYS_FILE_OK & err:
        errors.append('Logfile Error')
    if not SYS_SD_OK & err:
        errors.append('SD Card Error')
    if not SYS_RTC_OK & err:
        errors.append('RTC Error')
    if not SYS_TEMP_OK & err:
        errors.append('Temp Error')
    if not SYS_ADXL_OK & err:
        errors.append('Accelerometer Error')
    if not SYS_HEADER_OK & err:
        errors.append('Header Error')
    if not SYS_HEADER_NEW & err:
        errors.append('Existing Header')
    else:
        errors.append('New Header')
    return 'Status: ' + ' '.join(errors)


class DataloggerConnection(Serial):
    """
    Datalogger Connection Class

    Wrapper for Serial which knows how to tell the datalogger the unixtime
    and grab a log message.
    """

    def __init__(self, device, side):
        """
        Wrap Serial initialization so we can instantite unpoened w/o problems
        This is fine, because it might be unplugged.
        """
        Serial.__init__(self, baudrate=115200, timeout=1)
        self.timeout = 1
        self.port = device
        if side != 'R' and side != 'B':
            raise ValueError('Side must be R or B')
        self.side = side
        try:
            self.open()
        except SerialException:
            pass

    def readLogData(self, parse=True):
        """
        Read one byte, then read the number of bytes specified in the first byte

        Return the read data
        """
        data = self.read(ord(self.read(1)))
        self.write('#')
        return data if not parse else self.fromDataloggerData(self.side, data)

    @staticmethod
    def fromDataloggerData(side, data):
        """
        Create a LoggerRecord from the raw data string from the datalogger

        The raw string consists of the data following the L and record length
        """
        # Parse the raw data
        if len(data) == COMPOSITE_RECORD_LENGTH:
            temps = tempsParser(data[0:4 * N_TEMP_SENSORS + 1])
            accels = accelsParser(data[0:-8])
        elif len(data) == ACCEL_RECORD_LENGTH:
            temps = None
            accels = accelsParser(data[0:-8])
        elif len(data) == TEMP_RECORD_LENGTH:
            temps = tempsParser(data[0:-8])
            accels = None
        else:
            raise ValueError("Malformed Record (%i bytes)" % len(data))
        unixtime = float(unsigned32BitParser(data[-8:-4]))
        unixtime += float(unsigned32BitParser(data[-4:]) % 1000) / 1000
        # Convert the raw accelerometer data to Gs
        if accels is not None:
            accels = ACCELS_TO_GEES * np.array(accels).reshape([32, 3])
        # Extract the sensor values
        if temps is not None:
            if side == 'R':
                echelleTemp = temps[ECHELLE_INDEX_R] + ECHELLE_OFFSET_R
                prismTemp = temps[PRISM_INDEX_R] + PRISM_OFFSET_R
                loresTemp = temps[LORES_INDEX_R] + LORES_OFFSET_R
            else:
                echelleTemp = temps[ECHELLE_INDEX_B] + ECHELLE_OFFSET_B
                prismTemp = temps[PRISM_INDEX_B] + PRISM_OFFSET_B
                loresTemp = temps[LORES_INDEX_B] + LORES_OFFSET_B
        else:
            echelleTemp = None
            prismTemp = None
            loresTemp = None
        # Generate the logger record
        return dict(time=unixtime, echelle=echelleTemp, prism=prismTemp, accels=accels, lores=loresTemp)

    def telltime(self):
        """
        Send the current unix time to the datalogger as a 32bit big endian

        For some reason I can't identify the null bytes are necessary for the
        message to be received properly.
        """
        s = 't' + UBInt32("f").build(int(time.mktime(datetime.utcnow().timetuple())))

        self.write(s[0])
        self.write('\x00' + s[1])
        self.write('\x00' + s[2])
        self.write('\x00' + s[3])
        self.write('\x00' + s[4])

        hextime = '0x' + (4 * '{:02x}').format(*map(ord, s[1:]))
        timemsg = 'Sending time as {}'.format(hextime)
        logging.getLogger(__name__+self.side).debug(timemsg)

    def getByte(self, timeout):
        """
        Return the next byte received if a byte received within timeout

        Returns '' and closes connection if there is an IO error
        """
        reader, junk, error = select.select([self], [], [self], timeout)
        if error:
            self.close()
            return ''
        if reader:
            try:
                return self.read(1)
            except SerialException:
                return ''
            except IOError:
                return ''
        return ''


class DataloggerListener(threading.Thread):
    """
    This is a thread class that handles communication with a datalogger and
    yields the reported data via a queue.
    """

    def __init__(self, side, device, redis_ts):
        """
        Start a new thread to capture temperature and accelerometer data from
        an M2FS datalogger on device. Place data into the Queue passed in Queue.
        """
        if side != 'R' and side != 'B':
            raise Exception('Side must be R or B')
        threading.Thread.__init__(self)
        self.redis_ts = redis_ts
        self.daemon = True
        self.side = side
        self.datalogger = DataloggerConnection(device, side)
        self.logger = logging.getLogger(__name__+side)
        self.logger.info("Listener started")

    def run(self):
        """

        It runs, listening for #, E, L, or t from the datalogger and acting
        accordingly.
        E) An \n delimited error message follows, recieve it
        L) A log record follows, recieve it, acknowledge it, and create a
            DataloggerRecord from it
        #) A \n delimited dubug message follows, receive it
        t) The datalogger is requesting the current time, send it

        As error, log, or debug messages are received, they are placed into the
        queue as the second element in a tuple, the first identifing the
        contents: 'record', 'error', 'debug'

        If the datalogger is disconnected, keep trying to connect
        """
        while True:
            try:
                if not self.datalogger.isOpen():
                    self.logger.debug("Trying to open")
                    try:
                        self.datalogger.open()
                        self.logger.info("Connection Opened")
                    except SerialException:
                        time.sleep(1)
                else:
                    byte = self.datalogger.getByte(SELECT_TIMEOUT)
                    if byte == 't':
                        self.datalogger.telltime()
                        self.logger.info('Handled time query')
                    elif byte == 'L':
                        try:
                            logdata = self.datalogger.readLogData(parse=True)
                            self.logger.debug(logdata)
                            rec = {k + self.side: logdata[k] for k in ('echelle', 'prism', 'lores')
                                   if logdata[k] is not None}
                            dl_t = datetime.utcfromtimestamp(logdata['time'])
                            t = datetime.utcnow()
                            for k, v in rec.items():
                                try:
                                    series = getattr(self.redis_ts, k.lower())
                                    series.add({'': v}, id=t)
                                except redis.ResponseError as e:
                                    if 'XADD' in str(e):
                                        try:
                                            top = getattr(self.redis_ts, k.lower())[t - timedelta(minutes=1.1):][-1].timestamp
                                        except:
                                            top=None
                                        self.logger.error('{}. {} @ t={}. Stream top: {} DLt: {}'.format(e, k, t, top, dl_t))
                                    else:
                                        raise
                        except ValueError as e:
                            self.logger.error(str(e))
                        except redis.ResponseError as e:
                            self.logger.error('Redis error {} while logging {} at t={}'.format(e, rec, t))
                        except RedisError as e:
                            self.logger.error(e, exc_info=True)
                    elif byte == 'E':
                        msg = self.datalogger.readline()
                        if 'Fatal Error' in msg:
                            self.logger.info(translateErrorByte(msg.split(': ')[1]))
                        self.logger.error(msg)
                    elif byte == '#':
                        msg = self.datalogger.readline()
                        # older version had a # in front of the error String
                        if 'Fatal Error' in msg:
                            self.logger.info(translateErrorByte(msg.split(': ')[1]))
                        self.logger.info(msg)
                        if 'PD' in msg:
                            self.logger.info('Logger powered down, closing serial')
                            self.datalogger.close()
                            time.sleep(1)
                    else:
                        pass
            except SerialException, e:
                self.logger.debug("%s" % str(e))
                time.sleep(1)
            except OSError, e:
                self.logger.debug("%s" % str(e))
                time.sleep(1)
            except IOError, e:
                self.logger.debug("%s" % str(e))
                time.sleep(1)
