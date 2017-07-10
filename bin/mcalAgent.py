#!/usr/bin/env python2.7
import sys, socket
sys.path.append(sys.path[0]+'/../lib/')

from agent import Agent
from m2fsConfig import getMCalLEDAddress

MCALLED_AGENT_VERSION_STRING='MCalLED Agent v0.1'


def send_rcv_mcalled(x, timeout=0.25):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(getMCalLEDAddress())
        sock.settimeout(timeout)
        sock.sendall(x[:29]+'\n')  # Never send more than 30 bytes
        # Expect "ACK #### #### #### #### #### ####\n" or "ERR #### #### #### #### #### ####\n"
        return sock.recv(34)
    finally:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()


class MCalLEDAgent(Agent):
    """
    This program is responsible for the calibration LED for the Shack-Hartman
    (SH) system and the insertion and removal of the SH lenslet array.
    
    The LED is controlled by a simple arduino sketch (shLED.ino), which sets the
    calibration LED to a brightness value 0-255, based on the value of whatever
    byte is received over the serial line. 
    
    The inserter is controlled by a Pololu 24v12 Simple Motor Controller. The
    controller is connected to the lenslet limit switches so we just tell it to
    drive the motor in one direction for insertion, and the other for removal.
    We know the lenslet is in when the appropriate limit is tripped.
    Note that the Polou configuration utility must be used to configure the 
    controller prior to using with the agent. The analog inputs must be 
    configured as limits and it must not be configured to boot into safe start
    mode.
    
    The controller has an onboard temperature sensor, which we expose so the 
    datalogger subsystem can keep track of it.
    """
    def __init__(self):
        Agent.__init__(self, 'ShackHartmanAgent')
        #Allow two connections so the datalogger agent can poll for temperature
        self.max_clients = 2
        #self.connections['shled'] = LEDserial(getMCalLEDAddress())
        self.ledValue = {'392': 0, '407': 0, 'whi': 0, '740': 0, '770': 0, '875': 0}
        self.command_handlers.update({'MCLED': self.MCLED_command_handler})
    
    def get_version_string(self):
        """ Return a string with the version."""
        return MCALLED_AGENT_VERSION_STRING
    
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
        
        Valid command string argument is a number from 0 to 255
        
        If we are getting, just report the most recently set value, if setting 
        convert the command argument to a single byte and send that to the SH 
        led. Respond OK or error as appropriate.
        """
        if '?' in command.string:
            command.setReply('%i' % self.shledValue)
        else:
            """ Set the LED brightness 0-255 """
            command_parts = command.string.split(' ')
            try:
                color, value = command_parts[0], int(command_parts[1])
                send_rcv_mcalled('{}{:04}'.format(color, value))
                self.ledValue[color] = value
                command.setReply('OK')
            except (ValueError, IndexError):
                self.bad_command_handler(command)
            except IOError:
                command.setReply('ERROR: MCalLED Disconnected')

    def get_status_list(self):
        """ 
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pairs name:cookie, Lenslet:position, Led:value, 
        Temp:value, & ErrByte:value pairs.
        """
        lensStatus=self.determineLensletPosition()
        temp=self.getTemp()
        err=self.getErrorStatus()
        try:
            #TODO Query MCAL for led brightness
            self.connections['mcled'].sendMessage(chr(self.shledValue))
            ledStatus = '%i' % self.shledValue
        except IOError:
            ledStatus = 'MCalLED Disconnected'
        return [(self.get_version_string(), self.cookie),
                ('393', ledStatus),
                ('407', temp),
                ('whi', err),
                ('740', err),
                ('770', err),
                ('875', err)]
    

if __name__=='__main__':
    agent=MCalLEDAgent()
    agent.main()
