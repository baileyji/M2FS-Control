#!/usr/bin/env python2.7
import sys, socket, time
sys.path.append(sys.path[0]+'/../lib/')

from agent import Agent
import m2fsConfig

MCAL_AGENT_VERSION_STRING='MCal Agent v0.1'


_sokMCalLED = None
COLORS = ('392','407', 'whi', '740', '770', '875')
MAXLEVEL = {'392':4096,'407':4096, 'whi':4096, '740':2048, '770':2048, '875':2048}

def send_rcv_mcalled(x, timeout=1.0, log=None):
    global _sokMCalLED
    try:
        if _sokMCalLED is None:
            if log is not None:
                log.info('Trying to connect to MCalLED')
            _sokMCalLED = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _sokMCalLED.connect(m2fsConfig.getMCalLEDAddress())
            _sokMCalLED.settimeout(timeout)
    
        _sokMCalLED.send(x[:29]+'\n')
        return _sokMCalLED.recv(34).strip()
        # never send more than 30 bytes
        # Expect "ACK #### #### #### #### #### ####\n" or "ERR #### #### #### #### #### ####\n"
    except Exception as e:
        if log is not None:
            log.warning(str(e))
        # _sokMCalLED.shutdown(socket.SHUT_RDWR)
        # _sokMCalLED.close()
        _sokMCalLED=None
        raise IOError(e)


class MCalAgent(Agent):
    """
    This program is responsible for the c
    """
    def __init__(self):
        Agent.__init__(self, 'MCalAgent')
        self.max_clients = 1
        #self.connections['mcled'] = socket connection the LED???
        self.colors = COLORS
        self.ledValue = {c:0 for c in self.colors}
        self.command_handlers.update({'MCLED': self.MCLED_command_handler})
    
    def get_version_string(self):
        """ Return a string with the version."""
        return MCAL_AGENT_VERSION_STRING
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the MCalLED agent. It controls the MCal LED Flatfield Unit."
    
    def MCLED_command_handler(self, command):
        """
        Handle geting/setting the LED illumination value 
        
        Valid command string argument is a number from 0 to 4096

        UV BLUE WHITE 740 770 875
        
        If we are getting, just report the most recently set value, if setting 
        convert the command argument to a single byte and send that to the SH 
        led. Respond OK or error as appropriate.
        """
        if '?' in command.string:
            command.setReply(self.get_led_values())
        else:
            """ Set the LED brightness 0-4096 """
            command_parts = command.string.split(' ')
            try:
                values = map(int, command_parts[1:])
                reply=self.safe_set_leds({c:v for c,v in zip(self.colors, values)})
                command.setReply(reply)
            except (ValueError, IndexError):
                self.bad_command_handler(command)
            except IOError:
                command.setReply('ERROR: MCalLED Disconnected')

    def safe_set_leds(self, level_dict):
        """Get led values"""

        for k in level_dict:
            try:
                level_dict[k] = min(MAXLEVEL[k], max(0, int(round(level_dict[k]))))
            except Exception as e:
                return 'ERROR: Bad Command for color {}'.format(k)

        for i, c in enumerate(self.colors):
            try:
                resp=send_rcv_mcalled('{}{:04}'.format(i + 1, level_dict[c]),
                                      log=self.logger)
                if resp[:3] is 'ACK':
                    self.ledValue[c] = level_dict[c]
                else:
                    self.ledValue[c] = 'Error'

                return 'OK'
            except IOError:
                self.ledValue[c] = 'Error'
                return 'ERROR: Try Again'
        return 'OK'

    def get_led_values(self, asdic=False):
        try:
            values = send_rcv_mcalled('?',log=self.logger)
            values = values.replace('ACK ', '').replace('ERR ', 'Error: ')
            self.logger.debug(values)
            if len(values.split()) !=6:
                raise IOError('Malformed Reply: "{}"'.format(values))
            return {c:v for c,v in zip(self.colors, values)} if asdic else values
        except IOError:
            return {c:'Error' for c in self.colors} if asdic else 'Error: Try Again'

    def get_status_list(self):
        """ 
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pairs name:cookie, color:value
        """
        return [(self.get_version_string(), self.cookie)] + [(c, self.ledValue[c][c]) for c in self.colors]


if __name__=='__main__':
    agent=MCalAgent()
    agent.main()
