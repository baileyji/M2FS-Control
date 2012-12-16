import time
import argparse
import socket
import signal
import atexit
import serial
import sys
import select
import SelectedConnection
from m2fsConfig import m2fsConfig

class GalilThreadUpdateException(IOError):
    pass

class GalilCommandNotAcknowledgedError(IOError):
    pass

import termios
class GalilSerial(SelectedConnection.SelectedSerial):
    """ Galil DMC-4183 Controller Class """
    def __init__(self, *args, **kwargs):
        self.SIDE=kwargs.pop('SIDE')
        self.settingName_to_variableName_map={
            'filter1encoder':'felencp[0]','filter2encoder':'felencp[1]',
            'filter3encoder':'felencp[2]','filter4encoder':'felencp[3]',
            'filter5encoder':'felencp[4]','filter6encoder':'felencp[5]',
            'filter7encoder':'felencp[6]','filter8encoder':'felencp[7]',
            'filter9encoder':'felencp[8]', #NB LOAD position
            'filterInserted':'fesinsp','filterRemoved':'fesremp',
            'filterTolerance':'feselrg',
            'hiresStep':'geshrp','loresStep':'geslrp',
            'hiresEncoder':'geshrep','loresEncoder':'geslrep',
            'gesTolerance':'gesenct',
            'flsimInserted':'flsinsp','flsimRemoved':'flsremp',
            'loresSwapStep':'gesgsp','loresSwapEncoder':'gesgsep'}
        self.settingNameCommandClasses={
            'filter1encoder':'FILTER','filter2encoder':'FILTER',
            'filter3encoder':'FILTER','filter4encoder':'FILTER',
            'filter5encoder':'FILTER','filter6encoder':'FILTER',
            'filter7encoder':'FILTER','filter8encoder':'FILTER',
            'filter9encoder':'FILTER', #NB LOAD position
            'filterInserted':'FILTER','filterRemoved':'FILTER',
            'filterTolerance':'FILTER',
            'hiresStep':'GES','loresStep':'GES',
            'hiresEncoder':'GES','loresEncoder':'GES',
            'gesTolerance':'GES',
            'flsimInserted':'FLSIM','flsimRemoved':'FLSIM',
            'loresSwapStep':'GES','loresSwapEncoder':'GES'}
        self.thread_command_map={
            '0':'AUTO','1':'ANAMAF','2':'LOCKMON','3':None,
            '4':None,'5':None,'6':None,'7':None}
        SelectedConnection.SelectedSerial.__init__(self,*args,**kwargs)
        self.config={}
        if self.isOpen():
            self.initialize_galil()
    
    def _postConnect(self):
        """
        Called after establishing a connection.
        
        Subclass may implement and throw an exception if the connection
        is in any way unsuitable. Any return values are ignored. Exception text
        will be raised as a connect error.
        """
        expected_version='0.1000'
        #Get the current threads
        self.update_executing_threads_and_commands()
        if self.thread_command_map['0']==None:
            try:
                self.send_command_to_gail('XQ#AUTO,0')
                self.logger.warning("Executing #AUTO manually")
                self.update_executing_threads_and_commands()
            except GalilCommandNotAcknowledgedError:
                error_message="Galil not programed"
                raise SelectedConnection.ConnectError(error_message)
        #Get the software version
        response=self.send_command_to_gail('MG m2fsver')
        if response != expected_version:
            error_message=("Incompatible Firmware, Galil reported '%s', expected '%s'." % (response,expected_version))
            raise SelectedConnection.ConnectError(error_message)
    
    def initialize_galil(self):
        #Check to see if we are connecting to the Galil for the first time after boot
        bootup1=self.send_command_to_gail('MG bootup1')
        if bootup1=='0.0000':
            return
        self.logger.info("Programming galil defaults.")
        config=m2fsConfig.getGalilDefaults(self.SIDE)
        #make sure all the settings are there
        try:
            if config=={}:
                raise KeyError
            for name in self.settingName_to_variableName_map.keys():
                config[name]
        except KeyError:
            #The config file is corrupted, rebuild
            self.logger.critical('Galil'+self.SIDE+' configFile corrupted.'+
                'Rebuilding from hardcoded defaults.')
            try:
                for settingName, variableName in self.settingName_to_variableName_map.items():
                    config[settingName]=self.send_command_to_gail('MG '+variableName)
                m2fsConfig.setGalilDefaults(self.SIDE, config)
                self.config=config
                self.send_command_to_gail('bootup1=0')
                config={}
                self.logger.critical('Galil'+self.SIDE+' configFile rebuilt.')
                return
            except IOError,e:
                raise IOError("Failure during rebuild of defaults file.")
        #Send the config to the galil
        if config:
            try:
                for settingName, value in config.items():
                    variableName=self.settingName_to_variableName_map[settingName]
                    self.send_command_to_gail('%s=%s' % (variableName, value))
                self.config=config
                self.send_command_to_gail('bootup1=0')
            except IOError, e:
                raise IOError("Can not set galil defaults.") 
    
    def send_command_to_gail(self, command_string):
        """
        Send a command string to the galil and wait for the : or ? responses
        
        send multiple commands in one string at your own peril!
        If ? is in response or don't gen number of : expected for 
        command string then raise GalilCommandNotAcknowledgedError
        """
        #No command, return
        if not command_string:
            return ''
        #Make sure no unnecessary ;
        if command_string[-1]==';':
            command_string=command_string[:-1]
        #Count the number of commands
        num_colons_expected=command_string.count(';')+1
        #Send the command
        self.sendMessageBlocking(command_string)
        #Deal with the response
        if num_colons_expected>1:
            #More than 1 command, assume the commands only result in : or ?
            #not always the case
            response=self.receiveMessageBlocking(nBytes=num_colons_expected)
            #This error may be in error if commands didn't all elicit simple : or ?
            if '?' in response or response.count(':') !=num_colons_expected:
                raise GalilCommandNotAcknowledgedError(
                    "Galil did not acknowledge command '%s'" % command_string )
            response=''
        #Command is XQ get either : or ?
        elif command_string[:2]=='XQ':
            if ':' != self.receiveMessageBlocking(nBytes=1):
                raise GalilCommandNotAcknowledgedError(
                    "Galil did not acknowledge command '%s'" % command_string )
            response=''
        #MG command
        elif command_string[:2]=='MG':
            #we should get something, followed by a line ending, then just a ':'
            # if command is bad we may get some stuff and finally get a '?'
            response=self.receiveMessageBlocking()
            if ':' not in response:
                self.receiveMessageBlocking(nBytes=1)
        #All other commands
        else:
            #Check for a ?
            response=self.receiveMessageBlocking(nBytes=1)
            if response ==':':
                #command complete fine
                response=''
            elif response =='?':
                #command failed
                raise GalilCommandNotAcknowledgedError(
                    "Galil did not acknowledge command '%s'" % command_string )
            else:
                #there is more to the response
                response=response+self.receiveMessageBlocking()
                if response[-1]!=':':
                    self.receiveMessageBlocking(nBytes=1)
        return response.strip()
    
    def sendMessageBlocking(self, message):
        """ Send a string immediately, appends string terminator if needed"""
        if not self.isOpen():
            message="Connect before sending '%s' to %s" % (message,self.addr_str())
            self.logger.error(message)
            raise SelectedConnection.WriteError(message)
        if not message:
            return
        if message[-1]==';':
            message=message[:-1]+'\r'
        elif message[-1] != '\r':
            message+='\r'
        try:
            count=self.connection.write(message)
            self.connection.flush()
            self.logger.debug("BlockingSend sent: %s" % 
                message.replace('\r','\\r').replace('\n','\\n'))
        except serial.SerialException, e:
            self.handle_error(e)
            raise SelectedConnection.WriteError(str(e))
    
    def update_executing_threads_and_commands(self):
        """Retrieve and update the list of thread statuses from the galil"""
        #Ask galil for thread statuses
        response=self.send_command_to_gail(
            'MG "HX=",_HX0,_HX1,_HX2,_HX3,_HX4,_HX5,_HX6,_HX7')
        #response='HX= 1.0000 1.0000 1.0000 0.0000 0.0000 0.0000 0.0000 0.0000\r\n:'
        if response[-1] == '?' or response[0:3] !='HX=':
            raise GalilThreadUpdateException("Could not update galil threads.")
        response=response[4:response.find('\r')]
        #Update threads are no longer running
        for thread_number, thread_status in enumerate(response.split(' ')):
            if '0.' in thread_status:
                self.thread_command_map["%i"%thread_number]=None
            elif self.thread_command_map["%i"%thread_number] != None:
                #something is running and we aren't aware of it
                if thread_number < 3:
                    self.thread_command_map["%i"%thread_number]=(
                        ['AUTO','ANAMAF','LOCKMON'][thread_number])
                else:
                    #Can't actually query what is running so block everything
                    self.thread_command_map["%i"%thread_number]=(
                        'FOCUS FILTER FLSIM LREL HREL HRAZ GES')
    
    def get_motion_thread(self):
        """ Get ID of Galil thread to use for the command. None if none free""" 
        for i in '3456':
            if self.thread_command_map[i]==None:
                return i
        return None
            
    def add_galil_command_to_executing_commands(self, command, thread):
        self.thread_command_map[thread]=command
    
    def getDefault(self, settingName):
        try:
            variableName=self.settingName_to_variableName_map[settingName]
        except KeyError:
            return "!ERROR: %s not a valid setting" % settingName
        try:
            self.connect()
            self.send_command_to_gail('MG '+variableName)
            val=self.receiveMessageBlocking(nBytes=20)
            if val=='':
                val="ERROR: Galil failed to return value"
            return val
        except IOError, e:
            return str(e)
    
    def reset(self):
        try:
            self.connection.open()
            self.connection.write('RS\r')
            self.connection.flush()
            self.connection.close()
            self.connect()
            return 'OK'
        except IOError, e:
            return str(e)
    
    def shutdown(self):
        try:
            self.send_command_to_gail('HX3;XQ#SHTDWN,3')
            return 'OK'
        except IOError, e:
            return str(e)
        finally:
            self.add_galil_command_to_executing_commands('SHUTDOWN', 3)
    
    def setDefault(self, settingName, value):
        try:
            variableName=self.settingName_to_variableName_map[settingName]
        except KeyError:
            return "!ERROR: %s not a valid setting" % settingName
        try:
            self.connect()
            self.update_executing_threads_and_commands()
            #Check to see if the command is blocked
            if self.command_class_blocked(settingNameCommandClasses[settingName]):
                return "ERROR: Command is blocked. Try again later."
            self.send_command_to_gail('%=%s' % (variableName, value))
            self.config[settingName]=value
            m2fsConfig.setGalilDefaults(self.SIDE, config)
            return 'OK'
        except IOError, e:
            return str(e)
    
    def do_motion_command(self, command_class, command_string):
        try:
            #Make sure we are connected
            self.connect()
            #Make sure galil is initialized, e.g all parameters are set
            self.initialize_galil()
            #Update galil thread statuses
            self.update_executing_threads_and_commands()
            #Check to see if the command is blocked
            if self.command_class_blocked(command_class):
                return "ERROR: Command is blocked. Try again later."
            #Check for Abort or ELO
            if self.check_abort_switch():
                return "ERROR: Abort switch engaged."
            if False and self.check_elo_switch():
                return "ERROR: ELO switch engaged."
            #Get a thread for the command
            thread_number=self.get_motion_thread()
            if thread_number is None:
                return "ERROR: All available galil threads in use. Try again later"
        except IOError, e:
            return "ERROR: "+str(e)
        try:
            #Send the command to the galil
            self.send_command_to_gail(
                command_string.replace('<threadID>', thread_number))
            return 'OK'
        except IOError, e:
            return "ERROR: "+str(e)
        finally:
            # assume that the command is blocked anyway
            self.add_galil_command_to_executing_commands(command_class, thread_number)
            
    def check_abort_switch(self):
        """ Return True if abort switch engaged """
        try:
            val=int(float(self.send_command_to_gail('MG _AB')))
        except ValueError,e:
                raise IOError(str(e))
        return val != 1
    
    def check_elo_switch(self):
        """ Return True if elo switch engaged """
        try:
            val=int(float(self.send_command_to_gail('MG _TA3')))
            #Galil doesn't reset the ELO status automatically, need to do
            #MO*;SHA;MOA;MG _TA3 to confirm the reading
            # This means that we may also return false negatives, but there is
            # no good way to check you need to turn an axis on to make the bit
            # update and that carries all the extra logic required to pick which
            # axis you want to toggle 
            if val != 0:
                self.sendMessageBlocking('MO*;SHA;MOA;MG _TA3')
                try:
                    val=int(float(self.receiveMessageBlocking().split()[-2]))
                    return val != 0
                except IndexError, e:
                    raise IOError(str(e))
                #Discard the last :
                self.receiveMessageBlocking(nBytes=1)
        except ValueError,e:
            raise IOError(str(e))
        return val != 0
    
    def raw(self, command_string):
        try:
            #Make sure we are connected
            self.connect()
            #Make sure galil is initialized
            self.initialize_galil()
            #Send the command to the galil
            self.sendMessageBlocking(command_string)
            response=self.receiveMessageBlocking(nBytes=1024)
            response=response.replace('\r','\\r').replace('\n','\\n')
            #Update galil thread statuses
            self.update_executing_threads_and_commands()
            return response
        except IOError, e:
            self.logger.error(str(e))
            return "ERROR: "+str(e)
    
    def do_status_query(self, command_string):
        try:
            #Make sure we are connected
            self.connect()
            #Make sure galil is initialized
            self.initialize_galil()
            #Update galil thread statuses
            self.update_executing_threads_and_commands()
            #Send the command to the galil
            self.send_command_to_gail(command_string)
            response=self.receiveMessageBlocking()
            if response is '':
                raise IOError('No response received from galil. Consider retrying.')
            try:
                response=response.partition(':')[2]
                if response[:3]=='ERR':
                    return "ERROR: "+response[3:]
                else:
                    return response.strip()
            except IndexError:
                #Non-standard response, just return it
                return response
        except IOError, e:
            return "ERROR: "+str(e)
        except AttributeError:
            import pdb; pdb.set_trace()
    
    
    def command_class_blocked(self, name):
        blockingThreads=filter(lambda x:
                               x[1] and
                               (name in x[1] or 'SHUTDOWN' in x[1]),
            self.thread_command_map.items())
        return blockingThreads!=[]
    
    def get_filter(self):
        command_string="XQ#%s,%s" % ('GETFILT', '7')
        return self.do_status_query(command_string)
    
    def get_loel(self):
        command_string="XQ#%s,%s" % ('GETLRTL', '7')
        return self.do_status_query(command_string)
        
    def get_hrel(self):
        command_string="XQ#%s,%s" % ('GETHRTL', '7')
        return self.do_status_query(command_string)
    
    def get_hraz(self):
        command_string="XQ#%s,%s" % ('GETHRAZ', '7')
        return self.do_status_query(command_string)
    
    def get_foc(self):
        command_string="XQ#%s,%s" % ('GETFOC', '7')
        return self.do_status_query(command_string)
    
    def get_ges(self):
        command_string="XQ#%s,%s" % ('GETGES2', '7')
        return self.do_status_query(command_string)
        
    def get_flsim(self):
        command_string="XQ#%s,%s" % ('GETFLSI', '7')
        return self.do_status_query(command_string)
        
    def set_filter(self, filter):
        command_class='FILTER'
        command_string="a[<threadID>]=%s;XQ#PICKFIL,<threadID>" % filter
        return self.do_motion_command(command_class, command_string)
    
    def set_loel(self, position):
        command_class='LREL'
        command_string="a[<threadID>]=%s;XQ#SETLRTL,<threadID>" % position
        return self.do_motion_command(command_class, command_string)
        
    def set_hrel(self, position):
        command_class='HREL'
        command_string="a[<threadID>]=%s;XQ#SETHRTL,<threadID>" % position
        return self.do_motion_command(command_class, command_string)
    
    def set_hraz(self, position):
        command_class='HRAZ'
        command_string="a[<threadID>]=%s;XQ#SETHRAZ,<threadID>" % position
        return self.do_motion_command(command_class, command_string)
    
    def set_foc(self, position):
        command_class='FOCUS'
        command_string="a[<threadID>]=%s;XQ#SETFOC,<threadID>" % position
        return self.do_motion_command(command_class, command_string)
    
    def set_ges(self, position):
        """Position should be either HIRES, LORES, or LRSWAP"""
        command_class='GES'
        command_string="XQ#%s,<threadID>" % position
        return self.do_motion_command(command_class, command_string)
    
    def insert_filter(self, *args):
        command_class='FILTER'
        command_string="XQ#INFESIN,<threadID>"
        return self.do_motion_command(command_class, command_string)
    
    def remove_filter(self, *args):
        command_class='FILTER'
        command_string="XQ#RMFESIN,<threadID>"
        return self.do_motion_command(command_class, command_string)
    
    def insert_flsim(self, *args):
        command_class='FLSIM'
        command_string="XQ#INFLSIN,<threadID>"
        return self.do_motion_command(command_class, command_string)
    
    def remove_flsim(self, *args):
        command_class='FLSIM'
        command_string="XQ#RMFLSIN,<threadID>"
        return self.do_motion_command(command_class, command_string)
    
    def calibrate_lrel(self, *args):
        command_class='LREL'
        command_string="XQ#CALLRT,<threadID>"
        return self.do_motion_command(command_class, command_string)
        
    def calibrate_hrel(self, *args):
        command_class='HREL'
        command_string="XQ#CALHRTL,<threadID>"
        return self.do_motion_command(command_class, command_string)
    
    def calibrate_hraz(self, *args):
        command_class='HRAZ'
        command_string="XQ#CALHRAZ,<threadID>"
        return self.do_motion_command(command_class, command_string)
    
    def calibrate_ges(self, *args):
        command_class='GES'
        command_string="XQ#CALGES,<threadID>"
        return self.do_motion_command(command_class, command_string)
    
