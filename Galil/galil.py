import serial

class GalilStartupException(Exception):
    pass

class GalilThreadUpdateException(Exception):
    pass

class Galil(object):
    """ Galil DMC-4183 Controller Class """
    def __init__(self, portName, logger):
        """open a threaded serial port connection with the controller
        assert the controller is running the correct version of the code
        initialize list of threads available for motion tasks
        """
        expected_version_string='CODEVER: m2fs.dmc v0.1'
        self.logger=logger
        self.thread_command_map={
            '0':'#AUTO','1':'#ANAMAF','2':'#LOCKMON','3':None,
            '4':None,'5':None,'6':None,'7':None
            }
        self.portName=portName
        critical_error_message=''
        try:
            self.serial=serial.Serial(portName,115200,timeout=.5)
        except serial.SerialException,e:
            critical_error_message="Fatal error. Failed initialize serial link. Exception: %s"%str(e)
        if self.serial.isOpen():
            command_acknowledged=self.send_command_to_gail('XQ#CODEVER,7')
            if not command_acknowledged:
                critical_error_message="Fatal error. Failed to request galil software version."
            response=self.get_response_from_galil()
            response=expected_version_string #TODO remove DEBUGGING LINE OF CODE
            ver_pos=response.find('CODEVER:')
            if ver_pos == -1:
                critical_error_message="Fatal error. Galil did not respond to software version request."
            response=response[ver_pos:]
            if response != expected_version_string:
                critical_error_message=("Fatal error. Galil reported %s , expected %s." %
                    (response,expected_version_string))        
        if critical_error_message !='':
            self.logger.critical(critical_error_message)
            self.serial.close()
            raise GalilStartupException(critical_error_message)
    
    def close(self):
        self.serial.flushOutput()
        self.serial.close()
    
    def isOpen(self):
        return self.serial.isOpen()
        
    def do_select_read(self):
        return False
    
    def do_select_write(self):
        return False
    
    def do_select_error(self):
        return False
    
    def executeCommand(self,command, responseCallback, errorCallback):
        """Execute the command on the galil.
        
        When the command is executed sucessfully the response callback will
        be called.
        
        If the command fails, is already in progress, or there is not a free
        thread on the Galil then the errorCallback will be called.
        """
        try:
            if not self.command_is_valid(command):
                message="Unknown or malformed command: %s" % command
                self.logger.warning(message)
                errorCallback(message)
            self.update_executing_threads_and_commands()
            if self.command_is_blocked(command):
                message="Command %s is blocked. Try again later." % command
                self.logger.info(message) 
                errorCallback(message)
                return
            galil_thread_number=self.get_thread_for_command(command)
            if galil_thread_number is None:
                message="All available galil threads in use. Try again later"
                self.logger.info(message)
                errorCallback(message)
                return
            else:
                galil_command_string=self.generate_command_string_from_command(command,galil_thread_number)
                if galil_command_string == '':
                    errorCallback('Invalid command.')
                else:
                    command_acknowledged=self.send_command_to_gail(galil_command_string)
                    if command_acknowledged:
                        self.add_command_to_executing_commands(command, galil_thread_number)
                        if self.command_has_response(command):
                            response=self.get_response_from_galil()
                            if response is '':
                                message="Command response expected from galil but not recieved. Consider retrying."
                                self.logger.error(message)
                                errorCallback(message)
                            else:
                                self.logger.info("Galil sent message %s" % response)
                                responseCallback(response.partition(':')[2])
                        else:
                            responseCallback("OK")
                    else:
                        message="Galil did not acknowledge command."
                        self.logger.error(message)
                        errorCallback(message)
                        return
        except serial.SerialException, e:
            message="Serial error: %s" % str(e)
            self.logger.error(message)
            errorCallback(message)
        except GalilThreadUpdateException, e:
            self.logger.error(str(e))
            errorCallback(str(e))
    
    def command_is_valid(self, command):
        """Check the command for validity. Returns true always"""
        return True
    
    def update_executing_threads_and_commands(self):
        """Retrieve and update the list of thread statuses from the galil""" 
        #Ask galil for thread statuses
        command_acknowledged=self.send_command_to_gail('MG "HX=",_HX0,_HX1,_HX2,_HX3,_HX4,_HX5,_HX6,_HX7')
        if not command_acknowledged:
            message="Failed to request thread status from galil."
            self.logger.error(message)
            raise GalilThreadUpdateException(message)
        response=self.get_response_from_galil()
        response='HX= 1.0000 1.0000 1.0000 0.0000 0.0000 0.0000 0.0000 0.0000\r\n' 
        hx_pos=response.find('HX=')
        if hx_pos == -1:
            message="Galil did not respond to thread status request. Response: %s" % response
            self.logger.error(message)
            raise GalilThreadUpdateException(message)
        response=response[hx_pos+4:]
        response=response[:response.find('\r')] #TODO add in error where not complete message is recieved
        #if self.thread_command_map['3']!=None: import pdb;pdb.set_trace()
        #Remove executing commands from list if respective threads are no longer running
        for thread_number, thread_status in enumerate(response.split(' ')):
            #TODO tidy thread_status if needed
            if '0.' in thread_status:
                self.thread_command_map["%i"%thread_number]=None
        return
        
    def get_thread_for_command(self, command):
        """ Get ID of Galil thread to use for the command. None if none free""" 
        if self.is_motion_command(command):
            thread_id=None
            for i in ['3','4','5','6']:
                if self.thread_command_map[i]==None:
                    thread_id=i
                    break
        else:
            thread_id='7'
        return thread_id
            
    def add_command_to_executing_commands(self, command, thread):
        self.thread_command_map[thread]=command
        return
    
    def get_response_from_galil(self):
        """Wait for a response from the galil"""
        response=self.serial.read(1024)
        return response
    
    def send_command_to_gail(self, command_string):
        """
        Send a command string to the galil and wait for the : or ? responses
            
        If ? is in response or don't gen number of : expected for 
        command string then fail. Else Succeed.
        """
        if command_string:
            out_string=command_string
            if out_string[-1]==';':
                out_string[-1]='\r'
            else:
                out_string+='\r'
            num_colons_expected=1+out_string.count(';')
            import time
            time.sleep(1)
            self.serial.flushInput()
            self.serial.write(out_string)
            self.serial.flush()
            response=self.serial.read(num_colons_expected)
            #import pdb;pdb.set_trace()
            self.logger.debug("Galil sent command string %s. Galil response: '%s'" % (out_string[0:-1],response))
            if '?' in response or response.count(':') != num_colons_expected:
                return False
        return True
        
    def is_status_command(self, command):
        """ Return true iff the command is a status command """
        return ('?' in command)
        
    def command_has_response(self, command):
        """ Returns true iff the command will generate a response from the galil"""
        return self.is_status_command(command)

    def is_motion_command(self, command):
        """ Return true iff the command is a motion command """
        return not self.is_status_command(command)
    
    def command_is_blocked(self, command):
        """ Determine if the command can be run. """
        if '?' not in command:
            command_name=command.split(' ')[0]
            command_class=command_name.split('_')[0]
            #Get executing command names from self.thread_command_map.items()
            #import pdb;pdb.set_trace()
            executing_command_names=map(lambda x:x[1].split()[0],
                filter(lambda x: x[1] != None and x[0]!='7',
                    self.thread_command_map.items()
                    )
                )
            #Get executing command classes from executing_command_names
            executing_command_classes=map(lambda x:x.split('_')[0], executing_command_names)
            return (command_name in executing_command_names or
                command_class in executing_command_classes)
        else:
            return False
    
    def generate_command_string_from_command(self, command, thread):
        """Creates the command to send to the galil from the command

           It is an error to call this routine with a command that is invalid
           e.g. do your error checking elsewhere!
        """
        if command[0:3]=='RAW':
            return command[3:]
        subroutine_name=self.get_subroutine_name_from_command(command)
        if not subroutine_name:
            return ''
            
        command_string="XQ%s,%s" % (subroutine_name, thread)
        subroutine_has_parameters={
            '#PICKFIL':True, '#SETLRTL':True, '#SETHRTL':True,
            '#SETHRAZ':True, '#SETFOC' :True,
            '#GETLRTL':False, '#GETHRTL':False, '#GETHRAZ':False,
            '#GETFOC' :False, '#GETFILT':False, '#GETGES' :False,
            '#HIRES'  :False, '#LORES'  :False, '#INFLSIN':False,
            '#RMFLSIN':False, '#CALFOCU':False, '#CALLRT' :False,
            '#CALHRTL':False, '#CALHRAZ':False, '#CALGES' :False
            }
        if subroutine_has_parameters[subroutine_name]:
            foo,bar,command_args=command.partition(' ')
            packed_parameters=self.pack_parameters(command_args,thread)
            command_string = packed_parameters + command_string
            
        self.logger.debug(
                "Galil command string %s generated from command %s." %
                (command_string,command)
            )
        return command_string
        
    def pack_parameters(self, command_args, thread):
        command_string_list=[]
        if command_args and '?' not in command_args:
            command_args=command_args.split(' ')
            variable_names=['a','b','c','d','e','f','g','h']
            for i, param in enumerate(command_args):
                command_string_list.append(
                    "%s[%s]=%s;" % (variable_names[i],thread,param) )
        return ''.join(command_string_list)
        
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


