import time
from construct import UBInt32, StrictRepeater, LFloat32, SLInt16, ULInt32
from numpy import array as numpyarray
import m2fsConfig

#Temp sensor quantity and order
N_TEMP_SENSORS=3

ECHELLE_INDEX_B=2
PRISM_INDEX_B=1
LORES_INDEX_B=0

ECHELLE_INDEX_R=1
PRISM_INDEX_R=2
LORES_INDEX_R=0

ECHELLE_OFFSET_B=-0.3125
PRISM_OFFSET_B=-0.125
LORES_OFFSET_B=-0.0625

ECHELLE_OFFSET_R=-0.125
PRISM_OFFSET_R=-0.125
LORES_OFFSET_R=-0.0625

#Lengths of the message parts in bytes
TEMPERATURE_BYTES=4
ACCELERATION_BYTES=2
TIMESTAMP_LENGTH=8
ADXL_FIFO_LENGTH=32
NUM_AXES=3
ACCELS_TO_GEES=0.00390625
ACCEL_RECORD_LENGTH=TIMESTAMP_LENGTH+NUM_AXES*ACCELERATION_BYTES*ADXL_FIFO_LENGTH
TEMP_RECORD_LENGTH=TIMESTAMP_LENGTH + TEMPERATURE_BYTES*N_TEMP_SENSORS
COMPOSITE_RECORD_LENGTH=ACCEL_RECORD_LENGTH+TEMP_RECORD_LENGTH-TIMESTAMP_LENGTH


#These are constructs which take the raw binary data for the accelerations or
# temps and parse them into lists of numbers
tempsParser =StrictRepeater(N_TEMP_SENSORS, LFloat32("temps")).parse
accelsParser=StrictRepeater(ADXL_FIFO_LENGTH*NUM_AXES, SLInt16("accel")).parse
unsigned32BitParser=ULInt32("foo").parse


class Unmergable(Exception):
    pass


def fromDataloggerData(side, data):
    """
    Create a LoggerRecord from the raw data string from the datalogger
    
    The raw string consists of the data following the L and record length
    """
    #Vet side
    if side!='R' and side!='B':
        raise ValueError('Side must be R or B')
    #Parse the raw data
    if len(data)==COMPOSITE_RECORD_LENGTH:
        temps=tempsParser(data[0:4*N_TEMP_SENSORS+1])
        accels=accelsParser(data[0:-8])
    elif len(data)==ACCEL_RECORD_LENGTH:
        temps=None
        accels=accelsParser(data[0:-8])
    elif len(data)==TEMP_RECORD_LENGTH:
        temps=tempsParser(data[0:-8])
        accels=None
    else:
        raise ValueError("Malformed Record (%i bytes)" % len(data))
    unixtime=float(unsigned32BitParser(data[-8:-4]))
    unixtime+=float(unsigned32BitParser(data[-4:]) % 1000) /1000
    #Convert the raw accelerometer data to Gs
    if accels is not None:
        accels=ACCELS_TO_GEES*numpyarray(accels).reshape([32,3])
    #Extract the sensor values
    if temps is not None:
        if side == 'R':
            echelleTemp=temps[ECHELLE_INDEX_R]+ECHELLE_OFFSET_R
            prismTemp=temps[PRISM_INDEX_R]+PRISM_OFFSET_R
            loresTemp=temps[LORES_INDEX_R]+LORES_OFFSET_R
        else:
            echelleTemp=temps[ECHELLE_INDEX_B]+ECHELLE_OFFSET_B
            prismTemp=temps[PRISM_INDEX_B]+PRISM_OFFSET_B
            loresTemp=temps[LORES_INDEX_B]+LORES_OFFSET_B
    else:
        echelleTemp=None
        prismTemp=None
        loresTemp=None
    #Generate the logger record
    if side=='R':
        return LoggerRecord(unixtime,
                            echelleRTemp=echelleTemp,
                            prismRTemp=prismTemp,
                            loresRTemp=loresTemp,
                            accelsR=accels)
    elif side =='B':
        return LoggerRecord(unixtime,
                            echelleBTemp=echelleTemp,
                            prismBTemp=prismTemp,
                            loresBTemp=loresTemp,
                            accelsB=accels)

class LoggerRecord(object):
    """
    A timestamped record containing temperatures and/or accelerations
    
    Initialize with the raw data string (following the L and num bytes sent)
    sent from the datalogger or by specifying fields individually. Throws 
    ValueError raw data does not parse into a valid record.
    
    Has the attributes:
    timestamp  - the unixtime of the record
    shackhartmaTemp - the shack-hartman temp reading
    sideR & sideB  - dicts of readings with keys: cradleTemp, echelleTemp, 
        prismTemp, loresTemp, & accels
    Temp readings are either None or a float
    Accels readings are either None of a numpy array in Gs with the format TODO.
    The first|last TODO reading is taken at approximately the timestamp and the
    remainder pre|pro TODO ceeding at intervals of 40 ms. The 3 element 
    dimension consists of x, y, & z axes.
    Side R & sideB accels are mutually exclusive

    Implements the magic function __str__
    """
    def __init__(self, timestamp, shackhartmanTemp=None,
                 cradleRTemp=None, cradleBTemp=None,
                 echelleRTemp=None, echelleBTemp=None,
                 prismRTemp=None, prismBTemp=None,
                 loresRTemp=None, loresBTemp=None,
                 accelsR=None, accelsB=None,
                 ifuProbeTemps=None, ifuSelectorDriveTemp=None, ifuSelectorMotorTemp=None):
        self.unixtime=timestamp
        self.shackhartmanTemp=shackhartmanTemp
        self.ifu=m2fsConfig.ifuProbeTempsToDict(ifuProbeTemps)
        self.ifu['driveTemp']=ifuSelectorDriveTemp
        self.ifu['motorTemp']=ifuSelectorMotorTemp
        self.sideR={'cradleTemp':cradleRTemp, 'echelleTemp':echelleRTemp,
            'prismTemp':prismRTemp, 'loresTemp':loresRTemp, 'accels':accelsR}
        self.sideB={'cradleTemp':cradleBTemp, 'echelleTemp':echelleBTemp,
            'prismTemp':prismBTemp, 'loresTemp':loresBTemp, 'accels':accelsB}
    
    def __str__(self):
        timestr=self.timeString()
        temps=self.tempsString()
        accels=self.accelsString()
        return ' '.join([timestr, temps, accels])
    
    def empty(self):
        """ Return true if the record contains no data """
        if self.haveIFUMData() or self.haveMFibData():
            return False
        for k in self.sideR.keys():
            if self.sideR[k] is not None:
                return False
        for k in self.sideB.keys():
            if self.sideB[k] is not None:
                return False
        return True
    
    def bOnly(self):
        """ Return true iff the record only contains B side data """
        if self.haveIFUMData() or self.haveMFibData():
            return False
        return self.haveBData() and not self.haveRData()

    def rOnly(self):
        """ Return true iff the record only contains R side data """
        if self.haveIFUMData() or self.haveMFibData():
            return False
        return self.haveRData() and not self.haveBData()

    def haveBData(self):
        for k in self.sideB.keys():
            if self.sideB[k] is not None:
                return True

    def haveRData(self):
        for k in self.sideR.keys():
            if self.sideR[k] is not None:
                return True

    def haveMFibData(self):
        return self.haveSHData()

    def haveIFUMData(self):
        return any(v is not None for v in self.ifu.values())

    def haveSHData(self):
        return self.shackhartmanTemp is not None

    def prettyStr(self):
        timestr=self.timeString()
        temps=self.tempsString()
        accels='No Accels'
        if self.sideB['accels'] is not None or self.sideR['accels'] is not None:
            accels='Accels '
        if self.sideB['accels'] is not None:
            accels+='B'
        if self.sideR['accels'] is not None:
            accels+='R'
        return ' '.join([timestr, temps, accels])

    def accelsString(self):
        """ Return a space delimited string of acceleration values with side """
        if self.sideB['accels'] is not None:
            return 'B\n'+str(self.sideB['accels'])
        elif self.sideR['accels'] is not None:
            return 'R\n'+str(self.sideR['accels'])
        else:
            return 'No Accels'
    
    def tempsString(self):
        """ Return a space delimited string of the temps or 'None' """
        if m2fsConfig.m2fsConfig.ifum_devices_present():  #TODO this is garbage, don't depend on that!
            temps = [self.ifu['ifuHTemp'], self.ifu['ifuSTemp'], self.ifu['ifuLTemp'],
                     self.ifu['motorTemp'], self.ifu['driveTemp'],
                     self.sideR['cradleTemp'], self.sideB['cradleTemp'],
                     self.sideR['echelleTemp'], self.sideB['echelleTemp'],
                     self.sideR['prismTemp'], self.sideB['prismTemp'],
                     self.sideR['loresTemp'], self.sideB['loresTemp']]
        else:
            temps=[self.shackhartmanTemp,
                   self.sideR['cradleTemp'], self.sideB['cradleTemp'],
                   self.sideR['echelleTemp'], self.sideB['echelleTemp'],
                   self.sideR['prismTemp'], self.sideB['prismTemp'],
                   self.sideR['loresTemp'], self.sideB['loresTemp']]
        temps=['{:.4f}'.format(t) if t is not None else 'U' for t in temps]
        return ' '.join(temps)
    
    def timeString(self):
        """
        Return the time of the record in the form Thu, 24 Jan 2013 06:00:09
        """
        formatStr="%a, %d %b %Y %H:%M:%S"
        return time.strftime(formatStr, time.localtime(self.unixtime))

    def recordsMergable(self, other):
        """
        Combines the records if they record different data, are both for the
        same minute. If they both contain accelerometer data, then they may not
        be merged
        """
        if self.shackhartmanTemp and other.shackhartmanTemp:
            return False
        for k in self.ifu.keys():
            if self.ifu[k] is not None and other.ifu[k] is not None:
                return False
        for k in self.sideR.keys():
            if self.sideR[k] is not None and other.sideR[k] is not None:
                return False
        for k in self.sideB.keys():
            if self.sideB[k] is not None and other.sideB[k] is not None:
                return False
        #Ensure both don't contain acceleration data
        if (self.sideR['accels'] is not None and other.sideB['accels'] is not None or
            self.sideB['accels'] is not None and other.sideR['accels'] is not None):
            return False
#        if int(other.unixtime)/60 != int(self.unixtime)/60:
#            return False
        return True
    
    def merge(self, other, force=False):
        """
        Merge other with this record if appropriate or throw ValueError
        
        If Force is true (default false) all set values are merged into self
        """
        if not force and not self.recordsMergable(other):
            raise Unmergable()
        # acceleration timestamp has priority
        if (not force and (other.sideR['accels'] is not None or
                           other.sideB['accels'] is not None)):
                self.unixtime=other.unixtime
        for k,v in other.sideB.items():
            if v is not None:
                self.sideB[k]=v
        for k,v in other.sideR.items():
            if v is not None:
                self.sideR[k]=v
        for k,v in other.ifu.items():
            if v is not None:
                self.ifu[k]=v
        if other.shackhartmanTemp is not None:
            self.shackhartmanTemp=other.shackhartmanTemp
