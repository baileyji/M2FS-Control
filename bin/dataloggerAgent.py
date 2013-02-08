#!/usr/bin/env python2.7
import sys, time, threading, Queue
from itertools import groupby
from operator import attrgetter
from threading import Timer
sys.path.append(sys.path[0]+'/../lib/')
from agent import Agent
from datalogger import DataloggerListener
from datalogger import ECHELLE_INDEX_B, PRISM_INDEX_B, LORES_INDEX_B
from datalogger import ECHELLE_INDEX_R, PRISM_INDEX_R, LORES_INDEX_R
from m2fsConfig import m2fsConfig
from SelectedConnection import SelectedSocket
import logging
LOGGING_LEVEL=logging.DEBUG

DATALOGGER_VERSION_STRING='Datalogger Agent v0.1'
POLL_AGENTS_INTERVAL=60.0
READING_EXPIRE_INTERVAL=75.0

class Unmergable(Exception):
    pass

class LoggerRecord(object):
    """
    A timestamped record containing temperatures and/or accelerations
    
    Initialize with the raw data string (following the L and num bytes sent)
    sent from the datalogger. Throws ValueError if the data does not parse into
    a valid record.
    
    Has the attributes:
    temps - None or a list of floats in the order sent by the datalogger
    accels - None or a numpy 32x3 array of accelerations in Gs with the 
    FIRST?LAST?TODO
    taken at approximately the timestamp and the remainder preceeding at
    intervals of 40 ms. 3 element dimension consists of x, y, & z axes.
    unixtime - The unixtime the of the record
    millis - The number of miliseconds into the day
    
    Implements the magic function __str__
    """
    @staticmethod
    def fromDataloggerRecord(side, dlRecord):
        if dlRecord.temps:
            if side == 'R':
                echelleTemp=dlRecord.temps[ECHELLE_INDEX_R]
                prismTemp=dlRecord.temps[PRISM_INDEX_R]
                loresTemp=dlRecord.temps[LORES_INDEX_R]
            else:
                echelleTemp=dlRecord.temps[ECHELLE_INDEX_B]
                prismTemp=dlRecord.temps[PRISM_INDEX_B]
                loresTemp=dlRecord.temps[LORES_INDEX_B]
        else:
            echelleTemp=None
            prismTemp=None
            loresTemp=None
        if side=='R':
            return LoggerRecord(dlRecord.unixtime,
                                echelleRTemp=echelleTemp,
                                prismRTemp=prismTemp,
                                loresRTemp=loresTemp,
                                accelsR=dlRecord.accels)
        elif side =='B':
            return LoggerRecord(dlRecord.unixtime,
                                echelleBTemp=echelleTemp,
                                prismBTemp=prismTemp,
                                loresBTemp=loresTemp,
                                accelsB=dlRecord.accels)
        raise ValueError('Side must be R or B')
    
    def __init__(self, timestamp, shackhartmanTemp=None,
                        cradleRTemp=None, cradleBTemp=None,
                        echelleRTemp=None, echelleBTemp=None,
                        prismRTemp=None, prismBTemp=None,
                        loresRTemp=None, loresBTemp=None,
                        accelsR=None, accelsB=None):
        self.unixtime=timestamp
        self.shackhartmanTemp=shackhartmanTemp
        self.sideR={'cradleTemp':cradleRTemp, 'echelleTemp':echelleRTemp,
            'prismTemp':prismRTemp, 'loresTemp':loresRTemp, 'accels':accelsR}
        self.sideB={'cradleTemp':cradleBTemp, 'echelleTemp':echelleBTemp,
            'prismTemp':prismBTemp, 'loresTemp':loresBTemp, 'accels':accelsB}
    
    def __str__(self):
        timestr=time.strftime("%a, %d %b %Y %H:%M:%S",
                              time.localtime(self.unixtime))
        temps=self.tempsString()
        accels=self.accelsString()
        return ' '.join([timestr, temps, accels])
    
    def accelsString(self):
        """ Return a space delimited string of acceleration values with side """
        if self.sideB['accels'] != None:
            return 'B\n'+str(self.sideB['accels'])
        elif self.sideR['accels'] != None:
            return 'R\n'+str(self.sideR['accels'])
        else:
            return 'No Accels'
    
    def tempsString(self):
        """ Return a space deleimted string of the temps or 'None' """
        temps=[self.shackhartmanTemp,
               self.sideR['cradleTemp'], self.sideB['cradleTemp'],
               self.sideR['echelleTemp'], self.sideB['echelleTemp'],
               self.sideR['prismTemp'], self.sideB['prismTemp'],
               self.sideR['loresTemp'], self.sideB['loresTemp']]
        temps=['{:.4f}'.format(t) if t != None else 'UNKNOWN' for t in temps]
        return ' '.join(temps)

    def recordsMergable(self, other):
        """
        Combines the records if they record different data, are both for the
        same minute. If they both contain accelerometer data, then they may not
        be merged
        """
        if self.shackhartmanTemp and other.shackhartmanTemp:
            return False
        for k in self.sideR.keys():
            if self.sideR[k] != None and other.sideR[k] != None:
                return False
        for k in self.sideB.keys():
            if self.sideB[k] != None and other.sideB[k] != None:
                return False
        #Ensure both don't contain acceleration data
        if (self.sideR['accels'] and other.sideB['accels'] or
            self.sideB['accels'] and other.sideR['accels']):
            return False
        if int(other.unixtime)/60 != int(self.unixtime)/60:
            return False
        return True
    
    def merge(self, other, force=False):
        """
        Merge other with this record if appropriate or throw ValueError
        
        If Force is true (default false) all set values are merged into self
        """
        if not force and not self.recordsMergable(other):
            raise Unmergable()
        # acceleration timestamp has priority
        if (not force and (other.sideR['accels'] != None or
                          other.sideB['accels'] != None)):
                self.unixtime=other.unixtime
        for k,v in other.sideB.items():
            if v != None:
                self.sideB[k]=v
        for k,v in other.sideR.items():
            if v != None:
                self.sideR[k]=v

class DataloggerAgent(Agent):
    """
    This is the M2FS Datalogger Agent. It gatheres temperature and accelerometer
    data from various sensors in the instrument and both maintains a record of
    the current temp readings and logs all the data to disk.
    """
    def __init__(self):
        Agent.__init__(self,'DataloggerAgent')
        #Initialize the dataloggers
        self.dataloggerRQueue=Queue.Queue()
        self.dataloggerR=DataloggerListener('/dev/dataloggerR', self.dataloggerRQueue)
        self.dataloggerR.start()
        self.dataloggerBQueue=Queue.Queue()
        self.dataloggerB=DataloggerListener('/dev/dataloggerB', self.dataloggerBQueue)
        self.dataloggerB.start()
        agent_ports=m2fsConfig.getAgentPorts()
        self.agentsQueue=Queue.Queue()
        self.shoeR=SelectedSocket('localhost', agent_ports['ShoeAgentR'])
        self.shoeB=SelectedSocket('localhost', agent_ports['ShoeAgentB'])
        self.shackHartman=SelectedSocket('localhost',
                                         agent_ports['ShackHartmanAgent'])
        self.logfile=m2fsConfig.getDataloggerLogfileName()
        self.currentRecord=LoggerRecord(time.time())
        self.command_handlers.update({
            #Return a list of the temperature values
            'TEMPS':self.TEMPS_command_handler})
        #self.logger.setLevel(LOGGING_LEVEL)
    
    def get_version_string(self):
        return DATALOGGER_VERSION_STRING
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the M2FS datalogger"
    
    def TEMPS_command_handler(self, command):
        """ Report the current temperatures """
        command.setReply(self.currentRecord.tempsString())
    
    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pair name:cookie
        """
        return [(self.get_version_string(),self.cookie)]
    
    def runSetup(self):
        """ execute before main loop """
        self.queryAgentsTimer=threading.Timer(POLL_AGENTS_INTERVAL,
                                              self.queryAgentTemps)
        self.queryAgentsTimer.daemon=True
        self.queryAgentsTimer.start()
    
    def run(self):
        """
        Called once per main loop, after select & any handlers but
            before closing out commands.
        
        Grab any data from the dataloggers that is in the queues, compile it
        and add it to the database.
        """
        records=[]
        #Get all the new Datalogger records into Logger records
        try:
            while True:
                records.append(LoggerRecord.fromDataloggerRecord(
                                'B', self.dataloggerBQueue.get_nowait()))
        except Queue.Empty:
            pass
        try:
            while True:
                records.append(LoggerRecord.fromDataloggerRecord(
                                 'R', self.dataloggerRQueue.get_nowait()))
        except Queue.Empty:
            pass
        #Get all the agent records, this should never be more that one
        try:
            while True:
                records.append(self.agentsQueue.get_nowait())
        except Queue.Empty:
            pass
        #Cases
        #1) Got nothing -> do nothing
        #2) Got something from one source, sort them try updating current state
        # with most recent, and log the records
        #3) Got something from multiple sources, sort them, merge any that can
        # be merged, update current state with most recent of each source, and
        #log
        records.sort(key=attrgetter('unixtime'))
        for minute, group in groupby(records, lambda x: int(x.unixtime)/60):
            recordGroup=list(group)
            #Cases:
            # 1) One record this minute, do nothing, we will log it later
            # 2) Multiple records this minute, attempt to merge, keep merged and
            # any that don't merge
            if len(recordGroup) == 1:
                pass
            else:
                for record in recordGroup[1:]:
                    try:
                        recordGroup[0].merge(record)
                        records.drop(record)
                    except Unmergable:
                        pass
            mostRecentRecord=recordGroup[0]
        if records:
            self.updateCurrentReadingsWith(mostRecentRecord)
            self.logRecords(records)
            
    def updateCurrentReadingsWith(self, record):
        """
        Update the live state with the data in the record. Ignore old records.
        
        Sensor readings are updated with values in the record if they have newer
        timestamps. Time stamps of records are maintained on a per sensor basis.
        
        READING_EXPIRE_INTERVAL current if it is within a minute of the
        current record timestaonlythe readings, extract it and add
        """
        self.logger.debug('Prep update current record: %s' % str(self.currentRecord))
        timeDelta=record.unixtime-self.currentRecord.unixtime
        if timeDelta > READING_EXPIRE_INTERVAL:
            self.currentRecord=record
        elif timeDelta >= 0:
            self.currentRecord.merge(record,force=True)
        else:
            self.logger.debug('No update to record') #we don't wan't old data
            return
        #Don't keep track of accelerations
        self.currentRecord.sideB['accels']=None
        self.currentRecord.sideR['accels']=None
        self.logger.info('Current record now: %s' % str(self.currentRecord))
    
    def logRecords(self, records):
        """
        Write all the LoggerRecords in records to the log file
        """
        with open(self.logfile,'a') as file:
            for r in records:
                self.logger.debug('Logging: %s' % str(r))
                file.write(str(r)+'\n')
    
    def queryAgentTemps(self):
        try:
            self.shoeR.connect() #in case we lost connection
            self.shoeR.sendMessageBlocking('SLITS_TEMP')
            cradleRTemp=float(self.shoeR.receiveMessageBlocking())
        except IOError:
            self.logger.debug("Failed to poll shoeR for temp")
            cradleRTemp=None
        except ValueError:
            cradleRTemp=None
        try:
            self.shoeB.connect()
            self.shoeB.sendMessageBlocking('SLITS_TEMP')
            cradleBTemp=float(self.shoeB.receiveMessageBlocking())
        except IOError:
            self.logger.debug("Failed to poll shoeB for temp")
            cradleBTemp=None
        except ValueError:
            cradleBTemp=None
        try:
            self.shackHartman.connect()
            self.shackHartman.sendMessageBlocking('TEMP')
            shTemp=float(self.shackHartman.receiveMessageBlocking())
        except IOError:
            self.logger.debug("Failed to poll S-H for temp")
            shTemp=None
        except ValueError:
            shTemp=None
        #Create a record and stick it in the queue
        self.agentsQueue.put(LoggerRecord(time.time(),
                                         shackhartmanTemp=shTemp,
                                         cradleRTemp=cradleRTemp,
                                         cradleBTemp=cradleBTemp))
        #Do it again in in a few
        self.queryAgentsTimer=Timer(POLL_AGENTS_INTERVAL, self.queryAgentTemps)
        self.queryAgentsTimer.daemon=True
        self.queryAgentsTimer.start()

if __name__=='__main__':
    agent=DataloggerAgent()
    agent.main()

