import pymodbus
from pymodbus.pdu import ModbusRequest
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pymodbus.transaction import ModbusRtuFramer
import numpy as np
import logging, time, threading

# TODO (general)
# -Modbus commands can be silently ignored and also not trip an alarm, e.g. move_to raises no errors
# -ensure all communication commands only raise subclasses of IOError then remove the broad catches (or add
#  specific ones if must to selectorAgent)
# move_to needs to be robust

# count= the number of registers to read
# unit= the slave unit this request is targeting
# address= the starting address to read from

CLIENTID = 1
PORT = '/dev/tty.usbserial-FT2KYRWY'  # '/dev/thkrail'
BAUD = 230400

ADDR_REMOTEIO = (0x007f, 2)
ADDR_DIO = (0x00D4, 2)
ADDR_OUTPUTS = (0x0178, 8)  # 0x0178-0x017F

MAX_PULSE_RATE = 74000  # from docs should be 83333, however anything above ~74916 seems to trigger overspeed

DEFAULT_SPEED_MMPERS = 28  # mm/s
MM_TO_PULSE = 1 / .0006
DEFAULT_SPEED = int(round(MM_TO_PULSE * DEFAULT_SPEED_MMPERS))
DEFAULT_ACCEL = int(round(MM_TO_PULSE * 600))  # 0.6 m/s^2 is what the system came programmed with
DEFAULT_DECEL = DEFAULT_ACCEL

"""
Function codes supported 3,6,8,10,17 (hex)  3,6,8,16,23

pymodbus.register_read_message.ReadHoldingRegistersRequest 3
pymodbus.register_write_message.WriteSingleRegisterRequest 6
pymodbus.diag_message.DiagnosticStatusRequest(**kwargs) 8
pymodbus.register_write_message.WriteMultipleRegistersRequest 16
pymodbus.register_read_message.ReadWriteMultipleRegistersRequest 23
"""

# Note null strings indicate bits reserved by OM, '-' indicates an unassigned/unused/NON-SIG bit
DIRECT_IO_IN_BITS = ('FW-LS', '-', 'RV-LS', 'STOP-COFF', 'HOMES', '-', '-', 'ALM-RST', '-', '-', 'P-RESET', '',
                     '-', '-', '-', '-')
DIRECT_IO_OUT_BITS = ('HOME-END', 'IN-POS', 'PLS-RDY', 'READY', 'MOVE', 'ALM-B', '', '', '', '', '', '', '', '',
                      'ASG', 'BSG')

REMOTE_IO_OUT_BITS = ('MBC', 'STOP-COFF_R', 'RV_LS_R', '-', 'FW-LS_R', 'READY', 'INFO', 'ALM-A', 'SYS-BSY',
                      'AREA0', 'AREA1', 'AREA2', 'TIM', 'MOVE', 'IN-POS', 'TLC')

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


def is_bit_set(value, bits, name):
    return bool(value & (1 << bits.index(name)))


def split_dword(x):
    return x >> 16, x & 0xffff


def twos_complement(val, nbits):
    """Compute the 2's complement of int value val"""
    if val < 0:
        val = (1 << nbits) + val
    else:
        if (val & (1 << (nbits - 1))) != 0:
            # If sign bit is set.
            # compute negative value.
            val = val - (1 << nbits)
    return val


def merge_reg(reg, bytewid=8,
              rev=False):  # Seems like rev should default to true since OM has high byters at lower register addr
    o = 0
    if rev:
        reg = reg[::-1]
    for i, r in enumerate(reg):
        o |= r << (i * bytewid)
    return o


class OrientalMotor(object):
    def __init__(self, port, baud=BAUD):
        self.baud = baud
        self.port = port
        self.modbus = None
        self.rlock = threading.RLock()

    def disconnect(self, stop_and_break=True):
        if stop_and_break:
            self.turn_on_break()
        self.modbus.close()

    def close(self):
        """Shortcut to disconnect(stop_and_break=True)"""
        self.disconnect(True)

    def connect(self):
        self.modbus = ModbusClient(method="rtu", port=self.port, stopbits=1, bytesize=8, parity='E', baudrate=BAUD)
        self.modbus.connect()

    def get_remoteOut(self, pretty=True):
        """Return number with the 16 bits of remote output, bytes might be flipped, need to test when one of bits 8-15
        set, (e.g. while moving)

        pretty returns a list of the bit names
        """
        x = merge_reg(self.modbus.read_holding_registers(*ADDR_REMOTEIO, unit=1).registers)
        if pretty:
            return tuple([v for i, v in enumerate(REMOTE_IO_OUT_BITS) if x & (1 << i) and v])
        else:
            return x

    def get_directOut(self, pretty=True):
        x = merge_reg(self.modbus.read_holding_registers(*ADDR_DIO, unit=1).registers)
        if pretty:
            return tuple([v for i, v in enumerate(DIRECT_IO_OUT_BITS) if x & (1 << i) and v])
        else:
            return x

    def get_out(self, pretty=True):
        x = merge_reg(self.modbus.read_holding_registers(*ADDR_OUTPUTS, unit=1).registers, bytewid=2)
        if pretty:
            return tuple([v for i, v in enumerate(OUTPUT_BITS) if x & (1 << i) and v])
        else:
            return x

    def get_temps(self):
        """ drivetemp, motor temp (deg C)"""
        # INFO - DRVTMP  0x00F8 0x00f9   (1=0.1C)
        # INFO - MTRTMP  0x00FA 0x00fb
        return (merge_reg(self.modbus.read_holding_registers(0x00F8, 2, unit=1).registers, bytewid=2, rev=True) * .1,
                merge_reg(self.modbus.read_holding_registers(0x00FA, 2, unit=1).registers, bytewid=2, rev=True) * .1)

    def move_to(self, position, speed=None, accel=None, decel=None, relative=False, _debreak_sleep=.15):
        """ See pg. 306 & 365 of HM-60262-6E.pdf

        pos in mm
        speed in mm/s, limit is about 44 mm/s
        accel&decel in steps/sec
        """
        op_number = 0
        op_type = 3 if relative else 1  # relative to feedback (2 is relative to previous command pos)
        position = int(round(position * MM_TO_PULSE))
        speed = int(round(min(speed * MM_TO_PULSE if speed is not None else DEFAULT_SPEED, MAX_PULSE_RATE)))
        accel = int(round(accel * MM_TO_PULSE if accel is not None else DEFAULT_ACCEL))
        decel = int(round(decel * MM_TO_PULSE if decel is not None else DEFAULT_DECEL))
        current = 1000  # 100% in units of .1
        trigger = 1  # move right away

        cmd = []
        cmd.extend(split_dword(op_number))
        cmd.extend(split_dword(op_type))
        cmd.extend(split_dword(twos_complement(position, 32)))
        cmd.extend(split_dword(speed))
        cmd.extend(split_dword(accel))
        cmd.extend(split_dword(decel))
        cmd.extend(split_dword(current))
        cmd.extend(split_dword(trigger))
        self.turn_off_break()
        time.sleep(_debreak_sleep)
        self.modbus.write_registers(0x058, cmd, unit=1)

    def get_position(self):
        # 0x00CC-D detected position, is in steps
        raw = merge_reg(self.modbus.read_holding_registers(0x00CC, 2, unit=1).registers, rev=True)
        return twos_complement(raw, 32) / MM_TO_PULSE

    def stop(self, apply_break=True):
        """
        This performs a deceleration stop and sets the commanded position to stop position. Motor is left energized.
        """
        if apply_break:
            self.turn_on_break()
        else:
            self.move_to(0, 0)

    def turn_on_break(self):
        val = merge_reg(self.modbus.read_holding_registers(0x007D, 2, unit=1).registers)  # 0x0171 bit0 STOP-COFF
        val |= 0b1
        self.modbus.write_register(0x007D, val, unit=1)

    def turn_off_break(self):
        val = merge_reg(self.modbus.read_holding_registers(0x007D, 2, unit=1).registers)  # 0x0171 bit0 STOP-COFF
        val &= 0xfffe
        self.modbus.write_register(0x007D, val, unit=1)

    def read_alarm(self, number=1):
        """
        0x0080-1 present alarm code
        01AA-01AB alarm record details, write 1 to 10 to pick
        then read 0A00-0A18

        TODO needs testing, (13 2 byte reg?) and lots of formatting/parsing
        """
        # code = client.read_holding_registers(0x0080, 2, unit=1).registers
        self.modbus.write_registers(0x01AA, [0, number], unit=1)
        regs = self.modbus.read_holding_registers(0x0A00, 26, unit=1).registers
        regs_iter = iter(regs)
        vals = [merge_reg((r, next(r)), rev=True) for r in regs_iter]
        alarm_code = vals[0]  # 66 means sensor error at power on  get if motor disconnected
        return vals

    def reset_alarm(self):
        # 0x0180-1  write 0, then 1
        self.modbus.write_registers(0x0180, [0, 0], unit=1)
        self.modbus.write_registers(0x0180, [0, 1], unit=1)
        # 0x0184-5 clear alarm records
        self.modbus.write_registers(0x0184, [0, 0], unit=1)
        self.modbus.write_registers(0x0184, [0, 1], unit=1)
        # 0x0188 clear communication error records

    def status(self):
        outputs = self.get_out()  # see bit list excel
        # 0x00AC-D present communcation error
        # 0x00C6-7 command position
        # 0x00CC-D detected position
        # 0x00D6 0x00D7  current/max torque
        # TODO finish

        out_bits = self.get_out(pretty=False)
        remote_bits = self.get_remoteOut(pretty=False)

        self.motor_powered = not is_bit_set(remote_bits, REMOTE_IO_OUT_BITS, 'STOP-COFF_R')

        torque_pct = merge_reg(self.modbus.read_holding_registers(0x00D6, 2, unit=1).registers, rev=True)

        self.torque_pct = torque_pct
        self.brake = is_bit_set(remote_bits, REMOTE_IO_OUT_BITS, 'MBC')
        self.position = self.get_position()
        self.moving = is_bit_set(remote_bits, REMOTE_IO_OUT_BITS, 'MOVING')
        self.ready = is_bit_set(remote_bits, REMOTE_IO_OUT_BITS, 'READY')
        self.inposition = is_bit_set(remote_bits, REMOTE_IO_OUT_BITS, 'IN-POS')
        self.alarm = self.read_alarm()[0]
        self.fwlim = is_bit_set(remote_bits, REMOTE_IO_OUT_BITS, 'FW-LS_R')
        self.rvlim = is_bit_set(remote_bits, REMOTE_IO_OUT_BITS, 'RV_LS_R')

        self.error_string = error_string
        self.has_fault = self.alarm != 0

        # REMOTE_IO_OUT_BITS = ('MBC', 'STOP-COFF_R', 'RV_LS_R', '-', 'FW-LS_R', 'READY', 'INFO', 'ALM-A', 'SYS-BSY',
        #                       'AREA0', 'AREA1', 'AREA2', 'TIM', 'MOVE', 'IN-POS', 'TLC')

        alarm = self.read_alarm()
        pos = self.get_position()
        drive, motor = self.get_temps()
        # self.modbus.read_holding_registers(0x0A00, 26, unit=1).registers

        from collections import namedtuple
        motorIsOn  # true/false
        breakEngaged
        moving
        return x(current, brake, pos, moving, ready, inpos, alarm, fmlim, rvlim, home)


class OrientalState(object):
    def __init__(self, *args, **kwargs):
        """
        required attributes:
        'error_string' (if has_fault)
        'has_fault'
        'position'
        'moving'
        'temp_string'

        'READY',"SYS-BSY","ETO-MON","IN-POS","FW-SLS","RV-SLS",'MBC'
        OUTPUT_BITS = ("HOME-END","ABSPEN","ELPRST-MON","-","-","PRST-DIS","PRST-STLD","ORGN-STLD","RND-OVF","FW-SLS","RV-SLS",
               "ZSG", "RND-ZERO","TIM","-","MAREA","CONST-OFF","ALM-A","ALM-B","SYS-RDY","READY","PLS-RDY","MOVE",
               "INFO","SYS-BSY","ETO-MON","IN-POS","-","TLC","VA","CRNT","AUTO-CD","MON-OUT","PLS-OUTR","-","-",
               "USR-OUT0","USR-OUT1","-","-","-","-","-","-","-","-","-","-","AREA0","AREA1","AREA2","AREA3",
               "AREA4","AREA5","AREA6","AREA7","MPS","MBC","RG","-","EDM","HWTOIN-MON","-","-","M-ACT0","M-ACT1",
               "M-ACT2","M-ACT3","M-ACT4","M-ACT5","M-ACT6","M-ACT7","D-END0","D-END1","D-END2","D-END3","D-END4",
               "D-END5","D-END6","D-END7","CRNT-LMTD","SPD-LMTD","-","-","OPE-BSY","PAUSE-BSY","SEQ-BSY",
               "DELAY-BSY","JUMP0-LAT","JUMP1-LAT","NEXT-LAT","PLS-LOST","DCMD-RDY","DCMD-FULL","-","M-CHG",
               "INFO-FW-OT","INFO-RV-OT","INFO-CULD0","INFO-CULD1","INFO-TRIP","INFO-ODO","-","-","-","-","-","-",
               "INFO-DSLMTD","INFO-IOTEST","INFO-CFG","INFO-RBT","INFO-USRIO","INFO-POSERR","INFO-DRVTMP",
               "INFO-MTRTMP","INFO-OVOLT","INFO-UVOLT","INFO-OLTIME","-","INFO-SPD","INFO-START","INFO-ZHOME",
               "INFO-PR-REQ","-","INFO-EGR-E","INFO-RND-E","INFO-NET-E")


        """
        self.motor_powered = motor_powered
        self.position = position
        self.current_ma = current_ma
        self.brake = brake
        self.position = position
        self.moving = moving
        self.ready = ready
        self.inposition = inposition
        self.alarm = alarm
        self.fwlim = fwlim
        self.rvlim = rvlim
        self.home = home
        self.error_string = error_string
        self.has_fault = has_fault

    #
    # @property
    # def calibrated(self):
    #     return self.io.calibrated
    #
    # @property
    # def errorPresent(self):
    #     return self.faults.faultPresent or self.io.errcode
    #
    # def faultString(self):
    #     return bin(self.faults.byte) + bin(self.io.errcode)


m = OrientalMotor(PORT)
# if __name__ == '__main__':
#     logging.basicConfig()
#     log = logging.getLogger()
#     log.setLevel(logging.DEBUG)
#     m = self = OrientalMotor(PORT)

# -hw lim @-107
# +hw lim @159.5
# -104 to 156
