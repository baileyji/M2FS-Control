import pymodbus
from pymodbus.pdu import ModbusRequest
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pymodbus.transaction import ModbusRtuFramer
from pymodbus.exceptions import ModbusIOException, ConnectionException, ModbusException  #last is the parent
from bitstring import Bits, BitArray
import logging, time, threading, select


#TODO (general)
# -Modbus commands can be silently ignored and also not trip an alarm, e.g. move_to raises no errors
# -ensure all communication commands only raise subclasses of IOError then remove the broad catches (or add
#  specific ones if must to selectorAgent)
# move_to needs to be robust

# count= the number of registers to read
# unit= the slave unit this request is targeting
# address= the starting address to read from


# SOME VERY EARLY NOTES:
# SKR3306D-0470-P0-0BA0
#
# D block (2 short 470 travel
# 6mm lead
#
# Max speed 500mm/s  83.333 rev  #should that be 50mm/s?
#
# gear 10:1
#
# 1000 pulse/rev
# max pulse rate 83333 Hz
#
# pulserate*.006 = speed in mm/s
#
#
# See this: https://minimalmodbus.readthedocs.io/en/master/usage.html#general-on-modbus-protocol
#Function codes supported 3,6,8,10,17 (hex)  3,6,8,16,23

# pymodbus.register_read_message.ReadHoldingRegistersRequest 3
# pymodbus.register_write_message.WriteSingleRegisterRequest 6
# pymodbus.diag_message.DiagnosticStatusRequest(**kwargs) 8
# pymodbus.register_write_message.WriteMultipleRegistersRequest 16
# pymodbus.register_read_message.ReadWriteMultipleRegistersRequest 23

ALARM_CODES = {0x66: 'Hardware Overtravel',
               0x67: 'Software Overtravel',
               0x62: 'Return-to-home error'}

MAX_HOME_TIME = 40
CLIENTID = 1
BAUD = 230400

ADDR_REMOTEOUT = (0x007f, 1)
ADDR_DIO = (0x00D4, 2)
ADDR_OUTPUTS = (0x0178, 8)  # 0x0178-0x017F

MAX_PULSE_RATE = 74000  # from docs should be 83333, however anything above ~74916 seems to trigger overspeed

DEFAULT_SPEED_MMPERS = 28  # mm/s
MM_TO_PULSE = PULSE_PER_MM = 1 / .0006
DEFAULT_SPEED = int(round(MM_TO_PULSE * DEFAULT_SPEED_MMPERS))
DEFAULT_ACCEL = int(round(MM_TO_PULSE * 600))  # 0.6 m/s^2 is what the system came programmed with
DEFAULT_DECEL = DEFAULT_ACCEL


#need to be able to check software limits from agent

#MBC bit indicates the break is disabled, might stand for motor break current

# Note null strings indicate bits reserved by OM, '-' indicates an unassigned/unused/NON-SIG bit
# Note that setvalue/defaultvalue
DIRECT_IO_IN_BITS = ('FW-LS', '-', 'RV-LS', 'STOP-COFF', 'HOMES', '-/FREE', '-/STOP', 'ALM-RST', '-/FW-JOG', '-/RV-JOG',
                     'P-RESET', '', '-', '-', '-', '-')  # 0-9, ext-in, N/C, virin 0-3  pg 378
DIRECT_IO_OUT_BITS = ('HOME-END', 'IN-POS', 'PLS-RDY', 'READY', 'MOVE', 'ALM-B', '', '', '', '', '', '', '', '',
                      'ASG', 'BSG')  # Dout 0-5  pg 378

REMOTE_IO_OUT_BITS = ('MBC', 'STOP-COFF_R', 'RV_LS_R', '-', 'FW-LS_R', 'READY', 'INFO', 'ALM-A', 'SYS-BSY',
                      'AREA0', 'AREA1', 'AREA2', 'TIM', 'MOVE', 'IN-POS', 'TLC')

REMOTE_IO_IN_BITS = ('STOP-COFF', '-', 'M2', 'START', 'HOME', 'STOP', 'FREE', 'ALM-RST',
                     'D-SEL0', 'D-SEL1', 'D-SEL2', 'SSTART', 'FW-JOG-P', 'RV-JOG-P', 'FW-POS', 'RV-POS')



#ALM-B is just the opposite polarity of ALM-A
OUTPUT_BITS = ("HOME-END", "ABSPEN", "ELPRST-MON", "-", "-", "PRST-DIS", "PRST-STLD", "ORGN-STLD", "RND-OVF", "FW-SLS",
               "RV-SLS", "ZSG", "RND-ZERO", "TIM", "-", "MAREA", "CONST-OFF", "ALM-A", "ALM-B", "SYS-RDY", "READY",
               "PLS-RDY", "MOVE", "INFO", "SYS-BSY", "ETO-MON", "IN-POS", "-", "TLC", "VA", "CRNT", "AUTO-CD",
               "MON-OUT", "PLS-OUTR", "-", "-", "USR-OUT0", "USR-OUT1", "-", "-", "-", "-", "-", "-", "-", "-", "-",
               "-", "AREA0", "AREA1", "AREA2", "AREA3", "AREA4", "AREA5", "AREA6", "AREA7", "MPS", "MBC", "RG", "-",
               "EDM", "HWTOIN-MON", "-", "-", "M-ACT0", "M-ACT1",  "M-ACT2", "M-ACT3", "M-ACT4", "M-ACT5", "M-ACT6",
               "M-ACT7", "D-END0", "D-END1", "D-END2", "D-END3", "D-END4",  "D-END5", "D-END6", "D-END7", "CRNT-LMTD",
               "SPD-LMTD", "-", "-", "OPE-BSY", "PAUSE-BSY", "SEQ-BSY",  "DELAY-BSY", "JUMP0-LAT", "JUMP1-LAT",
               "NEXT-LAT", "PLS-LOST", "DCMD-RDY", "DCMD-FULL", "-", "M-CHG",  "INFO-FW-OT", "INFO-RV-OT", "INFO-CULD0",
               "INFO-CULD1", "INFO-TRIP", "INFO-ODO", "-", "-", "-", "-", "-", "-",  "INFO-DSLMTD", "INFO-IOTEST",
               "INFO-CFG", "INFO-RBT", "INFO-USRIO", "INFO-POSERR", "INFO-DRVTMP",  "INFO-MTRTMP", "INFO-OVOLT",
               "INFO-UVOLT", "INFO-OLTIME", "-", "INFO-SPD", "INFO-START", "INFO-ZHOME",  "INFO-PR-REQ", "-",
               "INFO-EGR-E", "INFO-RND-E", "INFO-NET-E")


def merge(reg, twos=False, le=True, return_bits=False):
    #bits[0]
    s = 'uintle:16={}' if le else 'uint:16={}'
    bits = Bits(','.join([s]*len(reg)).format(*reg))
    if return_bits:
        return bits
    return bits.uint if not twos else bits.int


class OrientalMotor(object):
    def __init__(self, port, baud=BAUD):
        self.baud = baud
        self.port = port
        self.modbus = None
        self.rlock = threading.RLock()
        self.connect(error=False)

    def close(self):
        """required by exit hooks of agent"""
        self.disconnect()

    def disconnect(self):
        try:
            self.modbus.close()
        except OSError:
            pass
        except AttributeError:
            pass
        self.modbus = None

    def connect(self, error=True):
        if self.modbus is not None:
            try:
                self.modbus.connect()
            except ModbusException as s:
                if error:
                    raise s
            return

        self.modbus = ModbusClient(method="rtu", port=self.port, stopbits=1, bytesize=8, parity='E', baudrate=BAUD)

        try:
            self.modbus.connect()
            # ~1337 mm in the OM control program
            if self.read_regs(0x0404, 2, reverse=False, connect=False).int != -28297:
                logging.getLogger(__name__).error("Controller not programmed")
                raise IOError("Controller not programmed")
        except ModbusException as s:
            if error:
                raise IOError('Controller may not be powered, got '+str(s))
        except IOError as s:
            if error:
                raise s
        except TypeError:
            if error:
                raise IOError('Controller may not be powered, got TypeError from pymodbus')

    def write_regs(self, addr, values, connect=True):
        if connect:
            self.connect()
        try:
            if isinstance(values, int):
                self.modbus.write_register(0x007D, values, unit=1)
            else:
                self.modbus.write_registers(addr, values, unit=1)
        except ModbusIOException as s:
            self.disconnect()
            raise IOError(s)
        except ConnectionException as s:
            self.disconnect()
            raise IOError(s)
        except select.error as s:
            self.disconnect()
            raise IOError(s)
        except OSError as s:
            self.disconnect()
            raise IOError(s)

    def read_regs(self, addr, length, reverse=True, raw=False, connect=True):
        if connect:
            self.connect()
        try:
            reg = self.modbus.read_holding_registers(addr, length, unit=1)
        except ConnectionException as s:
            self.disconnect()
            raise IOError(s)
        except select.error as s:
            self.disconnect()
            raise IOError(s)
        except OSError as s:
            self.disconnect()
            raise IOError(s)

        if isinstance(reg, ModbusIOException):
            self.disconnect()
            raise IOError(str(reg))

        if raw:
            return reg.registers

        ba = BitArray(','.join(['uint:16={}'] * len(reg.registers)).format(*reg.registers))
        if reverse:
            out = BitArray()
            for b in ba.cut(16):
                b.reverse()
                out.append(b)
        else:
            out = ba
        return out

    def get_remoteOut(self, pretty=True):
        """
        0000111010000001 = 3713 =  RO 0,7,9-B  uintle:163713
        Return bitstring.Bits of the 16 bits of remote output or a tuple with the set bits (if pretty is set).

        pretty returns a list of the bit names
        """
        x = self.read_regs(*ADDR_REMOTEOUT)
        return tuple([v for i, v in enumerate(REMOTE_IO_OUT_BITS) if x[i] and v]) if pretty else x

    def get_directIO(self, pretty=True):
        #p 378
        #first 16 are out 0-15 second are in 0-15
        #[49152, 21] -> O14,15 and I0,2,4 set
        x = self.read_regs(*ADDR_DIO)  #0-15 out 16-31 in
        return tuple([v for i, v in enumerate(DIRECT_IO_OUT_BITS) if x[i] and v]) if pretty else x

    @property
    def limits(self):
        """Returns the limits software or HW, whichever is smaller"""
        fv_lim = self.read_regs(0x0388, 2, reverse=False).int
        rw_lim = self.read_regs(0x038A, 2, reverse=False).int
        return rw_lim, fv_lim

    @property
    def moving(self):
        return self.get_remoteOut(pretty=False)[REMOTE_IO_OUT_BITS.index('MOVE')]

    @property
    def home_end(self):
        return self.get_out(pretty=False)[DIRECT_IO_OUT_BITS.index('HOME-END')]

    def get_out(self, pretty=True):
        x = self.read_regs(*ADDR_OUTPUTS)
        return tuple([v for i, v in enumerate(OUTPUT_BITS) if x[i] and v]) if pretty else x

    def disable_software_limits(self):
        self.write_regs(0x0386, [word.uint for word in Bits(int=-1, length=32).cut(16)])

    def enable_software_limits(self):
        """See page 404 of HM-60262-6E.pdf. 1=deceleration stop"""
        self.write_regs(0x0386, [word.uint for word in Bits(int=1, length=32).cut(16)])

    def set_sw_limits(self, limits):
        """See page 404 of HM-60262-6E.pdf."""
        rlim=min(limits)
        flim=max(limits)
        # negative
        self.write_regs(0x038A, [word.uint for word in Bits(int=rlim, length=32).cut(16)])
        # positive
        self.write_regs(0x0388, [word.uint for word in Bits(int=flim, length=32).cut(16)])

    def calibrate(self):
        self.set_remote_in('FW-POS', False)
        self.set_remote_in('RV-POS', False)
        self.reset_alarm()
        self.turn_off_break()
        self.sleep(.15)
        self.disable_software_limits()
        self.set_remote_in('RV-POS')
        time.sleep(1)
        while self.moving:
            time.sleep(.1)
        self.set_remote_in('RV-POS', False)
        self.reset_alarm()
        if self.break_is_on:
            self.enable_software_limits()
            return False  # Abort we were stopped
        self.set_remote_in('HOME')
        self.set_remote_in('HOME', False)
        elapsed = 0
        while not (self.break_is_on or self.alarm or self.home_end or elapsed > MAX_HOME_TIME):
            elapsed += .1
            time.sleep(.1)

        self.enable_software_limits()
        self.turn_on_break()
        return self.home_end and not self.alarm

    def get_temps(self):
        """ drivetemp, motor temp (deg C)"""
        # INFO - DRVTMP  0x00F8 0x00f9   (1=0.1C)
        # INFO - MTRTMP  0x00FA 0x00fb
        #[0, 338] -> 33.300000000000004
        return self.read_regs(0x00F8, 2, reverse=False).uint * 0.1, self.read_regs(0x00FA, 2, reverse=False).uint * 0.1

    def get_position(self, steps=True):
        # 0x00CC-D detected position, is in steps
        #[65535, 37239] -> -28297
        raw = self.read_regs(0x00CC, 2, reverse=False).int
        return raw if steps else raw / PULSE_PER_MM

    def move_to(self, position, speed=None, accel=None, decel=None, relative=False, _debreak_sleep=.15,
                steps=True):
        """ See pg. 306 & 365 of HM-60262-6E.pdf

        pos in mm unless steps = True
        speed in mm/s, limit is about 44 mm/s
        accel&decel in steps/sec

        #move_to -50 should generate cmd=[0, 0, 0, 1, 65534, 47739, 0, 46667, 15, 16960, 15, 16960, 0, 1000, 0, 1]
        """
        op_number = 0
        op_type = 3 if relative else 1  # relative to feedback (2 is relative to previous command pos)

        position = int(round(position * PULSE_PER_MM)) if not steps else int(round(position))

        speed = int(round(min(speed * PULSE_PER_MM if speed is not None else DEFAULT_SPEED, MAX_PULSE_RATE)))
        accel = int(round(accel * PULSE_PER_MM if accel is not None else DEFAULT_ACCEL))
        decel = int(round(decel * PULSE_PER_MM if decel is not None else DEFAULT_DECEL))
        current = 1000  # 100% in units of .1
        trigger = 1  # move right away

        cmd = (Bits(uint=op_number, length=32) + Bits(uint=op_type, length=32) + Bits(int=position, length=32) +
               Bits(uint=speed, length=32) + Bits(uint=accel, length=32) + Bits(uint=decel, length=32) +
               Bits(uint=current, length=32) + Bits(uint=trigger, length=32))

        with self.rlock:
            self.turn_off_break()
            time.sleep(_debreak_sleep)
            self.write_regs(0x058, [word.uint for word in cmd.cut(16)])

        # def split_dword(x):
        #     return x >> 16, x & 0xffff
        #
        # def twos_complement(val, nbits):
        #     """Compute the 2's complement of int value val"""
        #     if val < 0:
        #         val = (1 << nbits) + val
        #     else:
        #         if (val & (1 << (nbits - 1))) != 0:
        #             # If sign bit is set.
        #             # compute negative value.
        #             val = val - (1 << nbits)
        #     return val
        # cmd = []
        # cmd.extend(split_dword(op_number))
        # cmd.extend(split_dword(op_type))
        # cmd.extend(split_dword(twos_complement(position, 32)))
        # cmd.extend(split_dword(speed))
        # cmd.extend(split_dword(accel))
        # cmd.extend(split_dword(decel))
        # cmd.extend(split_dword(current))
        # cmd.extend(split_dword(trigger))
        # self.turn_off_break()
        # time.sleep(_debreak_sleep)
        # self.modbus.write_registers(0x058, cmd, unit=1)

    def stop(self, apply_break=True):
        """
        This performs a deceleration stop and sets the commanded position to stop position. Motor is left energized.
        """
        if apply_break:
            self.turn_on_break()  #NB where does the set the commanded position
        else:
            self.move_to(0, 0)  #this works, go figure

    @property
    def break_is_on(self):
        return self.get_remoteOut(pretty=False)[REMOTE_IO_OUT_BITS.index('STOP-COFF_R')]

    def turn_on_break(self):
        #p284
        # 0x0171 bit0 STOP-COFF
        with self.rlock:
            val = self.read_regs(0x007D, 1)
            val[0] = True
            val.reverse()  #writes are reversed words, gross
            self.write_regs(0x007D, val.uint)

    def turn_off_break(self):
        #p284
        # 0x0171 bit0 STOP-COFF
        with self.rlock:
            val = self.read_regs(0x007D, 1)
            val[0] = False
            val.reverse()
            self.write_regs(0x007D, val.uint)

    def set_remote_in(self, bit_name, value=True):
        #p284
        if bit_name == '-':  #These are unused bits
            return
        with self.rlock:
            val = self.read_regs(0x007D, 1)
            val[REMOTE_IO_IN_BITS.index(bit_name.upper())] = bool(value)
            val.reverse()
            self.write_regs(0x007D, val.uint)

    @property
    def alarm(self):
        """True if there is an alarm"""
        return self.get_remoteOut(pretty=False)[REMOTE_IO_OUT_BITS.index('ALM-A')]

    def read_alarm(self, number=0):
        """
        0x0080-1 present alarm code
        01AA-01AB alarm record details, write 0 to 10 to pick
        then read 0A00-0A18

        p 452 for meanings
        """
        # code = client.read_holding_registers(0x0080, 2, unit=1).registers
        self.write_regs(0x01AA, [0, number])
        regs_iter = iter(self.read_regs(0x0A00, 26, raw=True))
        try:
            vals = [merge((r, next(regs_iter)), le=0) for r in regs_iter]
            return OrientalAlarm(vals)
        except Exception:
            return 'ERROR: Unable to read alarm code'

    def reset_alarm(self):
        # 0x0180-1  write 0, then 1
        self.write_regs(0x0180, [0, 0])
        self.write_regs(0x0180, [0, 1])
        # 0x0184-5 clear alarm records
        self.write_regs(0x0184, [0, 0])
        self.write_regs(0x0184, [0, 1])
        # # 0x0188 clear communication error records
        # self.write_regs(0x0188, [0, 0])
        # self.write_regs(0x0188, [0, 1])

    def get_torque_pct(self):
        """0-100"""
        # 0x00D6 0x00D7  current/max torque
        return self.read_regs(0x00D6, 2,reverse=False).uint/10.0

    def get_commanded_position(self, steps=True):
        # 0x00C6-7 command position
        raw = self.read_regs(0x00C6, 2, reverse=False).int
        return raw if steps else raw / PULSE_PER_MM

    def status(self):
        # 0x00AC-D present communication error
        direct_bits = self.get_directIO(pretty=False)
        out_bits = self.get_out(pretty=False)
        remote_bits = self.get_remoteOut(pretty=False)

        alarm = self.read_alarm()
        torque_pct = self.get_torque_pct()
        drive_temp, motor_temp = self.get_temps()
        position = self.get_position()
        commanded_position = self.get_commanded_position()

        return OrientalState(direct_bits, remote_bits, out_bits, drive_temp=drive_temp, motor_temp=motor_temp,
                             position=position, commanded_position=commanded_position, torque=torque_pct, alarm=alarm)


class OrientalAlarm(object):
    def __init__(self, alarm_record):
        # 66 means sensor error at power on  get if motor disconnected
        if len(alarm_record) != 13:
            raise ValueError('Alarm records must have 13 entries')
        u = alarm_record[9]  # fbpos is in twos compliment, 32b
        alarm_record[9] = (u & ((1 << 31) - 1)) - (u & (1 << 31))
        self.record = tuple(alarm_record)
        #code, subcode, drive t, motor t, invert volt*10, dio in, rio out, op info 1, op info 2, feedbackpos, time from boot, time from move, main power time
        # code0, subcode1, drive t2, motor t3, invert volt*10 4, dio in 5, rio out 6, op info 1 7, op info 2 8, feedbackpos 9, time from boot 10,
        # time from move 11, main power time 12
        #le=(0, 0, 0, 0,0, 0, 0, ? (-1=[0, 65535]),? (13 = [0, 13]), twos=1 & le=0 (I think), 0, 0, [0, 2315] = 1day 14h 35 min)

    def __str__(self):
        if self.code == 0:
            return 'No Alarm'

        msg = ('AZD Alarm: {record[0]}:{record[1]} ({alarm}) Drive/Motor T: {record[2]}/{record[3]} C '
               'Vin: {volt:.1f} DIOin: {dio} RIOout: {rio} Pos: {record[9]} '
               'OpInfo: {record[7]},{record[8]} '
               'Time (boot/move/power): {record[10]}/{record[11]}/{record[12]}')
        return msg.format(record=self.record, alarm=ALARM_CODES.get(self.record[0], 'HM-60262-6E pg.452'),
                          volt=float(self.record[4])/10, dio=bin(self.record[5]), rio=bin(self.record[6]))

    @property
    def code(self):
        return self.record[0]

    def __nonzero__(self):
        return self.record[0] != 0


class OrientalState(object):
    def __init__(self, direct_bits, remote_bits, out_bits, motor_temp=None, drive_temp=None,
                 position=None, commanded_position=None, alarm=None, torque=None):
        """
        required attributes:
        'error_string' (if has_fault)
        'has_fault'
        'position'
        'moving'
        'temp_string'
        """
        self.out_bits = out_bits

        self.direct_bits = direct_bits
        self.home = direct_bits[DIRECT_IO_IN_BITS.index('HOMES')]

        self.remote_bits = remote_bits
        self.motor_powered = not remote_bits[REMOTE_IO_OUT_BITS.index('STOP-COFF_R')]
        self.brake_on = not remote_bits[REMOTE_IO_OUT_BITS.index('MBC')]
        self.moving = remote_bits[REMOTE_IO_OUT_BITS.index('MOVE')]
        self.ready = remote_bits[REMOTE_IO_OUT_BITS.index('READY')]
        self.in_position = remote_bits[REMOTE_IO_OUT_BITS.index('IN-POS')]
        self.fwlim = remote_bits[REMOTE_IO_OUT_BITS.index('FW-LS_R')]
        self.rvlim = remote_bits[REMOTE_IO_OUT_BITS.index('RV_LS_R')]
        self.fwslim = out_bits[OUTPUT_BITS.index('FW-SLS')]
        self.rvslim = out_bits[OUTPUT_BITS.index('RV-SLS')]

        self.position = position
        self.commanded_position = commanded_position
        self.position_error = position - commanded_position
        self.alarm = alarm
        self.motor_temp = motor_temp
        self.drive_temp = drive_temp
        self.torque = torque

        # self.error_string = error_string
        self.has_fault = bool(self.alarm)

    @property
    def position_error_str(self):
        """ Positve position_error indicates overshoot """
        return '{:.1f}um ({})'.format(self.position_error/MM_TO_PULSE*1000, self.position_error)

    @property
    def error_string(self):
        return 'No Errors' if not self.alarm.code else str(self.alarm)

# self = m = OrientalMotor(PORT)
# if __name__ == '__main__':
#     logging.basicConfig()
#     log = logging.getLogger()
#     log.setLevel(logging.DEBUG)
#     m = self = OrientalMotor(PORT)

# -hw lim @-107
# +hw lim @159.5
# -104 to 156
