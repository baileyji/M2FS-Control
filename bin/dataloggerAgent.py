#!/usr/bin/env python2.7
import sys, time, threading, Queue
from itertools import groupby
from operator import attrgetter
from threading import Timer
sys.path.append(sys.path[0]+'/../lib/')
from agent import Agent
from datalogger import DataloggerListener
from m2fsConfig import N_IFU_TEMPS
from m2fsConfig import m2fsConfig
from SelectedConnection import SelectedSocket
import logging
from LoggerRecord import *

LOGGING_LEVEL=logging.DEBUG  #This will not have any effect if it is more aggressive than the conf file

DATALOGGER_VERSION_STRING='Datalogger Agent v1.0'
POLL_AGENTS_INTERVAL=60.0
READING_EXPIRE_INTERVAL=120.0


def logDebugInfo(logger, records):
    """ Records should be sorted in time """
    if len(records) <3:
        for r in records:
            logger.debug(r.prettyStr())
    else:
        bCount=0
        rCount=0
        for r in records:
            if r.bOnly():
                bCount+=1
            elif r.rOnly():
                rCount+=1
        logger.debug("R records: %i  B records: %i" % (rCount, bCount))
        logger.debug("Earliest: %s Latest: %s" %
                     (records[0].timeString(), records[-1].timeString()))


class DataloggerAgent(Agent):
    """
    This is the M2FS Datalogger Agent. It gatheres temperature and accelerometer
    data from various sensors in the instrument and both maintains a record of
    the current temp readings and logs all the data to disk.
    """
    def __init__(self):
        Agent.__init__(self,'DataloggerAgent')
        #Initialize the dataloggers
        self.recordQueue=Queue.Queue()
        self.dataloggerR=DataloggerListener('R','/dev/dataloggerR', self.recordQueue)
        self.dataloggerR.start()
        self.dataloggerB=DataloggerListener('B', '/dev/dataloggerB', self.recordQueue)
        self.dataloggerB.start()
        agent_ports=m2fsConfig.getAgentPorts()
        if m2fsConfig.ifum_devices_present(): #TODO make this support user forgetfullness
            self.ifushoes = SelectedSocket('localhost', agent_ports['IFUShoeAgent'])
            self.ifuselector = SelectedSocket('localhost', agent_ports['SelectorAgent'])
            self.ifushield = SelectedSocket('localhost', agent_ports['IFUShieldAgent'])
        else:
            self.shoeR=SelectedSocket('localhost', agent_ports['ShoeAgentR'])
            self.shoeB=SelectedSocket('localhost', agent_ports['ShoeAgentB'])
            self.shackHartman=SelectedSocket('localhost', agent_ports['ShackHartmanAgent'])
        self.logfile=open(m2fsConfig.getDataloggerLogfileName(),'a')
        self.currentRecord=LoggerRecord(time.time())
        self.command_handlers.update({
            #Return a list of the temperature values
            'TEMPS': self.TEMPS_command_handler})

        self.queryAgentsTimer=None
        self.bUpdateTime=0
        self.rUpdateTime=0
        self.shUpdateTime=0
        self.ifuUpdateTime=0

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
        self.queryAgentsTimer=Timer(POLL_AGENTS_INTERVAL, self.queryAgentTemps)
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
        #Get all the new records
        try:
            while True:
                records.append(self.recordQueue.get_nowait())
        except Queue.Empty:
            pass
        #Cases
        #1) Got nothing -> do nothing
        #2) Got something from one source, sort them try updating current state
        # with most recent, and log the records
        #3) Got something from multiple sources, sort them, merge any that can
        # be merged, update current state with most recent of each source, and
        #log
        if len(records)>0:
            self.logger.debug('Have {} records'.format(len(records)))
        logMerge=len(records) > 1
        records.sort(key=attrgetter('unixtime'))
        toRemove=[]
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
                        toRemove.append(record)
                    except Unmergable:
                        pass
        if toRemove:
            map(records.remove, toRemove)
        if logMerge:
            self.logger.debug('Have {} records after merging'.format(len(records)))
        if records:
            logDebugInfo(self.logger, records)
            self.updateCurrentReadingsWith(records[-1])
            self.logRecords(records)

    def updateCurrentReadingsWith(self, record):
        """
        Update the live state with the data in the record. Ignore old records.
        
        Sensor readings are updated with values in the record if they have newer
        timestamps. Time stamps of records are maintained on a per sensor basis.
        
        READING_EXPIRE_INTERVAL current if it is within a minute of the
        current record timestaonlythe readings, extract it and add
        """
        timeDelta=record.unixtime-self.currentRecord.unixtime

        if False or timeDelta < 0:
            #we don't wan't old data
            self.logger.debug('Current record newer than update (%s) ' % self.currentRecord.timeString())
            return
        else:
            if timeDelta < 0:
                self.logger.debug('Updating record with "older" data ({}) delta'.format(timeDelta))

            #update the timestamps for the data
            if record.haveBData():
                self.bUpdateTime=record.unixtime
            if record.haveRData():
                self.rUpdateTime=record.unixtime
            if record.haveSHData():
                self.shUpdateTime=record.unixtime
            if record.haveIFUMData():
                self.ifuUpdateTime=record.unixtime

            #Merge in the new data, replacing the old
            self.logger.debug('Current record was: %s' % self.currentRecord.prettyStr())
            self.currentRecord.merge(record, force=True)

            #Adopt the new time
            self.currentRecord.unixtime=record.unixtime

            #Clear out any data that is too old
            if (self.currentRecord.unixtime - self.rUpdateTime) > READING_EXPIRE_INTERVAL:
                self.logger.debug('R values expired, clearing')
                for k in self.currentRecord.sideR:
                    self.currentRecord.sideR[k]=None

            if (self.currentRecord.unixtime - self.bUpdateTime) > READING_EXPIRE_INTERVAL:
                self.logger.debug('B values expired, clearing')
                for k in self.currentRecord.sideB:
                    self.currentRecord.sideB[k]=None

            if (self.currentRecord.unixtime - self.shUpdateTime) > READING_EXPIRE_INTERVAL:
                self.logger.debug('SH value expired, clearing')
                self.currentRecord.shackhartmanTemp=None

            if (self.currentRecord.unixtime - self.ifuUpdateTime) > READING_EXPIRE_INTERVAL:
                self.logger.debug('IFU value expired, clearing')
                for k in self.currentRecord.ifu:
                    self.currentRecord.ifu[k]=None

            #Don't keep track of accelerations
            self.currentRecord.sideB['accels']=None
            self.currentRecord.sideR['accels']=None

            #Log the result
            self.logger.debug('Current record now: %s' % self.currentRecord.prettyStr())

    def logRecords(self, records):
        """
        Write all the LoggerRecords in records to the log file
        """
        #with open(self.logfile,'a') as file:
        self.logger.debug('Logging {} records'.format(len(records)))
        for r in records:
            self.logfile.write(str(r)+'\n')

    def _exitHook(self):
        self.logfile.close()

    def _gatherIFUTemps(self):
        try:
            cradleRTemp, cradleBTemp = None, None
            self.ifushoes.connect()  # in case we lost connection
            self.ifushoes.sendMessageBlocking('SLITS_TEMP')
            resp = self.ifushoes.receiveMessageBlocking()
            cradleRTemp, cradleBTemp = map(float, resp.split())
        except IOError:
            self.logger.debug("Failed to poll IFU Shoes for temps")
        except ValueError:
            self.logger.debug("Bad response '{}'from IFU Shoes for temps".format(resp))

        try:
            driveTemp, motorTemp = None, None
            self.ifuselector.connect()  # in case we lost connection
            self.ifuselector.sendMessageBlocking('SELECTOR_TEMP')
            resp = self.ifuselector.receiveMessageBlocking()
            driveTemp, motorTemp = map(float, resp.split())
        except IOError:
            self.logger.debug("Failed to poll selector for temps")
        except ValueError:
            self.logger.debug("Bad response '{}' from IFU selector for temps".format(resp))

        try:
            probeTemps = [None] * N_IFU_TEMPS
            self.ifushield.connect()  # in case we lost connection
            self.ifushield.sendMessageBlocking('TEMPS')
            resp=self.ifushield.receiveMessageBlocking()
            probeTemps = map(float, resp.split())
            if len(probeTemps)!=N_IFU_TEMPS:
                raise ValueError
        except IOError:
            self.logger.debug("Failed to poll IFUShield for temps")
        except ValueError:
            self.logger.debug("Bad response '{}' from IFU Shield for temps".format(resp))

        return cradleRTemp, cradleBTemp, driveTemp, motorTemp, probeTemps

    def _gatherM2FSTemps(self):
        try:
            cradleRTemp = None
            self.shoeR.connect()  # in case we lost connection
            self.shoeR.sendMessageBlocking('SLITS_TEMP')
            cradleRTemp = float(self.shoeR.receiveMessageBlocking())
        except IOError:
            self.logger.debug("Failed to poll shoeR for temp")
        except ValueError:
            pass
        try:
            cradleBTemp = None
            self.shoeB.connect()
            self.shoeB.sendMessageBlocking('SLITS_TEMP')
            cradleBTemp = float(self.shoeB.receiveMessageBlocking())
        except IOError:
            self.logger.debug("Failed to poll shoeB for temp")
        except ValueError:
            pass
        try:
            shTemp = None
            self.shackHartman.connect()
            self.shackHartman.sendMessageBlocking('TEMP')
            shTemp = float(self.shackHartman.receiveMessageBlocking())
        except IOError:
            self.logger.debug("Failed to poll S-H for temp")
        except ValueError:
            pass

        return cradleRTemp, cradleBTemp, shTemp

    def queryAgentTemps(self):
        #Gather Temps
        if m2fsConfig.ifum_devices_present():
            shTemp = None
            cradleRTemp, cradleBTemp, driveTemp, motorTemp, probeTemps = self._gatherIFUTemps()
        else:
            driveTemp, motorTemp = None, None
            probeTemps = [None] * N_IFU_TEMPS
            cradleRTemp, cradleBTemp, shTemp = self._gatherM2FSTemps()

        #Create a record and stick it in the queue
        temps=[shTemp, cradleRTemp, cradleBTemp, driveTemp, motorTemp]
        temps.extend(probeTemps)
        if not all(v is None for v in temps):
            record=LoggerRecord(time.time(), shackhartmanTemp=shTemp, cradleRTemp=cradleRTemp, cradleBTemp=cradleBTemp,
                         ifuSelectorDriveTemp=driveTemp, ifuSelectorMotorTemp=motorTemp, ifuProbeTemps=probeTemps)
            self.recordQueue.put(record)
        #Do it again in in a few
        self.queryAgentsTimer=Timer(POLL_AGENTS_INTERVAL, self.queryAgentTemps)
        self.queryAgentsTimer.daemon=True
        self.queryAgentsTimer.start()

if __name__=='__main__':
    agent=DataloggerAgent()
    agent.main()

