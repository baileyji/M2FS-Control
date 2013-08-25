#!/usr/bin/env python2.7
import sys
sys.path.append(sys.path[0]+'/../lib/')
import SelectedConnection
from agent import Agent

SHACKHARTMAN_AGENT_VERSION_STRING='Shack-Hartman Agent v0.2'

# The byte returned by getErrorStatus() if there are no errors
NO_POLOLU_ERRORS='0x00'

class LEDserial(SelectedConnection.SelectedSerial):
    """
    The Shack-Hartman LED controller connection class
    
    This is just a simple wrapper for selectedserial that removes the default
    line terminator on sent messages and sends a null byte on connect.
    
    The LED controller sets the LED brightness to the value of the most recent
    byte it gets. For example, send a \x05 and the led is 5/256% of full on.
    There is a pot on the microcontroller that may be used to set the full on
    brightness.
    """
    def _postConnect(self):
        """ Turn the LED off whenever the agent connects (known state)"""
        self.connection.write('\x00')
        self.connection.flush()
    
    def _terminateMessage(self, message):
        """ LED messages don't get a terminator """
        return message

def convertSigned16bit(str):
    """
        Convert a 2 byte little-endian string to a signed 16 bit number
        
        Raise ValueError if not a 2 byte string or unable to convert
        """
    if len(str) != 2:
        raise ValueError
    try:
        n=(ord(str[0])+256*ord(str[1]))
        if n>32767:
            return n-65536
        else:
            return n
    except Exception:
        raise ValueError

def convertUnsigned16bit(str):
    """
        Convert a 2 byte little-endian string to an unsigned 16 bit number
        
        Raise ValueError if not a 2 byte string or unable to convert
        """
    if len(str) != 2:
        raise ValueError
    try:
        return (ord(str[0])+256*ord(str[1]))
    except Exception:
        raise ValueError

class ShackHartmanAgent(Agent):
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
        Agent.__init__(self,'ShackHartmanAgent')
        #Allow two connections so the datalogger agent can poll for temperature
        self.max_clients=2
        self.connections['shled']=LEDserial('/dev/shLED', 115200)
        self.connections['shlenslet']=SelectedConnection.SelectedSerial('/dev/shLenslet', 115200)
        self.shledValue=0
        self.command_handlers.update({
            #Get/Set the SH calibration LED brightness
            'SHLED':self.SHLED_command_handler,
            #Get/Set the SH lenslet position
            'SHLENS':self.SHLENS_command_handler,
            #Get the temperature at the SH lenslet
            'TEMP':self.TEMP_command_handler})
    
    def get_version_string(self):
        """ Return a string with the version."""
        return SHACKHARTMAN_AGENT_VERSION_STRING
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return ("This is the Shack-Hartman agent. It controlls the lenslet & "+
            "calibration LED")
    
    def SHLED_command_handler(self, command):
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
            command_parts=command.string.split(' ')
            try:
                self.connections['shled'].sendMessage(chr(int(command_parts[1])))
                self.shledValue=int(command_parts[1])
                command.setReply('OK')
            except ValueError:
                self.bad_command_handler(command)
            except IOError, e:
                command.setReply('ERROR: LED Disconnected')
    
    def SHLENS_command_handler(self, command):
        """ 
        Handle geting/setting the position of the lenslet
        
        Arguments are: ? IN OUT
        If querying, report the lenslet position, if setting, command the 
        controller to drive the lenslet in or out. Respond OK or ERROR as
        appropriate.
        """
        if '?' in command.string:
            position=self.determineLensletPosition()
            command.setReply(position)
        else:
            err=self.getErrorStatus()
            if err !=NO_POLOLU_ERRORS:
                command.setReply('ERROR: %s' % err)
            else:
                #See simple_motor_controllers.pdf p64-65 for commands
                MOTOR_FORWARD_FULL_SPEED='\x89\x7F'
                MOTOR_REVERSE_FULL_SPEED='\x8A\x7F'
                try:
                    if 'IN' in command.string and 'OUT' not in command.string:
                        self.connections['shlenslet'].sendMessage(MOTOR_REVERSE_FULL_SPEED)
                        command.setReply('OK')
                    elif 'OUT' in command.string and 'IN' not in command.string:
                        self.connections['shlenslet'].sendMessage(MOTOR_FORWARD_FULL_SPEED)
                        command.setReply('OK')
                    else:
                        self.bad_command_handler(command)
                except IOError:
                    command.setReply('ERROR: Lenslet Disconnected')
    
    def TEMP_command_handler(self, command):
        """ Report the temp of the lenslet controller in deg C, below 0 = 0 """
        command.setReply(self.getTemp())
    
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
            self.connections['shled'].sendMessage(chr(self.shledValue))
            ledStatus='%i' % self.shledValue
        except IOError:
            ledStatus='LED Disconnected'
        return [(self.get_version_string(), self.cookie),
                ('Lenslet',lensStatus),
                ('Led', ledStatus),
                ('Temp', temp),
                ('ErrByte', err)]
    
    def getErrorStatus(self):
        """
        Poll the controller for the error status byte
        
        Returns the error value as a hex string or ERROR if IOERROR. No errors 
        is the string '0x00'
        
        NB We must and the response as some of the bits are reserved and may not 
        be 0 despite there being no error.
        """
        try:
            REQUEST_ERROR_BYTE='\xA1\x00'
            ERROR_BITS=0x3ff
            self.connections['shlenslet'].sendMessageBlocking(REQUEST_ERROR_BYTE)
            response=self.connections['shlenslet'].receiveMessageBlocking(nBytes=2)
            #for bit meanings see simple_motor_controllers.pdf
            err='0x{0:02x}'.format(convertUnsigned16bit(response) & ERROR_BITS)
            return err
        except IOError:
            return 'Lenslet Disconnected'
        except ValueError:
            return 'Unable to parse lenslet response'
    
    def getTemp(self):
        """
        Poll the controller for the temp in degrees Celsius 
        
        Returns the temp value as a string or UNKNOWN if an error occurs.
        Converts the temp to degrees. Controller responds with two bytes, low
        first. Value is in units of 0.1 deg C.
        """
        try:
            REQUEST_TEMPERATURE='\xA1\x18'
            self.connections['shlenslet'].sendMessageBlocking(REQUEST_TEMPERATURE)
            response=self.connections['shlenslet'].receiveMessageBlocking(nBytes=2)
            temp=str(0.1*convertUnsigned16bit(response))
        except (IOError, ValueError):
            temp='UNKNOWN'
        return temp
    
    def determineLensletPosition(self):
        """
        Returns the status of the lenslet inserter
        
        responds IN, OUT, MOVING, INTERMEDIATE, or ERROR
        Queries the controller for the value of the current speed of the motor
        and gets the error byte. If the speed in nonzero we return MOVING.
        
        Otherwise we check the values of both limits and report IN if 
        analog1 is greater than a threshold. OUT if analog2 is greater, ERROR if
        they both are (a switch has failed), and INTERMEDIATE if neither is over
        the threshold. At the hardware level the Pololu is configured so that 
        the normally closed limit switches are connected to the two analog
        inputs which have pullups on them and go to a 12bit ADC.
        """
        try:
            REQUEST_MOTOR_SPEED='\xA1\x15'
            REQUEST_ANALOG1_RAW_VALUE='\xA1\x0C'
            REQUEST_ANALOG2_RAW_VALUE='\xA1\x10'
            ANALOG_THRESHOLD=1024
            self.connections['shlenslet'].sendMessageBlocking(REQUEST_MOTOR_SPEED)
            response=self.connections['shlenslet'].receiveMessageBlocking(nBytes=2)
            if convertSigned16bit(response) != 0:
                return 'MOVING'
            else:
                #Check IN limit
                self.connections['shlenslet'].sendMessageBlocking(REQUEST_ANALOG1_RAW_VALUE)
                response=self.connections['shlenslet'].receiveMessageBlocking(nBytes=2)
                limINValue=convertUnsigned16bit(response)
                limINtripped=limINValue>ANALOG_THRESHOLD
                #Check OUT limit
                self.connections['shlenslet'].sendMessageBlocking(REQUEST_ANALOG2_RAW_VALUE)
                response=self.connections['shlenslet'].receiveMessageBlocking(nBytes=2)
                limOUTValue=convertUnsigned16bit(response)
                limOUTtripped=limOUTValue>ANALOG_THRESHOLD
                #Determine the state
                if limINtripped and not limOUTtripped:
                    return 'IN'
                elif limOUTtripped and not limINtripped:
                    return 'OUT'
                elif not limINtripped and not limOUTtripped:
                    return 'INTERMEDIATE'
                else:
                    return 'ERROR: Both limits tripped'
        except IOError:
            return 'ERROR: Lenslet Disconnected'
        except ValueError:
            return 'ERROR: Lenslet did not adhere to protocol' 

if __name__=='__main__':
    agent=ShackHartmanAgent()
    agent.main()
