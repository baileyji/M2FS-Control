import serial, termios

class ShoeStartupException(Exception):
    pass

class Shoe(object):
    """ Fiber shoe  Controller Class """
    def __init__(self, portName, logger):
        """open a threaded serial port connection with the controller
        assert the controller is running the correct version of the code
        initialize list of threads available for motion tasks
        """
        expected_version_string='foobar v0.1'
        self.logger=logger
        self.portName=portName
        critical_error_message=''
        try:
            self.serial=serial.Serial(portName,115200,timeout=.5)
        except serial.SerialException,e:
            critical_error_message="Fatal error. Failed initialize serial link. Exception: %s"%str(e)
        if self.serial.isOpen():
            command_acknowledged=self.send_command_to_shoe('CV')
            if not command_acknowledged:
                critical_error_message="Fatal error. Failed to request software version."
            response=self.get_response_from_shoe()
            #response=expected_version_string #DEBUGGING LINE OF CODE
            if response != expected_version_string:
                critical_error_message=("Fatal error. Shoe reported '%s' , expected '%s'." %
                    (response,expected_version_string))     
        if critical_error_message !='':
            self.logger.critical(critical_error_message)
            self.serial.close()
            raise ShoetartupException(critical_error_message)
    
    def close(self):
        self.serial.flushOutput()
        self.serial.flushInput()
        self.serial.close()
    
    def isOpen(self):
        return self.serial.isOpen()
        
    def do_select_read(self):
        return False
    
    def do_select_write(self):
        return False
    
    def do_select_error(self):
        return False
    
    def executeCommand(self, command, responseCallback, errorCallback):
        """Execute the command on the shoe.
        
        When the command is executed sucessfully the response callback will
        be called. If the command fails then the errorCallback will be called.
        """
        try:
            shoe_command_string=self.generate_command_string_from_command(command)
            if shoe_command_string == '':
                message="Unknown or malformed command: %s" % command
                self.logger.warning(message)
                errorCallback(message)
            else:
                if self.command_is_blocked(command):
                    message="Command %s is blocked. Try again later." % command
                    self.logger.info(message) 
                    errorCallback(message)
                    return
                command_acknowledged=self.send_command_to_shoe(shoe_command_string)
                if command_acknowledged:
                    if self.command_has_response(command):
                        response=self.get_response_from_shoe()
                        if response is '':
                            message="Command response expected from shoe but not recieved. Consider retrying."
                            self.logger.error(message)
                            errorCallback(message)
                        else:
                            self.logger.info("Shoe sent message %s" % response)
                            responseCallback(response.partition(':')[2])
                    else:
                        responseCallback("OK")
                else:
                    message="Shoe did not acknowledge command."
                    self.logger.error(message)
                    errorCallback(message)
                    return
        except serial.SerialException, e:
            message="Serial error: %s" % str(e)
            self.logger.error(message)
            errorCallback(message)
        except termios.error, e:
            message="Serial error: %s" % str(e)
            self.logger.error(message)
            errorCallback(message)
    
    def command_is_valid(self, command):
        """Check the command for validity. Returns true always"""
        return True
        
    def command_is_blocked(self, command):
        return False
    
    def get_response_from_shoe(self):
        """Wait for a response from the shoe"""
        response=self.serial.read(1024)
        if len(response) >0 and response[-1] in '\r\n':
            chop=1
            if len(response) > 1 and response[-2] in '\r\n':
                chop=2
            response=response[:-chop]
        return response
    
    def send_command_to_shoe(self, command_string):
        """
        Send a command string to the shoe and wait for the : or ? responses
            
        If ? is in response or don't gen number of : expected for 
        command string then fail. Else Succeed.
        """
        if command_string:
            out_string=command_string
            if out_string[-1]==';':
                out_string=[:-1]+'\n'
            else:
                out_string+='\n'
            self.serial.flushInput()
            self.serial.write(out_string)
            self.serial.flush()
            response=self.serial.read(1)
            self.logger.debug("Shoe sent '%s', response '%s'" % (out_string[0:-1],response))
            if '?' in response or response.count(':') != num_colons_expected:
                return False
        return True
        
    def is_status_command(self, command):
        """ Return true iff the command is a status command """
        return ('?' in command)
        
    def command_has_response(self, command):
        """ Returns true iff the command will generate a response from the shoe"""
        return self.is_status_command(command)

    def is_motion_command(self, command):
        """ Return true iff the command is a motion command """
        return not self.is_status_command(command)
    
    def command_is_blocked(self, command):
        """ Determine if the command can be run. """
        return False
    
    def generate_command_string_from_command(self, command):
        """Creates the command to send to the device

           It is an error to call this routine with a command that is invalid
           e.g. do your error checking elsewhere!
        """
        if command[0:3]=='RAW':
            return command[3:]
        subroutine_name=self.get_subroutine_name_from_command(command)
        if not subroutine_name:
            return ''
        command_string=subroutine_name
        subroutine_has_parameters={
            'VO':0, 'VE':0, 'TS':0,'PC':0, 'TE':0, 
            'TD':1, 'SH':1, 'MO':1, 'ST':1, 'SQ':1, 'MQ':1, 'DH':1,
            'DP':2, 'PA':2, 'PR':2, 'SP':2, 'AC':2, 'SL':2, 'SD':2, 'BL':2}
        n_args_expected=subroutine_has_parameters[subroutine_name]
        if n_args_expected:
            foo,bar,command_args=command.partition(' ')
            args=command_args.split(' ')
            if len(args) != n_args_expected:
                return ''
            else:
                command_string = command_string + ''.join(args)
        self.logger.debug(
                "Command string %s generated from command %s." %
                (command_string,command)
            )
        return command_string
        
                      
    def get_subroutine_name_from_command(self, command):
        command_name,junk,command_args=command.partition(' ')
        if command_name == 'FILTER':
            if '?' in command: subroutine_name='#GETFILT'
            else:              subroutine_name='#PICKFIL'
        elif command_name == 'LREL':
            if '?' in command:
                subroutine_name='#GETLRTL'
            else:
                subroutine_name='#SETLRTL'
        elif command_name == 'HREL':
            if '?' in command:
                subroutine_name='#GETHRTL'
            else:
                subroutine_name='#SETHRTL'
        elif command_name == 'HRAZ':
            if '?' in command:
                subroutine_name='#GETHRAZ'
            else:
                subroutine_name='#SETHRAZ'
        elif command_name == 'FOCUS':
            if '?' in command:
                subroutine_name='#GETFOC'
            else:
                subroutine_name='#SETFOC'
        elif command_name == 'GES':
            if '?' in command:
                subroutine_name='#GETGES'
            elif 'HIRES' in command:
                subroutine_name='#HIRES'
            elif 'LORES' in command:
                subroutine_name='#LORES' 
        elif command_name == 'FILTER_INSERT':
            subroutine_name='#INFLSIN'
        elif command_name == 'FILTER_REMOVE':
            subroutine_name='#RMFLSIN'
        elif command_name == 'FOCUS_CALIBRATE':
            subroutine_name='#CALFOCU'
        elif command_name == 'LREL_CALIBRATE':
            subroutine_name='#CALLRT'
        elif command_name == 'HREL_CALIBRATE':
            subroutine_name='#CALHRTL'
        elif command_name == 'HRAZ_CALIBRATE':
            subroutine_name='#CALHRAZ'
        elif command_name == 'GES_CALIBRATE':
            subroutine_name='#CALGES'
        else:
            subroutine_name=''
        return subroutine_name
