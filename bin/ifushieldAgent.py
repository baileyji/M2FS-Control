#!/usr/bin/env python2.7
import time
import m2fscontrol.selectedconnection as selectedconnection
from m2fscontrol.agent import Agent

IFUSHIELD_AGENT_VERSION_STRING = 'IFUShield Agent v1.2'

ARDUINO_BOOT_TIME = 2.3
EXPECTED_IFUSHIELD_INO_VERSION = '1.2'

COLORS = ('392', '407', 'whi', '740', '770', '875')

COLORS = ('770', '740', '875', 'whi', '407', '392')
HVLAMPS = ('thxe', 'benear', 'lihe')
HVLMAP_MAX_CURRENT = {'thxe': 10, 'benear': 10, 'lihe': 10}
HVLMAP_MIN_CURRENT = {'thxe': 1, 'benear': 2, 'lihe': 1}
TEMPS = ('ebox', 'stage', 'enc1', 'enc2')

HVLAMPMAP = {1: 'thxe', 2: 'benear', 3: 'lihe', 4: 'thxe', 5: 'benear', 6: 'lihe'}  # 1 indexed on arduino


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
        self.connection.flushInput()
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
            self.connection.write('OF\n')  # turn everything off
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
            'SHIELDRAW': self.RAW_command_handler,
            # Get/Set state of HV lamps
            'THXE': self.HV_command_handler,  # response: {OK,ERROR,#}
            'BENEAR': self.HV_command_handler,
            'LIHE': self.HV_command_handler,
            # Get/Set state of LEDs
            'MCLED': self.LED_command_handler,  # response:{ OK,ERROR, # # # # # #}
            # Report all the temps
            'TEMPS': self.TEMPS_command_handler})  # response:{  # # # # # #}

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
                response = self._send_command_to_shield('TE')
            except IOError, e:
                response = 'UNKNOWN'
            finally:
                self.connections['ifushield'].rlock.release()
        else:
            response = 'ERROR: Busy, try again'
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
            # Set the LED brightness 0-4096
            command_parts = command.string.split(' ')
            try:
                commands = ['LE{}{}'.format(i + 1, val) for i, val in
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

        Valid command string is a lamp name followed by a current value current values in excess of 20 will
        activate lamp 4, clobbering any previous activation.

        Respond OK or error as appropriate.
        """
        if '?' in command.string:
            try:
                response = self._send_command_to_shield('HV?')  # Per arduino order is BeNeAr LiHe ThXe
                hvstat = response.split()
                if len(hvstat) != len(HVLAMPMAP):
                    raise IOError('Bad response to HV? "{}", expected {} values'.format(response, len(HVLAMPMAP)))
                hvdict = {i+1: float(s) for i, s in enumerate(hvstat)}
                lamp = command.string.split()[0].lower()
                response = str(sum([hvdict[lamp_ndx] for lamp_ndx, lamp_type in HVLAMPMAP.items() if lamp_type==lamp]))
            except IOError as e:
                response = str(e)
                if not response.startswith('ERROR: '):
                    response = 'ERROR: ' + response
            command.setReply(response)

        else:  # Activate the appropriate HV lamp
            command_parts = command.string.split(' ')
            try:
                lamp_type = command.string.split()[0].lower()  # nb * not permitted
                lamp_indices = [i for i, kind in HVLAMPMAP.items() if kind == lamp_type]

                if len(lamp_indices) < 1:
                    raise IOError('No lamp type "{}"'.format(lamp_type))

                current = int(command_parts[1])
                if current > len(lamp_indices)*HVLMAP_MAX_CURRENT[lamp_type]:
                    raise IOError('Current {} too high for {} available lamps of type {}'.format(current, len(lamp_indices), lamp_type))

                if current == 0:
                    for lamp_ndx in lamp_indices:
                        self._send_command_to_shield('HV{}{}'.format(lamp_ndx, 0))
                else:
                    # Either

                    # Split the current bright to dim between the lamps
                    # while current>0:
                    #     l_current = min(max(HVLMAP_MIN_CURRENT[lamp_type], current), HVLMAP_MAX_CURRENT[lamp_type])
                    #     self._send_command_to_shield('HV{}{}'.format(lamp_indices.pop(), l_current))
                    #     current -= l_current

                    # Or

                    # Split the current more or less evenly between the lamps
                    base_current = current // len(lamp_indices)
                    bonus_current = current % len(lamp_indices)

                    if base_current < HVLMAP_MIN_CURRENT[lamp_type]:
                        current = min(max(HVLMAP_MIN_CURRENT[lamp_type], current), HVLMAP_MAX_CURRENT[lamp_type])
                        self._send_command_to_shield('HV{}{}'.format(lamp_indices[0], current))
                    else:
                        for lamp_ndx in lamp_indices:
                            current = min(base_current+bonus_current, HVLMAP_MAX_CURRENT[lamp_type])
                            bonus_current = max(0, bonus_current - (current-base_current))
                            self._send_command_to_shield('HV{}{}'.format(lamp_ndx, current))

                fault, state = self.check_lamp_fault(lamp_type)
                if fault:
                    command.setReply('ERROR: {} fault: {}'.format(lamp_type, state))
                else:
                    command.setReply('OK')
            except (ValueError, IndexError):
                self.bad_command_handler(command)
            except IOError as e:
                response = str(e)
                if not response.startswith('ERROR: '):
                    response = 'ERROR: ' + response
                command.setReply(response)

    def check_lamp_fault(self, species):
        status = self.query_status()
        lamp_bays = [bay for bay, lamp in HVLAMPMAP.items() if lamp == species]
        state = {'{}_bay{}'.format(species, bay): status['{}_bay{}'.format(species, bay)]
                 for bay in lamp_bays if '{}_bay{}'.format(species, bay) in status}
        have_faults = any(status.get('{}_bay{}_fault'.format(species, bay), False) for bay in lamp_bays)
        return have_faults, state

    def query_status(self):
        """
        Parses TS command

            ```c
            bool TScommand() {
              Serial.println("LEDs");
              Serial.print(F(" UV (390): "));Serial.print(ledlevels[0]);Serial.print(F("  BL (410): "));Serial.print(ledlevels[1]);
              Serial.print(F("  White : "));Serial.println(ledlevels[2]);
              Serial.print(F(" IR (740): "));Serial.print(ledlevels[3]);Serial.print(F("  IR (770): "));Serial.print(ledlevels[4]);
              Serial.print(F("  IR (850): "));Serial.println(ledlevels[5]);

              Serial.println(F("Temps"));Serial.print(" ");
              for (int i=0;i<N_TEMP_SENSORS-1;i++) {
                Serial.print(temps[i].reading);
                Serial.print(", ");
              }
              Serial.println(temps[N_TEMP_SENSORS-1].reading, 3);


             Serial.println(F("Lamps"));
              for (int i=0; i<N_LAMPS; i++) {
                Serial.print(" ");Serial.print(i+1);Serial.print(", "); Serial.print(lamps[i].isEnabled() ? F("enabled") : F("disabled"));
                Serial.print(", ");Serial.print(lamps[i].isCurrentMode() ? "current":"voltage");Serial.print(F("_limit_mode, "));
                Serial.print(lamps[i].getVoltage(), 2);Serial.print(F(" V ("));Serial.print(lamps[i].getVoltageLimit());Serial.print(F(" lim), "));
                Serial.print(lamps[i].getCurrent(), 2);Serial.print(F(" mA ("));Serial.print(lamps[i].getCurrentLimit());Serial.println(F(" lim)"));
              }

              return true;
            }
            ```

        """
        ts_reply = self._send_command_to_shield('TS')
        ret = {}
        lines = [l.strip() for l in ts_reply.split('\n') if l.strip()]
        if len(lines) < 7:
            raise IOError('Malformed TS reply: too few lines')
        if lines[0] != 'LEDs':
            raise IOError('Malformed TS reply: missing LEDs heading')

        # parse LED values
        led_values = []
        led_values.extend(lines[1].replace('UV (390):', '')
                          .replace('BL (410):', '')
                          .replace('White :', '')
                          .split())
        led_values.extend(lines[2].replace('IR (740):', '')
                          .replace('IR (770):', '')
                          .replace('IR (850):', '')
                          .split())
        if len(led_values) != len(COLORS):
            raise IOError('Malformed TS reply: expected {} LED values, got {}'.format(len(COLORS), len(led_values)))
        led_map = {'392': led_values[0], '407': led_values[1], 'whi': led_values[2],
                   '740': led_values[3], '770': led_values[4], '875': led_values[5]}
        ret.update(led_map)

        if not lines[3].startswith('Temps'):
            raise IOError('Malformed TS reply: missing Temps heading')
        if len(lines) > 4:
            temp_values = [x.strip() for x in lines[4].split(',') if x.strip()]
            if len(temp_values) != len(TEMPS):
                self.logger.warning('Unexpected temp response format: "{}"'.format(lines[4]))
            else:
                for key, val in zip(TEMPS, temp_values):
                    ret[key] = val

        if len(lines) < 6 or lines[5] != 'Lamps':
            raise IOError('Malformed TS reply: missing Lamps heading')

        lamp_ids = sorted(HVLAMPMAP.keys())
        if len(lines) < 6 + len(lamp_ids):
            raise IOError('Malformed TS reply: incomplete lamp status block')
        lamp_lines = lines[6:]
        lamp_current_totals = {lamp_type: 0.0 for lamp_type in HVLAMPS}

        for lamp_line_idx, i in enumerate(lamp_ids):
            state_line = lamp_lines[lamp_line_idx]

            state = [x.strip() for x in state_line.split(',')]
            if len(state) < 5:
                raise IOError('Malformed TS reply: bad lamp state "{}"'.format(state_line))
            if int(state[0]) != i:
                raise IOError('Malformed TS reply: expected lamp {} found {}'.format(i, state[0]))

            enabled = (state[1] == 'enabled')

            current_mode = (state[2].split('_')[0] == 'current')

            voltage_field, current_field = state[3], state[4]
            if ' V (' not in voltage_field or ' mA (' not in current_field:
                raise IOError('Malformed TS reply: bad lamp value "{}"'.format(state_line))

            voltage, volt_lim = voltage_field.split(' V (', 1)
            current, current_lim = current_field.split(' mA (', 1)
            volt_lim = volt_lim.replace(' lim)', '')
            current_lim = current_lim.replace(' lim)', '')
            lamp_current_totals[HVLAMPMAP[i]] += float(current)

            lamp_type = HVLAMPMAP[i]
            lamp_name = '{}_bay{}'.format(lamp_type, i)
            star_v = '' if current_mode else '*'
            star_i = '*' if current_mode else ''
            ret[lamp_name+'_fault'] = enabled and not current_mode
            enabled_label = 'enabled' if enabled else 'disabled'
            ret[lamp_name] = '{}/{} V{} {}/{} mA{} ({})'.format(
                voltage.strip(), volt_lim.strip(), star_v, current.strip(), current_lim.strip(), star_i, enabled_label)

        for k in HVLAMPS:
            ret[k + '_total'] = '{}'.format(lamp_current_totals[k])

        return ret

    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply

        Report the Key:Value pairs name:cookie, led_color:led_value, hv_lamp_species:total_current, hv_lamp_name:volt_current_mode_str

        hv_lamp_name:volt_current_mode_str is of form '{species}_bay{number}':'{volt}/{volt_lim} V{"*" if not current_mode else ""} {current}/{current_lim} mA{"*" if current_mode else ""} (enabled or disabled))'
        """

        try:
            parsed = self.query_status()
            lamp_details = [('{}_bay{}'.format(HVLAMPMAP[i], i), parsed['{}_bay{}'.format(HVLAMPMAP[i], i)]) for i in sorted(HVLAMPMAP.keys())]
            led_status = [(c, parsed[c]) for c in COLORS]
            lamp_status = [(c, parsed[c+'_total']) for c in HVLAMPS]
            status_list = led_status + lamp_status + lamp_details
        except IOError as e:
            num_keys = len(COLORS) + len(HVLAMPS) + len(HVLAMPMAP)
            status_list = [('ERROR', 'ERROR')] * num_keys
            self.logger.error('Unable query TS status: "{}"'.format(e))
        except Exception as e:
            num_keys = len(COLORS) + len(HVLAMPS) + len(HVLAMPMAP)
            status_list = [('ERROR', 'ERROR')] * num_keys
            self.logger.error('Failure parsing TS: "{}"'.format(e))

        return [(self.get_version_string(), self.cookie)] + status_list


if __name__ == '__main__':
    agent = IFUShieldAgent()
    agent.main()
