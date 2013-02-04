#!/usr/bin/env python2.7
import sys, time, threading
from operator import attrgetter
from threading import Timer
sys.path.append(sys.path[0]+'/../lib/')
from agent import Agent
import cPickle
from datalogger import Datalogger
from m2fsConfig import m2fsConfig
from SelectedConnection import SelectedSocket

DATALOGGER_VERSION_STRING='Datalogger Agent v0.1'
POLL_SHOE_INTERVAL=60.0
POLL_SH_INTERVAL=60.0


class LoggerRecord(object):
    """
    A timestamped record containing temperatures and/or accelerations
    
    Initialize with the raw data string (following the L and num bytes sent)
    sent from the datalogger. Throws ValueError if the data does not parse into
    a valid record.
    
    Has the attributes:
    temps - None or a list of floats in the order sent by the datalogger
    accels - None or a numpy 32x3 array of accelerations in Gs with the FIRST?LAST?TODO
    taken at approximately the timestamp and the remainder preceeding at
    intervals of 40 ms. 3 element dimension consists of x, y, & z axes.
    unixtime - The unixtime the of the record
    millis - The number of miliseconds into the day
    
    Implements the magic function __str__
    """
    def __init__(self, timestamp,
                        shackhartmanTemp=None,
                        cradleRTemp=None,
                        cradleBTemp=None,
                        echelleRTemp=None,
                        echelleBTemp=None,
                        prismRTemp=None,
                        prismBTemp=None,
                        loresRTemp=None,
                        loresBTemp=None,
                        accelsR=None,
                        accelsB=None):
        self.unixtime=timestamp
        self.shackhartmanTemp=shackhartmanTemp
        self.cradleRTemp=cradleRTemp
        self.cradleBTemp=cradleBTemp
        self.echelleRTemp=echelleRTemp
        self.echelleBTemp=echelleBTemp
        self.prismRTemp=prismRTemp
        self.prismBTemp=prismBTemp
        self.loresRTemp=loresRTemp
        self.loresBTemp=loresBTemp
        self.accelsR=accelsR
        self.accelsB=accelsB
    
    @staticmethod
    def fromDataloggerRecord(side, dlRecord):
        if side=='R':
            return LoggerRecord(dlRecord.unixtime,
                                echelleRTemp=dlRecord.temps[ECHELLE_INDEX],
                                prismRTemp=dlRecord.temps[PRISIM_INDEX],
                                loresRTemp=dlRecord.temps[LORES_INDEX],
                                accelsR=dlRecord.accels)
        elif side =='B':
            return LoggerRecord(dlRecord.unixtime,
                                echelleBTemp=dlRecord.temps[ECHELLE_INDEX],
                                prismBTemp=dlRecord.temps[PRISIM_INDEX],
                                loresBTemp=dlRecord.temps[LORES_INDEX],
                                accelsB=dlRecord.accels)
        raise ValueError('Side must be R or B')
    
    def __str__(self):
        kind
        
        timestr=time.strftime("%a, %d %b %Y %H:%M:%S",
                              time.localtime(self.unixtime))
        return ' '.join([string,timestr,str(self.millis/1000.0)])
    
    def tempsString(self):
        """ Return a space deleimted string of the temps or 'None' """
        return ' '.join(map(str, [self.shackhartmanTemp,
                                  self.cradleRTemp,
                                  self.cradleBTemp,
                                  self.echelleRTemp,
                                  self.echelleBTemp,
                                  self.prismRTemp,
                                  self.prismBTemp,
                                  self.loresRTemp,
                                  self.loresBTemp])
    
    def merge(self, other):
        """
        Merge other with this record if appropriate or throw ValueError
        
        Combines the records if they record different data, are both for the
        same minute. If they both contain accelerometer data, then they may not
        be merged        
        """
        for attribute in other != None
            if attribute in self != None:
                raise ValueError('Records record same data')
        if self.accelsR and other.accelsB or self.accelsB and other.accelsR:
                raise ValueError('Records both record acceleration data')
        
        if int(other.unixtime)/60 == int(self.unixtime)/60:
             # acceleration timestamp has priority
            if other.accelsB or other.accelsR:
                self.unixtime=other.unixtime
            for attribute in other !=None:
                set attribute in self to value of attribute in other


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
        DataloggerListener('/dev/dataloggerR', self.dataloggerRQueue)
        self.dataloggerBQueue=Queue.Queue()
        DataloggerListener('/dev/dataloggerB', self.dataloggerBQueue)
        agent_ports=m2fsConfig.getAgentPorts()
        self.agentsQueue=Queue.Queue()
        self.shoeR=SelectedSocket('localhost', agent_ports['ShoeAgentR'])
        self.shoeB=SelectedSocket('localhost', agent_ports['ShoeAgentB']),
        self.shackHartman=SelectedSocket('localhost', agent_ports['ShackHartman'])
        self.logFile=open(=m2fsConfig.getDataloggerLogfileName(),'a')
        self.command_handlers.update({
            #Return a list of the temperature values
            'TEMPS':self.TEMPS_command_handler})
    
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
        command.setReply(self.getStringOfCurrentTemps())
    
    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pair name:cookie
        """
        return [(self.get_version_string(),self.cookie)]
    
    def getStringOfCurrentTemps(self):
        """ Return a space delimited list of the current temperatures """
        temps=self.currentTemps.values()
        return ''.join((len(temps)*"%f ")%temps)
    
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
                                'B', dataloggerBQueue.get_nowait()))
        except Queue.Empty:
            pass
        try:
            while True:
                records.append(LoggerRecord.fromDataloggerRecord(
                                 'R', dataloggerRQueue.get_nowait()))
        except Queue.Empty:
            pass
        
        #Get all the agent records, this should never be more that one
        try:
            while True:
                records.append(self.agentsQueue.get_nowait()))
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
        for minute, group in groupby(records, lambda x: int(x.unixtime)/60)
            #Cases:
            # 1) One record this minute, do nothing, we will log it later
            # 2) Multiple records this minute, attempt to merge, keep merged and
            # any that don't merge
            if len(group) == 1:
                pass
            else:
                for record in group[1:]:
                    try:
                        group[0].merge(record)
                        records.drop(record)
                    except ValueError:
                        pass
            mostRecentRecord=group[0]
        if records:
            self.updateCurrentReadingsWith(mostRecentRecord)
            self.logRecords(records)
            
    def updateCurrentReadingsWith(self,record):
        """
        Update the live state with the data in the record. Ignore old records.
        
        Sensor readings are updated with values in the record if they have newer
        timestamps. Time stamps of records are maintained on a per sensor basis.
        
          READING_EXPIRE_TIME current if it is within a minute of the
        current record timestaonlythe readings, extract it and add
        """
        pass
    
    def logRecords(self, records):
        """
        Write all the LoggerRecords in records to the log file
        
        
    
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
        self.queryAgentsTimer=Timer(POLL_AGENT_INTERVAL, self.queryAgentTemps)
        self.queryAgentsTimer.daemon=True
        self.queryAgentsTimer.start()
        
    def on_exit(self, arg):
        """Prepare to exit"""
        self.logFile.close()
        Agent.on_exit(self, arg)

if __name__=='__main__':
    agent=DataloggerAgent()
    agent.main()

