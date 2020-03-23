#!/usr/bin/env python2.7
import Queue

from threading import Timer
from datetime import datetime, timedelta
from m2fscontrol.agent import Agent
from m2fscontrol.datalogger import DataloggerListener
from m2fscontrol.m2fsConfig import M2FSConfig, N_IFU_TEMPS
from m2fscontrol.selectedconnection import SelectedSocket
import logging
from m2fscontrol.loggerrecord import *

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
        self.redis_ts = self.redis.time_series('temps', ['temp_stream'])
        self.redis_stream = self.redis_ts.temp_stream
        self.dataloggerR=DataloggerListener('R','/dev/m2fs_dataloggerR', self.redis)
        self.dataloggerR.start()
        self.dataloggerB=DataloggerListener('B', '/dev/m2fs_dataloggerB', self.redis)
        self.dataloggerB.start()
        agent_ports=M2FSConfig.getAgentPorts()
        if M2FSConfig.ifum_devices_present(): #TODO make this support user forgetfullness
            self.ifushoes = SelectedSocket('localhost', agent_ports['IFUShoeAgent'])
            self.ifuselector = SelectedSocket('localhost', agent_ports['SelectorAgent'])
            self.ifushield = SelectedSocket('localhost', agent_ports['IFUShieldAgent'])
        else:
            self.shoeR=SelectedSocket('localhost', agent_ports['ShoeAgentR'])
            self.shoeB=SelectedSocket('localhost', agent_ports['ShoeAgentB'])
            self.shackHartman=SelectedSocket('localhost', agent_ports['ShackHartmanAgent'])

        self.command_handlers.update({
            #Return a list of the temperature values
            'TEMPS': self.TEMPS_command_handler})

        self.queryAgentsTimer=None

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

        latest = self.redis_stream[datetime.utcnow() - timedelta(minutes=1):]
        current = {}
        for r in latest:
            current.update(r.data)

        if M2FSConfig.ifum_devices_present():
            templist = ('ifuentrance', 'ifutop', 'ifufiberexit', 'ifumotor', 'ifudrive', 'ifuhoffman',
                        'shoebox', 'cradleR', 'cradleB', 'echelleR', 'echelleB', 'prismR', 'prismB',
                        'loresR', 'loresB')
        else:
            templist = ('sh', 'cradleR', 'cradleB', 'echelleR', 'echelleB', 'prismR', 'prismB', 'loresR', 'loresB')
        reply = ' '.join(['{:.3f}'.format(float(current[k])) if k in current else 'U' for k in templist])
        command.setReply(reply)

    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pair name:cookie
        """
        return [(self.get_version_string(), self.cookie)]

    def runSetup(self):
        """ execute before main loop """
        self.queryAgentsTimer=Timer(POLL_AGENTS_INTERVAL, self.logTemps)
        self.queryAgentsTimer.daemon=True
        self.queryAgentsTimer.start()

    def _gatherIFUTemps(self):
        try:
            cradleRTemp, cradleBTemp, shoeboxTemp = None, None, None
            self.ifushoes.connect()  # in case we lost connection
            self.ifushoes.sendMessageBlocking('SLITS_TEMP')
            resp = self.ifushoes.receiveMessageBlocking()

            def floatnone(x):
                try:
                    return float(x)
                except ValueError:
                    return None

            if 'busy' not in resp.lower():
                cradleRTemp, cradleBTemp, shoeboxTemp = map(floatnone, resp.split())
        except IOError:
            self.logger.debug("Failed to poll IFU Shoes for temps")

        try:
            driveTemp, motorTemp = None, None
            self.ifuselector.connect()  # in case we lost connection
            self.ifuselector.sendMessageBlocking('TEMP')
            resp = self.ifuselector.receiveMessageBlocking()
            driveTemp, motorTemp = map(float, resp.split())
        except IOError:
            self.logger.debug("Failed to poll selector for temps")
        except ValueError:
            self.logger.debug("Bad response '{}' from IFU selector for temps".format(resp))

        try:
            probe_temps = [None] * N_IFU_TEMPS
            self.ifushield.connect()  # in case we lost connection
            self.ifushield.sendMessageBlocking('TEMPS')
            resp = self.ifushield.receiveMessageBlocking()
            probe_temps = map(float, resp.split())
            if len(probe_temps) != N_IFU_TEMPS:
                raise ValueError('Incorrect number of probe temperatures received from IFU Shield')
        except IOError:
            self.logger.debug("Failed to poll IFUShield for temps")
        except ValueError:
            self.logger.debug("Bad response '{}' from IFU Shield for temps".format(resp))

        return cradleRTemp, cradleBTemp, shoeboxTemp, driveTemp, motorTemp, probe_temps

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

    def logTemps(self):
        #Gather Temps
        temps = dict(cradleR=None, cradleB=None, shoebox=None, ifudrive=None, ifumotor=None,
                     ifuentrance=None, ifufiberexit=None, ifutop=None, ifuhoffman=None, sh=None)
        if M2FSConfig.ifum_devices_present():
            cradleRTemp, cradleBTemp, shoeboxTemp, driveTemp, motorTemp, probeTemps = self._gatherIFUTemps()
            temps['cradleR'] = cradleRTemp
            temps['cradleB'] = cradleBTemp
            temps['shoebox'] = shoeboxTemp
            temps['ifudrive'] = driveTemp
            temps['ifumotor'] = motorTemp
            temps.update(m2fsConfig.ifuProbeTempsToDict(probeTemps))
        else:
            cradleRTemp, cradleBTemp, shTemp = self._gatherM2FSTemps()
            temps['cradleR'] = cradleRTemp
            temps['cradleB'] = cradleBTemp
            temps['sh'] = shTemp

        rec = {k: v for k, v in temps.items() if v is not None}
        self.redis_stream.add(rec, id=datetime.utcnow())

        #Do it again in in a few
        self.queryAgentsTimer=Timer(POLL_AGENTS_INTERVAL, self.queryAgentTemps)
        self.queryAgentsTimer.daemon=True
        self.queryAgentsTimer.start()


if __name__=='__main__':
    agent=DataloggerAgent()
    agent.main()

