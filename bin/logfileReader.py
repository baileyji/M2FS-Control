#File format
#0 header size
#1- header size - 13: ID (ascii string) (1-4)
#next 4 bytes: write pos
#next 4: read pos
#next 4: file end
#next byte if file end != header size: record length
#next length bytes: record
#rinse lather repeat
import sys
sys.path.append(sys.path[0]+'/../lib/')
from construct import ULInt32
import numpy as np

from LoggerRecord import tempsParser, accelsParser, COMPOSITE_RECORD_LENGTH, ACCEL_RECORD_LENGTH, TEMP_RECORD_LENGTH, ACCELS_TO_GEES,N_TEMP_SENSORS

ulint32=ULInt32('f').parse

def processLogfile(file):

    with open(file,'r') as f:
        headersize=ord(f.read(1))
        id=f.read(headersize-13)
        wp=ulint32(f.read(4))
        rp=ulint32(f.read(4))
        eof=ulint32(f.read(4))
        
        assert rp < eof
        assert wp <= eof
        assert rp >=headersize
        assert wp >= headersize
        assert rp!=wp
        
        #Go to the read pointer
        f.seek(headersize)
        records=[]
        while True:
            rl=ord(f.read(1))
            data=f.read(rl)
            if len(data) != rl:
                raise IOError('Record truncated in file')
            
            try:
                records.append(parseRecord(data))
            except Exception:
                break
                
            if f.tell() == wp:
                #we've read out all the valid data
                break
            if f.tell() == eof and wp < rp:
                f.seek(headersize)

    return records

def parseRecord(data):
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
        import pdb;pdb.set_trace()
        raise ValueError("Malformed Record (%i bytes)" % len(data))

    if accels !=None:
        accels=ACCELS_TO_GEES*np.array(accels).reshape([32,3])

    unixtime=float(ulint32(data[-8:-4]))
    unixtime+=float(ulint32(data[-4:]) % 1000) /1000

    return (unixtime, temps, accels)