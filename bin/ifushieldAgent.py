#!/usr/bin/env python2.7
import time
import m2fscontrol.selectedconnection as selectedconnection
from m2fscontrol.agent import Agent

IFUSHIELD_AGENT_VERSION_STRING = 'IFUShield Agent v1.0'

ARDUINO_BOOT_TIME = 1.3
EXPECTED_IFUSHIELD_INO_VERSION = '1.0'

COLORS = ('392', '407', 'whi', '740', '770', '875')

COLORS = ('770', '740', '875', 'whi', '407', '392')
HVLAMPS = ('thxe', 'benear', 'lihe')
TEMPS = ('stage', 'lsb', 'hsb', 'msb')

class IFUArduinoSerial(selectedconnection.SelectedSerial):
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
        """ Attempt at workaround for https://bugs.launchpad.net/digitemp/+bug/920959 """
        try:
            from subprocess import call
            s = 'stty crtscts < {device};stty -crtscts < {device}'.format(device=self.port)
            ret = call(s, shell=True)
        except Exception, e:
            raise selectedconnection.ConnectError('rtscts hack failed. {}:{}:{}'.format(s, ret, str(e)))

    def _postConnect(self):
        """
        Implement the post-connect hook

        With the shoe we need verify the firmware version. If if doesn't match
        the expected version fail with a ConnectError.
        """
        # Shoe takes a few seconds to boot
        time.sleep(ARDUINO_BOOT_TIME)

        #todo should this be flush input?
        while self.receiveMessageBlocking():
            pass
        # verify the firmware version
        self.sendMessageBlocking('PV')
        response = self.receiveMessageBlocking()
        self.receiveMessageBlocking(nBytes=1)  # discard the :
        if response != EXPECTED_IFUSHIELD_INO_VERSION:
            error_message = ("Incompatible Firmware, Arduino reported '%s' , expected '%s'." %
                             (response, EXPECTED_IFUSHIELD_INO_VERSION))
            raise selectedconnection.ConnectError(error_message)

    def _implementationSpecificDisconnect(self):
        """ Disconnect the serial connection, telling the shoe to disconnect """
        try:
            self.connection.write('OF\n')  #turn everything off
            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except Exception, e:
            pass


class IFUShieldAgent(Agent):
    """
    This program is responsible for the c
    """
    def __init__(self):
        Agent.__init__(self, 'IFUShieldAgent')
        self.connections['ifushield'] = IFUArduinoSerial(self.args.DEVICE, 115200, timeout=.5)
        self.max_clients = 2
        self.command_handlers.update({
            #TODO add raw
            'SHIELDRAW': self.RAW_command_handler,
            # Get/Set state of HV lamps
            'THXE': self.HV_command_handler,   #response: {OK,ERROR,#}
            'BENEAR': self.HV_command_handler,
            'LIHE': self.HV_command_handler,
            # Get/Set state of LEDs
            'MCLED': self.LED_command_handler, #response:{ OK,ERROR, # # # # # #}
            #Report all the temps
            'TEMPS': self.TEMPS_command_handler})  #response:{  # # # # # #}

    def add_additional_cli_arguments(self):
        """
        Additional CLI arguments may be added by implementing this function.

        Arguments should be added as:
        self.cli_parser.add_argument(See ArgumentParser.add_argument for syntax)
        """
        self.cli_parser.add_argument('--device', dest='DEVICE',
                                     action='store', required=False, type=str,
                                     help='the device to control', default='/dev/ifum_shield')

    def get_version_string(self):
        """ Return a string with the version. """
        return IFUSHIELD_AGENT_VERSION_STRING

    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.

        Subclasses should override this to provide a description for the cli
        parser
        """
        return "This is the IFUShield agent. It controls the IFU-M LED and HV lamp unit and fetches temps in IFU-M."

    def _send_command_to_shield(self, command_string):
        """
        Send a command string to the ifushield, wait for immediate response

        Silently ignore an empty command.

        Raise IOError if the command isn't acknowledged

        Procedure is as follows:
        Send the command string to the shield
        grab a singe byte from the shoe and if it isn't a : or a ? listen for
        a \n delimited response followed by a :.

        Return a string of the response to the commands.
        Note the : ? are not considered responses. ? gets the exception and :
        gets an empty string. The response is stripped of whitespace.
        """
        # No command, return
        if not command_string:
            return ''
        # Send the command(s)
        self.connections['ifushield'].sendMessageBlocking(command_string)
        # Get the first byte, this will be it for a simple ACK
        response = self.connections['ifushield'].receiveMessageBlocking(nBytes=1)
        # 3 cases:, :, ?, or stuff followed by \r\n:
        # case 1, command succeeds but returns nothing, return
        if response == ':':
            return ''
        elif response == '?':  # command failed
            raise IOError("ERROR: IFUShield did not acknowledge (gave ?) command {}".format(command_string))
        # command is returning something
        else:
            # do a blocking receive on \n
            response = response + self.connections['ifushield'].receiveMessageBlocking()
            # ...and a single byte read to grab the :
            confByte = self.connections['ifushield'].receiveMessageBlocking(nBytes=1)
            if confByte == ':':
                return response.strip()
            else:  # Consider it a failure, log it. Add the byte to the response for logging
                response += confByte
                err = ("IFUShield did not adhere to protocol. '%s' got '%s'" % (command_string, response))
                self.logger.warning(err)
                raise IOError('ERROR: %s' % err)

    def RAW_command_handler(self, command):
        """
        Send a raw string to the shoe and wait for a response

        NB the PC command can generate more than 1024 bytes of data
        """
        arg = command.string.partition(' ')[2]
        if arg:
            try:
                self.connections['ifushield'].sendMessageBlocking(arg)
                response = self.connections['ifushield'].receiveMessageBlocking(nBytes=2048)
                response = response.replace('\r', '\\r').replace('\n', '\\n')
            except IOError, e:
                response = 'ERROR: %s' % str(e)
            command.setReply(response)
        else:
            self.bad_command_handler(command)

    def TEMPS_command_handler(self, command):
        """
        Handle getting the temp sensor readings in IFU-M enclosure (except on the selector drive),
        respond with temps or UNKNOWN
        """
        if self.connections['ifushield'].rlock.acquire(False):
            try:
                response=self._send_command_to_shield('TE')
            except IOError, e:
                response='UNKNOWN'
            finally:
                self.connections['ifushield'].rlock.release()
        else:
            response='ERROR: Busy, try again'
        command.setReply(response)

    def LED_command_handler(self, command):
        """
        Handle geting/setting the LED illumination value

        Valid command string argument is a number from 0 to 4096

        UV BLUE WHITE 740 770 875

        If we are getting, just report the most recently set value, if setting
        convert the command argument to a single byte and send that to the SH
        led. Respond OK or error as appropriate.
        """
        if '?' in command.string:
            try:
                response = self._send_command_to_shield('LE?')
            except IOError as e:
                response = str(e)
            command.setReply(response)
        else:
            #Set the LED brightness 0-4096
            command_parts = command.string.split(' ')
            try:
                commands = ['LE{}{}'.format(i+1, val) for i, val in
                            enumerate(map(int, command_parts[1:]))]
                if len(commands) != len(COLORS):
                    raise IndexError
                for c in commands:
                    self._send_command_to_shield(c)
                response = 'OK'
            except (ValueError, IndexError):
                self.bad_command_handler(command)
                return
            except IOError as e:
                response = str(e)
                if not response.startswith('ERROR: '):
                    response = 'ERROR: ' + response
            command.setReply(response)

    def HV_command_handler(self, command):
        """
        Handle geting/setting the HV lamps

        Valid command string is a lamp name followed by a current value

        Respond OK or error as appropriate.
        """
        if '?' in command.string:
            try:
                response = self._send_command_to_shield('HV?')  #Per arduino order is BeNeAr LiHe ThXe
                hvstat = response.split()
                if len(hvstat) != len(HVLAMPS):
                    raise IOError('Bad response to HV? "{}", expected {} values'.format(response, len(HVLAMPS)))
                hvdict={'thxe':hvstat[2], 'benear':hvstat[0], 'lihe':hvstat[1]}
                lamp=command.string.split()[0].lower()
                response = hvdict[lamp]
            except IOError as e:
                response = str(e)
                if not response.startswith('ERROR: '):
                    response = 'ERROR: ' + response
            command.setReply(response)
        else:  #Activate the appropriate HV lamp
            command_parts = command.string.split(' ')
            try:
                lamp_num = HVLAMPS.index(command_parts[0].lower())+1  #one base in ardunio  THXE_LAMP=1, BENEAR_LAMP=2, LIHE_LAMP=3, ALL_LAMPS=4
                current = int(command_parts[1])
                self._send_command_to_shield('HV{}{}'.format(lamp_num, current))
                command.setReply('OK')
            except (ValueError, IndexError):
                self.bad_command_handler(command)
            except IOError as e:
                response = str(e)
                if not response.startswith('ERROR: '):
                    response = 'ERROR: ' + response
                command.setReply(response)

    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply

        Report the Key:Value pairs name:cookie, color:value, led:value, hv:value
        """
        try:
            reply = self._send_command_to_shield('LE?')
            ledstat = reply.split()
            if len(ledstat) != len(COLORS):
                raise IOError('Malformed reply to LE? "{}"'.format(reply))
        except IOError as e:
            ledstat = ['ERROR']*len(COLORS)
            self.logger.error('Unable to fetch led values: "{}"'.format(e))

        try:
            reply = self._send_command_to_shield('HV?')
            hvstat = reply.split()
            if len(hvstat)!=len(HVLAMPS):
                raise IOError('Malformed reply to HV? "{}"'.format(reply))
        except IOError as e:
            hvstat = ['ERROR'] * len(HVLAMPS)
            self.logger.error('Unable to fetch HV values: "{}"'.format(e))

        return ([(self.get_version_string(), self.cookie)] +
                [(c, v) for c,v in zip(COLORS, ledstat)] +
                [(c, v) for c,v in zip(HVLAMPS, hvstat)])


if __name__ == '__main__':
    agent = IFUShieldAgent()
    agent.main()
