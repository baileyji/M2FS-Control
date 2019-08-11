#!/usr/bin/env python2.7
import sys, socket, time
sys.path.append(sys.path[0]+'/../lib/')

from agent import Agent
import m2fsConfig

IFUCAL_AGENT_VERSION_STRING = 'IFUCal Agent v1.0'

ARDUINO_BOOT_TIME = .1
EXPECTED_IFUCAL_INO_VERSION = 1

COLORS = ('392', '407', 'whi', '740', '770', '875')
HVLAMPS = ('thar', 'thne', 'hg', 'ne', 'he')
TEMPS = ('stage', 'lsb', 'hsb', 'msb')
MAXLEVEL = {'392': 4096, '407': 4096, 'whi': 4096, '740': 2048, '770': 2048, '875': 2048,
            'ThAr':7, 'ThNe':7, 'Hg':7, 'Ne':7, 'He':7}


class IFUArduinoSerial(SelectedConnection.SelectedSerial):
    """
    Tetris Shoe Controller Connection Class

    This class extents the SelectedSerial implementation of SelectedConnection
    with custom implementations of _postConnect and
    _implementationSpecificDisconnect.

    The _postConnect hook is used to verify the shoe is running a compatible
    firmware version. EXPECTED_FIBERSHOE_INO_VERSION should match the define for
    VERSION_STRING in fibershoe.ino

    _implementationSpecificDisconnect is overridden to guarantee the shoe is
    told to power down whenever the serial connection closes.
    """

    def _preConnect(self):
        """
        Attempt at workaround for
        https://bugs.launchpad.net/digitemp/+bug/920959
        """
        try:
            from subprocess import call
            s = 'stty crtscts < {device};stty -crtscts < {device}'.format(device=self.port)
            ret = call(s, shell=True)
        except Exception, e:
            raise SelectedConnection.ConnectError('rtscts hack failed. {}:{}:{}'.format(s, ret, str(e)))

    def _postConnect(self):
        """
        Implement the post-connect hook

        With the shoe we need verify the firmware version. If if doesn't match
        the expected version fail with a ConnectError.
        """
        # Shoe takes a few seconds to boot
        time.sleep(ARDUINO_BOOT_TIME)
        # verify the firmware version
        self.sendMessageBlocking('PV')
        response = self.receiveMessageBlocking()
        self.receiveMessageBlocking(nBytes=1)  # discard the :
        if response != EXPECTED_IFUCAL_INO_VERSION:
            error_message = ("Incompatible Firmware, Arduino reported '%s' , expected '%s'." %
                             (response, EXPECTED_IFUCAL_INO_VERSION))
            raise SelectedConnection.ConnectError(error_message)

        #TODO update various lamp statues
        self.sendMessageBlocking('LE ?')
        ledstat = self.receiveMessageBlocking(nBytes=30)
        self.sendMessageBlocking('HV ?')
        hvstat = self.receiveMessageBlocking()  #?=bytes in current value
        self.sendMessageBlocking('TE')
        temps = self.receiveMessageBlocking()

    def _implementationSpecificDisconnect(self):
        """ Disconnect the serial connection, telling the shoe to disconnect """
        try:
            self.connection.write('HV50\n')  #5th lamp is no lamp, current value ignored
            self.connection.write('LE*0\n')

            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except Exception, e:
            pass


class IFUCalAgent(Agent):
    """
    This program is responsible for the c
    """
    def __init__(self):
        Agent.__init__(self, 'IFUCalAgent')
        self.max_clients = 1
        self.connections['ifucal'] = IFUArduinoSerial() #TODO finish
        self.colors = COLORS
        self.hvlamps = HVLAMPS
        self.ledValue = {c: 0  for c in self.colors}
        self.hvValue = {c: 0 for c in self.hvlamps}
        self.temps = {t: 999 for t in TEMPS}  #TODO is this needed
        self.max_clients = 2
        self.command_handlers.update({
            # Get/Set state of HV lamps
            'THAR': self.HV_command_handler,   #response: {OK,ERROR,#}
            'THNE': self.HV_command_handler,
            'HE': self.HV_command_handler,
            'HG': self.HV_command_handler,
            'NE': self.HV_command_handler,
            # Get/Set state of LEDs
            'MCLED': self.MCLED_command_handler, #response:{ OK,ERROR, # # # # # #}
            #Report all the temps
            'TEMPS': self.TEMPS_command_handler)  #response:{  # # # # # #}

    def get_version_string(self):
        """ Return a string with the version."""
        return IFUCAL_AGENT_VERSION_STRING
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the IFUCalLED agent. It controls the IFU-M LED and HV lamp unit and fetches temps in IFU-M."

    def TEMPS_command_handler(self, command):
        """
        Handle getting the temp sensor readings in IFU-M, respond with temps or UNKNOWN
        """
        try:
            self.sendMessageBlocking('TE')
            command.setReply(self.receiveMessageBlocking())
            self.receiveMessageBlocking(nBytes=1)  # grab ack. :
        except IOError:
            command.setReply('UNKNOWN')

    def MCLED_command_handler(self, command):
        """
        Handle geting/setting the LED illumination value 
        
        Valid command string argument is a number from 0 to 4096

        UV BLUE WHITE 740 770 875
        
        If we are getting, just report the most recently set value, if setting 
        convert the command argument to a single byte and send that to the SH 
        led. Respond OK or error as appropriate.
        """
        #TODO exception handling, disconnects error reporting etc
        if '?' in command.string:
            self.sendMessageBlocking('LE?')
            ledstat = self.receiveMessageBlocking() #30 bytes
            self.receiveMessageBlocking(nBytes=1) #grab ack. :
            command.setReply(ledstat)
        else:
            #Set the LED brightness 0-4096
            command_parts = command.string.split(' ')
            try:
                values = map(int, command_parts[1:])
                commands = ['LE{}{}'.format(i+1, val) for i, val in enumerate(values)]
                if len(commands) != 6:
                    raise IndexError
                for c in commands:
                    self.sendMessageBlocking(c)
                    if self.receiveMessageBlocking(nBytes=1) != ':':
                        self.logger.error('IFU Shield did not acknowledge command')
                        raise IOError('IFU Shield did not acknowledge command')
                command.setReply('OK')
            except (ValueError, IndexError):
                self.bad_command_handler(command)
            except IOError:
                command.setReply('ERROR: IFUCal Disconnected')

    def HV_command_handler(self, command):
        """
        Handle geting/setting the HV lamps

        Valid command string is a lamp name followed by a current value

        Respond OK or error as appropriate.
        """
        # TODO exception handling, disconnects error reporting etc
        if '?' in command.string:
            self.sendMessageBlocking('HV?')
            reply = self.receiveMessageBlocking()  # 30 bytes
            self.receiveMessageBlocking(nBytes=1)  # grab ack. :
            hvstat = reply.split()
            if len(hvstat)!=len(self.hvlamps):
                err = 'Malformed reply to HV? "{}"'.format(reply)
                command.setReply('ERROR: '+ err)
                #TODO probably should disconnect and reconnect or trigger some sort of reset process
            else:
                val = {l:v for l,v in zip(self.hvlamps,hvstat)}[command.string.split()[0].lower()]
                command.setReply(val)
        else:  #Activate the appropriate HV lamp
            command_parts = command.string.split(' ')
            try:
                lamp_num = self.hvlamps.index(command_parts[0].lower())
                current=int(command_parts[1])
                self.sendMessageBlocking('HV{}{}'.format(lamp_num, current))
                resp = self.receiveMessageBlocking(nBytes=1)  # grab ack. :
                if resp != ':':
                    #todo handle error
                command.setReply('OK')
            except (ValueError, IndexError):
                self.bad_command_handler(command)
            except IOError:
                command.setReply('ERROR: IFUCal Disconnected')

    def get_status_list(self):
        """ 
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pairs name:cookie, color:value
        """
        #TODO vet & test
        try:
            self.sendMessageBlocking('LE?')
            reply = self.receiveMessageBlocking()
            self.receiveMessageBlocking(nBytes=1)  # grab ack. :
            ledstat = reply.split()
            if len(ledstat)!=len(self.colors):
                raise IOError('Malformed reply to LE? "{}"'.format(reply))
        except Exception, e:
            self.logger.error('Unable to fetch led values: "{}"'.format(e))

        try:
            self.sendMessageBlocking('HV?')
            reply = self.receiveMessageBlocking()
            self.receiveMessageBlocking(nBytes=1)  # grab ack. :
            hvstat = reply.split()
            if len(hvstat)!=len(self.hvlamps):
                raise IOError('Malformed reply to HV? "{}"'.format(reply))
        except Exception, e:
            self.logger.error('Unable to fetch HV values: "{}"'.format(e))

        return ([(self.get_version_string(), self.cookie)] +
                [(str(c), str(v)) for c,v in zip(self.colors, ledstat)] +
                [(str(c), str(v)) for c,v in zip(self.hvlamps, hvstat)])


if __name__=='__main__':
    agent=IFUCalAgent()
    agent.main()
