import serial, logging
import SelectedConnection
from m2fsConfig import m2fsConfig

EXPECTED_M2FS_DMC_VERSION='0.1000'
#Timeout to use if we must force open a connection to the galil to do a reset
GALIL_RESET_CONNECTION_TIMEOUT=0.5
#Normal io timout for galil communication
GALIL_TIMEOUT=0.5

def escapeString(string):
    return string.replace('\n','\\n').replace('\r','\\r')

class GalilThreadUpdateException(IOError):
    """ Unable to update list of threads executing on the Galil """
    pass

class GalilCommandNotAcknowledgedError(IOError):
    """ Gaili fails to acknowledge a command, e.g. didn't respond with ':' """
    pass

def stringIsNumber(string):
    """ Return true iff a string casts into a float sucessfully """
    try:
        float(string)
        return True
    except ValueError:
        return False

class GalilSerial(SelectedConnection.SelectedSerial):
    """ 
    Galil DMC-4183 Controller Class
    
    This class extents the SelectedSerial implementation of SelectedConnection
    with routines needed to control the Galil. It grew out of a potentially
    misguided desire to abstract some stuff ouut of the galil agent.
    As is all sends and receives are performed using blocking sends and receives
    so it never really makes use of the whole Selected bit. It does get used as
    it allows trapping of unsolicited messages from the galil, which is useful
    for trapping firmware execution errors.
    
    Firmware errors are trapped by setting the default_message_received_callback
    to _unsolicited_galil_message_handler. This handler logs the unexpected 
    message and checks the message to see if it indicates an error. If it does 
    it sets an error flag so that the next incomming command gets a message 
    about the error. An attempt is made to keep the error targeted to the 
    original source, but this is not possible in all cases. (e.g. only a filter 
    command would see an error that happend while the galil was executing filter
    related code. See _getErrorMessage and _setErrorFlag for more info.
    
    The controller uses the concept of command classes to keep track of which
    commands block other commands. E.g. if a command in class GES is executing 
    changing a parameter with the same class would be blocked. The classes are
    FOCUS, FILTER, FLSIM, LREL, HREL, HRAZ, GES, & SHUTDOWN. UNKNOWN is used in
    the situations where a thread is running but the specific command class is
    not known. It blocks all command classes
    
    The class maintains the last known position of the lores elevation,
    hires elevation, hires azimuth, and ges disperser slide, provided no errors
    are encountered as a convenience to the observer. When one of these axes
    is uncalibrated and reports as such the last known position will be reported
    as normal with the string 'LASTKNOWN' appended. The position is only updated
    when explicitly queired and is removed both whenever any response other than
    uncalibrated is received and when a motion is started.
    
    General flow is:
        initialize attributes
        initialize the SelectedSerial superclass
            _postconnect hook is used to verify galil is running and has proper
            version software
        initialize the galil with all the user parameters stored in the 
            appropriate m2fs_galil (R|B) conf file.
        get a command
            check for any outstanding command related or general errors
                abort and return the error if it exists, else continue
            connect if not connected
            check what threads are running
            initialize galil if necessary (initializeg sets a parmaeter to 0
                that the galil sets to 1 at boot)
            grab a free hardware thread for the command, tell the galil to 
                execute it, mark the thread as in use, and register the class
                of commands to which the command at hand belongs as blocked
                Provided:
                The command wasn't blocked and there was a free thread, in which
                case respond with try again later
            if a parameter is changed, update it on the galil and in the conf
            file (via m2fsConfig
    """
    def __init__(self, device, side):
        """
        Initialize the Galil object
        
        Requires argument side to indicate which M2FS galil we are working
        with ('R' or 'B') 
        Additional rguments are as defined in SelectedSerial
        """
        if side !='R' and side !='B':
            raise ValueError('Side must be R or B')
        self.SIDE=side
        #Register setting name to galil parameter map
        # It is done this way because we want readable parameter names
        # in the config file, but the galil limits us to 7 characters for
        # variables.
        self.settingName_to_variableName_map={
            'filter1encoder':'felencp[0]','filter2encoder':'felencp[1]',
            'filter3encoder':'felencp[2]','filter4encoder':'felencp[3]',
            'filter5encoder':'felencp[4]','filter6encoder':'felencp[5]',
            'filter7encoder':'felencp[6]','filter8encoder':'felencp[7]',
            'filter9encoder':'felencp[8]', #NB filter9=LOAD position
            'filterInserted':'fesinsp','filterRemoved':'fesremp',
            'filterTolerance':'feselrg',
            'hiresStep':'geshrp','loresStep':'geslrp',
            'hiresEncoder':'geshrep','loresEncoder':'geslrep',
            'gesTolerance':'gesenct',
            'flsimInserted':'flsinsp','flsimRemoved':'flsremp',
            'loresSwapStep':'gesgsp','loresSwapEncoder':'gesgsep'}
        #Define which variables are in which command classes
        self.settingNameCommandClasses={
            'filter1encoder':'FILTER','filter2encoder':'FILTER',
            'filter3encoder':'FILTER','filter4encoder':'FILTER',
            'filter5encoder':'FILTER','filter6encoder':'FILTER',
            'filter7encoder':'FILTER','filter8encoder':'FILTER',
            'filter9encoder':'FILTER', #NB filter9=LOAD position
            'filterInserted':'FILTER','filterRemoved':'FILTER',
            'filterTolerance':'FILTER',
            'hiresStep':'GES','loresStep':'GES',
            'hiresEncoder':'GES','loresEncoder':'GES',
            'gesTolerance':'GES',
            'flsimInserted':'FLSIM','flsimRemoved':'FLSIM',
            'loresSwapStep':'GES','loresSwapEncoder':'GES'}
        #Initialize the dict of which commands are executing on which
        # Galil hardware threads. The first three automatically run: the galil
        # starts #AUTO at power-on and #AUTO starts #ANAMAF and #MOMONI
        # the values are set to None if nothing is executing and a tuple
        # consisting of the command_class and the specific command (or None if
        # not known). In such situations where there was a command already
        # executing on the galil but it began prior to the connection with the
        # galil, the command_class is set to UNKNOWN and the specific command is
        # set to None. Commands may be made to block multiple command classes by
        # setting the first element of the tuple to a list of command class
        # strings blocked by the command.
        self.thread_command_map={
            '0':('AUTO','XQ#AUTO,0'),
            '1':('ANAMAF','#ANAMAF'),
            '2':('MOMONI','#MOMONI'),
            '3':None, '4':None, '5':None, '6':None, '7':None}
        # Error flag store
        self.errorFlags={}
        #Perform superclass initialization, note we implement the _postConnect
        # hook for the galil, see below
        SelectedConnection.SelectedSerial.__init__(self, device, 115200,
            timeout=GALIL_TIMEOUT, default_message_received_callback=
                self._unsolicited_galil_message_handler)
        self.logger=logging.getLogger('GalilCon'+side)
        self.logger.setLevel(SelectedConnection.DEFAULT_LOG_LEVEL)
        #Override the default message terminator for consistency. Doesn't matter
        #since we also override the _terminateMessage function
        self.messageTerminator='\r'
        #If we've sucessfully connected, go ahead and initialize the galil
        # see the command for what this means
        if self.isOpen():
            try:
                self._initialize_galil()
            except IOError:
                pass

    def _unsolicited_galil_message_handler(self, message_source, message):
        """
        Handle any unexpected messages from the Galil
        
        The only expected uncolicited message would be caused by the #CMDERR
        subroutine executing due to a bug in m2fs.dmc. These errors report
        an error code (see comref.pdf, TC), the thread which encountered the
        error, and the line number (as reported by the LS command). To obtain a
        listing of the code run the script download_galil_code.sh.
        
        If the message indicates a command error occured, extract the details, 
        figure out the command class and set a flag so the user will be notified
        by the _getErrorMessage call.
        
        Command error messages take the form 
        '#!CMDERR:ERR <#> (thread <#> line <#>):\r\n'
        
        If the message isn't a command error log a warning.
        """
        if 'CMDERR' in message:
            #extract the error
            parts=message.split()
            errno=str(int(float(parts[1])))
            threadno=str(int(float(parts[3])))
            lineno,junk,junk=parts[5].partition(')')
            lineno=str(int(float(lineno)))
            offending_cmd_info=self.thread_command_map[threadno]
            #Generate an error message, try to make it informative, log it
            if errno=='22':
                errmsg='Limit switch error while attempting '
            else:
                errmsg=(('Galil firmware encountered error %s on line %s' %
                    (errno, lineno)) +' while executing ')
            if offending_cmd_info:
                specific_cmd_str=offending_cmd_info[1]
                cmd_class_str=offending_cmd_info[0]
                if specific_cmd_str:
                    errmsg+=specific_cmd_str.replace('<threadID>',threadno)
                elif cmd_class_str == 'UNKNOWN':
                    errmsg+='an unknown command.'
                else:
                    errmsg+='a'+cmd_class_str+'command.'
                self.logger.error(errmsg)
            else:
                errmsg+='a thread on which nothing was believed to be running.'
                self.logger.critical(errmsg)
            #Set a flag so the next time a related function is called the error
            # is reported (if we know what was running)
            if offending_cmd_info:
                self._setErrorFlag(cmd_class_str, errmsg)
        else:
            self.logger.warning("Got unexpected, unsolicited message '%s'"
                % message)
    
    def _setErrorFlag(self, command_class, err):
        """
        Flag the specified command class for an out of band error
        
        UNKNOWN serves as a global error affecting all command classes
        """
        self.errorFlags[command_class]=err

    def _getErrorMessage(self, command_class):
        """
        Return message set by _setErrorFlag for the class or raise ValueError
        
        If _setErrorFlag has set an error affecting the passed command class
        then that message is returned and the error is cleared. Otherwise 
        ValueError is raised. command_class may be a command class or a list of
        classes. Errors specific to the command class are returned prior to 
        general errors. If multiple classes are passed the return of errors is
        prioritized by order. Only one error is returned per call. At most one
        error exists for a given command class.
        """
        if type(command_class)==str:
            command_class=[command_class]
        for cclass in command_class:
            if cclass in self.errorFlags.keys():
                return self.errorFlags.pop(cclass)
        if 'UNKNOWN' in self.errorFlags.keys():
            return self.errorFlags.pop('UNKNOWN')
        raise ValueError

    def _postConnect(self):
        """
        Implement the post-connect hook
        
        With the galil we need to do a few things prior to actually accepting
        the connection as healthy:
        1) Get the list of currently executing threads. 
        2) If nothing is executing in thread 0 start #AUTO, warn, & update the
            threads again. If #AUTO won't execute fail by throwing ConnectError
        3) Query the galil for the software version. If if doesn't match the
            expected version fail with a ConnectError
        """
        #Get the current threads
        self._update_executing_threads_and_commands()
        if self.thread_command_map['0']==None:
            try:
                self._send_command_to_galil('XQ#AUTO,0')
                self.logger.warning("Executing #AUTO manually")
                self._update_executing_threads_and_commands()
            except GalilCommandNotAcknowledgedError:
                error_message="Galil not programed"
                raise SelectedConnection.ConnectError(error_message)
        #Get the software version
        response=self._send_command_to_galil('MG m2fsver')
        if response != EXPECTED_M2FS_DMC_VERSION:
            error_message=("Incompatible Firmware, Galil reported '%s', expected '%s'." % (response,expected_version))
            raise SelectedConnection.ConnectError(error_message)
    
    def _initialize_galil(self):
        """
        Make sure configurable parameters are pushed to the galil
        
        There are a variety of position settings for the various axes which may
        change with time or otherwise need adjusting. Instead of changing the 
        hardcoded defaults we use the files m2fs_galilR.conf & m2fs_galilB.conf
        
        Procedure is as follows:
        Check to see if we are connecting for the first time since boot. If not
        return otherwise continue.
        Get the parameter values for the galil (R | B) from m2fsConfig
        Verify all of the settings are there, if not, the backing file got 
        corrupted and needs to be rebuilt, so do so, querying the galil for the 
        needed values and return after marking the galil as initialized.
        The translation between galil parameter name and config file setting
        is defined by self.settingName_to_variableName_map.
        Finally, set each of the parmeters on the galil and mark it as 
        initialized
        
        Raise IOError if the defaults can not be programmed.
        """
        bootup1=self._send_command_to_galil('MG bootup1')
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
            #The config file is corrupted, this is a fatal error
            errMsg='Galil'+self.SIDE+' configFile corrupted.'+
                'git reset --hard likely needed'
            self.logger.critical(errorMsg)
            raise IOError(errMsg)
        #Send the config to the galil
        try:
            #NB we are only here if bootup1=1, which implies nothing but the
            # basic threads are running and thus we are guaranteed the
            # settings are not blocked by some executing thread
            for settingName, value in config.items():
                variableName=self.settingName_to_variableName_map[settingName]
                self._send_command_to_galil('%s=%s' % (variableName, value))
            self.config=config
            self._send_command_to_galil('bootup1=0')
        except IOError, e:
            raise IOError("Can not set galil defaults.") 

    def _send_command_to_galil(self, command_string):
        """
        Send a command string to the galil, wait for immediate response

        Silently ignore an empty command.
        
        The command_string must not include spurrious ; or pathological commands
        such as MG ":::".
        
        Raise GalilCommandNotAcknowledgedError if the galil does not acknowledge
        any part of the command.
        
        The Galil may be sent multiple commands at a time as cmd1;cmd2;...cmdN.
        Each command will generate a : or ? indicating acceptance or an issue,
        respectively. Commands may cause the galil to response with data, in
        which case the response will take the form "data\r\n:".
        So for the example format above we might get ?foobar\r\n:...:

        Procedure is as follows:
        Send the command string to the galil
        grab a singe byte from the galil and if it isn't a : or a ? listen for 
        a \n delimeted response followed by a :.
        Repeat this for each of the commands in the command_string
        
        Return a merged string of the responses to the individual commands. 
        Note the : ? are cons considered responses. ? gets the exception and :
        gets an empty string. The responses are stripped of whitespace before
        merging and will run together.
        """
        #No command, return
        if not command_string:
            return ''
        #Make sure no unnecessary ;
        if command_string[-1]==';':
            command_string=command_string[:-1]
        #Count the number of commands, ignore pathological case of MG ";"
        num_colons_expected=command_string.count(';')+1
        #Send the command(s)
        self.sendMessageBlocking(command_string, connect=False)
        #Initialize the for loop
        acknowledgements=0 #acknowledgements for commands sent in command_string
        commandReplies=num_colons_expected*[''] #store for replies beyond :|? 
        galilReply=''
        galilProtocolError=False
        for i in range(0,num_colons_expected):
            #Get the first byte from the galil, typically this will be it
            response=self.receiveMessageBlocking(nBytes=1)
            # 3 cases :, ?, or stuff followed by /r/n:
            #case 1, command succeeds but returns nothing, return
            if response ==':':
                acknowledgements+=1
            #command fails
            elif response =='?':
                pass
            #command is returning something
            else:
                #do a blocking receive on \n
                response=response+self.receiveMessageBlocking()
                #...and a single byte read to grab the :
                confByte=self.receiveMessageBlocking(nBytes=1)
                if confByte==':':
                    acknowledgements+=1
                    commandReplies[i]=response.strip()
                else:
                    #Consider it a failure, but set a flag to log it once we've
                    # got everything. Add the byte to the response for logging
                    galilProtocolError=True
                    response+=confByte
            #Build up a record of everything we get from the galil in response
            # to command string incase we need to log it
            galilReply+=response
        #warn that something was fishy with the galil
        if galilProtocolError:
            self.logger.warning(
                "Galil did not adhere to protocol '%s' got '%s'" %
                (command_string, galilReply) )
        #We didn't get acknowledgements for all the commands, fail
        if acknowledgements != num_colons_expected:
            raise GalilCommandNotAcknowledgedError(
                "ERROR: Galil did not acknowledge command '%s' (%s)" %
                (command_string, galilReply) )
        #Join all of replies from the commands and return them as a single
        # string
        return ''.join(commandReplies)
    
    def _terminateMessage(self, message):
        """ Override default: Galil requires \r without a preceeding ; """
        if message[-1]==';':
            message=message[:-1]+'\r'
        elif message[-1] != '\r':
            message+='\r'
        return message
    
    def _update_executing_threads_and_commands(self):
        """
        Retrieve and update the list of thread statuses from the galil
        
        The galil doesn't provide a way to determine what program is executing
        on a thread, just that the thread is running. By convention, threads 0-2
        are used by the galil code as #AUTO, #ANAMAF, & #MOMONI, respectively. 
        Threads 3-6 are used for motion commands and thread 7 is used for
        status queries.
        
        Ask the galil what is running, fail if we don't recognize the response.
        For each inactive thread, mark the thread as not running anything by
        setting self.thread_command_map[idle_thread_number]=None
        For each executing thread, if we don't have a record of mark it as 
        active. For the first three threads, we can assign the name based on
        convention. For the remaining, mark the thread as running all command
        classes. While this is impossible there is no way to tell which 
        particular command class should be blocked. 
        """
        #Ask galil for thread statuses
        # The Expected response is of the form:
        # 'HX= 1.0000 1.0000 1.0000 0.0000 0.0000 0.0000 0.0000 0.0000'
        response=self._send_command_to_galil(
            'MG "HX=",_HX0,_HX1,_HX2,_HX3,_HX4,_HX5,_HX6,_HX7')
        if response[-1] == '?' or response[0:3] !='HX=':
            raise GalilThreadUpdateException("Could not update galil threads.")
        #Extract the part we care about
        response=response[4:]
        #Update threads are no longer running
        for thread_number, thread_status in enumerate(response.split(' ')):
            if '0.' in thread_status:
                self.thread_command_map["%i"%thread_number]=None
            elif self.thread_command_map["%i"%thread_number] == None:
                #something is running and we aren't aware of it
                if thread_number < 3:
                    self.thread_command_map["%i"%thread_number]=(
                        ['AUTO','ANAMAF','MOMONI'][thread_number])
                else:
                    #Can't actually query what is running so block
                    # all the command classes
                    self._add_galil_command_to_executing_commands(
                        None, 'UNKNOWN', thread_number)
    
    def _get_motion_thread(self):
        """
        Get ID of Galil thread to use for the command. None if none free
        
        This assumes the thread_command_map is current.
        By convention we use threads 3-6 for motion.
        """
        for i in '3456':
            #check to see if something is executing on the thread
            if self.thread_command_map[i]==None:
                return i
        return None
            
    def _add_galil_command_to_executing_commands(self, command,
                                                 command_class, thread):
        """
        Mark command as executing on thread.
        """
        self.thread_command_map[str(thread)]=(command_class, command)
    
    def _do_motion_command(self, command_class, command_string):
        """
        Execute a motion command, connecting and starting up if needed
        
        Connect to the galil
        Initialize the galil (function just returns if not needed)
        Update our knowledge of what is running
        Fail if the command if blocked
        Test for ELO & ABORT switched beign engaged. This is VERY UNRELIABLE.
        Get a thread to execute the command on, failing if none available
        Tell the galil to execute the the command on the proper thread
        Respond 'OK' with success and 'ERROR: '+message on failure. 
        Always assume that the command started sucessfully and add it to the 
        store of executing commands. If we are wrong no harm done and it will
        be dropped next time we update anyway.
        """
        try:
            #Make sure we are connected
            self.connect()
            #Make sure galil is initialized, e.g all parameters are set
            self._initialize_galil()
            #Update galil thread statuses
            self._update_executing_threads_and_commands()
            #Check to see if the command is blocked
            if self._command_class_blocked(command_class):
                return "ERROR: Command is blocked. Try again later."
            #Check for Abort or ELO
            if self.check_abort_switch():
                return "ERROR: Abort switch engaged."
            if self.check_elo_switch():
                return "ERROR: ELO switch engaged."
            #Get a thread for the command
            thread_number=self._get_motion_thread()
            if thread_number is None:
                return "ERROR: All available galil threads in use. Try again later"
        except IOError, e:
            return "ERROR: "+str(e)
        try:
            #Send the command to the galil
            self._send_command_to_galil(
                command_string.replace('<threadID>', thread_number))
            return 'OK'
        except IOError, e:
            return "ERROR: "+str(e)
        finally:
            # assume that the command is blocked anyway
            self._add_galil_command_to_executing_commands(
                command_string, command_class, thread_number)
    
    def _do_status_query(self, command_string):
        """
        Execute a status command, connecting and starting up if needed
        
        Connect to the galil
        Initialize the galil (function just returns if not needed)
        Update our knowledge of what is running
        Send the command to the galil, status commands are never blocked
        Listen for a response
        Check to see if the response indicates an error ('ERR' will follow the 
        first :. If so prepend ERROR: to the tail of the message.
        return the message
        Trap all errors and return 'ERROR: '+message
        """
        try:
            #Make sure we are connected
            self.connect()
            #Make sure galil is initialized
            self._initialize_galil()
            #Update galil thread statuses
            self._update_executing_threads_and_commands()
            #Send the command to the galil
            self._send_command_to_galil(command_string)
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
    
    def _command_class_blocked(self, cclass):
        """
        Return true if the command class is blocked by an executing thread
        
        cclass may be a command class name or list of command class names.
        
        Look through thread_command_map and find all threads running the
        command class cclass (or subset if list), 'SHUTDOWN', or 'UNKNOWN'. The
        latter two blocks all command classes. If any threads are found return
        true.
        
        See __init__ for the format of thread_command_map
        """
        def filterFunc(cmd_tuple):
            """
            Return true if cclass (or element, if list) is blocked by cmd_tuple.
            
            cmd_tuple must be a (command_class, command) tuple or None
            from  self.thread_command_map.values().
            command_class is either a singular class or a list of classes
            """ 
            if cmd_tuple!=None:
                cmd_classes=cmd_tuple[0]
                if 'SHUTDOWN' in cmd_classes or 'UNKNOWN' in cmd_classes:
                    return True
                else:
                    if type(cclass)==list:
                        for x in cclass:
                            if x in cmd_classes:
                                return True
                    elif cclass in cmd_classes:
                        return True
            return False
        blockingCommands=filter(filterFunc, self.thread_command_map.values())
        return blockingCommands!=[]
    
    def _lastknownPositionWrapper(self, axis, reply, replyGoodFunc):
        """
        Process reply from status query for last known position monitoring
        
        Arguments
        1)The axis for the position query reply being checked:
        'LREL', 'HREL', 'HRAZ', or 'GES'
        2) The reply string from the status query to the galil.
        3) A function of one argument that returns true iff the reply string
        reports a position that should be considered the 'last known' position
        of the axis
        
        If the reply is the string UNCALIBRATED then, if available, the
        last know position is retrieved from disk and returned with LASTKNOWN
        appended. If not available then the raw reply is returned.
        Otherwise, if replyGoodFunc(reply) evaluates to true then the last known
        position for the specifed axis is updated on disk. If the function
        evaluates to false then the lask known position is cleared. For both of
        the latter cases reply is returned unmodified.
        """
        if reply=='UNCALIBRATED':
            try:
                lastknown=m2fsConfig.getGalilLastPosition(self.SIDE, axis)
                return lastknown+' LASTKNOWN'
            except ValueError:
                return reply
        elif replyGoodFunc(reply):
            m2fsConfig.setGalilLastPosition(self.SIDE, axis, reply)
            return reply
        else:
            m2fsConfig.setGalilLastPosition(self.SIDE, axis, None)
            return reply
    
    def check_abort_switch(self):
        """ Return true if abort switch engaged """
        try:
            val=int(float(self._send_command_to_galil('MG _AB')))
        except ValueError,e:
                raise IOError(str(e))
        return val != 1
    
    def check_elo_switch(self):
        """
        Returns true if Electronic Lockout switch is engaged
        
        The ELO input is bridged with DI7. 1 is disengaged 0 is engaged.
        """
        return 0==int(float(self._send_command_to_galil('MG@IN[7]')))
    
    def reset(self):
        """ Reset the galil
        
        Directly use the underlying serial functions. self.connect may fail if
        the galil has entered some weird state. 
        """
        try:
            #If the connection isn't open force open a connection,
            # disregarding normal procedures (something screwy could be up,
            # hence the reset. We will close the connection right away anyway so
            # it doesn't matter
            if not self.isOpen():
                self.connection=serial.Serial(self.port, baudrate=self.baudrate,
                                          timeout=GALIL_RESET_CONNECTION_TIMEOUT)
            #send the command
            self._send_command_to_galil('RS')
            #close the connection
            self.close()
            #connect like normal
            self.connect()
            return 'OK'
        except (IOError, serial.SerialException), e:
            return 'ERROR: Reset may have failed (%s)' % str(e)
    
    def shutdown(self):
        """
        Tell the galil to prepare for poweroff
        
        It is not vital that this routine be called prior to power off, just a
        good idea. The galil code will gracefully handle an abrupt power
        failure.
        
        Kill thread 3 and execute shutdown on it. SHTDWN must be executed on 
        thread three. If motion was being controlled by thread 3 then shtdwn 
        will stop it.
        add shutdown to the list of commands running. It blocks all other motion
        commands.        
        """
        try:
            m2fsConfig.clearGalilLastPositions(self.SIDE)
            self._send_command_to_galil('HX3;XQ#SHTDWN,3')
            return 'OK'
        except IOError, e:
            return str(e)
        finally:
            self._add_galil_command_to_executing_commands('HX3;XQ#SHTDWN,3',
                                                          'SHUTDOWN', 3)

    def getDefault(self, settingName):
        """
        Retrieve the value of a galil setting
        
        get the galil parameter name
        tell galil to report it's value
        listen for the response (it won't be long, 20 chars is excessive)
        return the value as a string or an error message as a string
        invalid parameters are user errors and will generate a '!ERROR' message.
        """
        try:
            variableName=self.settingName_to_variableName_map[settingName]
        except KeyError:
            return "!ERROR: %s not a valid setting" % settingName
        try:
            self.connect()
            val=self._send_command_to_galil('MG '+variableName)
            if val=='':
                val="ERROR: Galil failed to return value"
            return val
        except IOError, e:
            return str(e)
    
    def setDefault(self, settingName, value):
        """
        Set a new value for galil setting
        
        make sure we are connected, initialized, and update the currently
        executing threads
        ensure the setting is a real setting
        ensure the setting isn't blocked by an executing thread
            return error message if so
        Set the new value on the galil and with m2fsConfig
        CAUTION: No provision is made to ensure the value is suitable
        return 'OK'
        """
        try:
            variableName=self.settingName_to_variableName_map[settingName]
        except KeyError:
            return "!ERROR: %s not a valid setting" % settingName
        try:
            self.connect()
            self._initialize_galil()
            self._update_executing_threads_and_commands()
            #Check to see if the command is blocked
            if self._command_class_blocked(
                self.settingNameCommandClasses[settingName]):
                return "ERROR: Command is blocked. Try again later."
            self._send_command_to_galil('%s=%s' % (variableName, value))
            m2fsConfig.setGalilDefault(self.SIDE, settingName, value)
            return 'OK'
        except IOError, e:
            return str(e)
    
    def raw(self, command_string):
        """
        Send a raw string to the galil and wait for the response
        
        make sure we are connected and initialized
        send the string to the galil
        get a response up to 1024 characters in length
        finally update the executing threads incase the command started 
        something
        """ 
        try:
            #Make sure we are connected
            self.connect()
            #Make sure galil is initialized
            self._initialize_galil()
            #Send the command to the galil
            self.sendMessageBlocking(command_string, connect=False)
            response=self.receiveMessageBlocking(nBytes=1024)
            response=escapeString(response)
            #Update galil thread statuses
            self._update_executing_threads_and_commands()
            return response
        except IOError, e:
            self.logger.error(str(e))
            return "ERROR: "+str(e)
    
    #The remaining commands are wrappers for each of the galil tasks
    # Each generates a basic command string to be sent to the galil
    # for the motion command, the thread ID is determined later and a
    # placeholder is used, which is filled in when _do_motion_command determines
    # which thread is to be used.
    # Note that the setting routines may start a move which takes 10s of seconds
    # to complete. The 'OK' returned only indicates that the move has begun
    def get_filter(self):
        """ Return the current filter position """
        command_class='FILTER'
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        command_string="XQ#%s,%s" % ('GETFILT', '7')
        return self._do_status_query(command_string)
    
    def get_loel(self):
        """ Return the Lores Elevation """
        command_class='LREL'
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        command_string="XQ#%s,%s" % ('GETLRTL', '7')
        reply=self._do_status_query(command_string)
        return self._lastknownPositionWrapper('LREL', reply, stringIsNumber)
    
    def get_hrel(self):
        """ Return the Hires Elevation """
        command_class='HREL'
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        command_string="XQ#%s,%s" % ('GETHRTL', '7')
        reply=self._do_status_query(command_string)
        return self._lastknownPositionWrapper('HREL', reply, stringIsNumber)
    
    def get_hraz(self):
        """ Return the Hires azimuth """
        command_class='HRAZ'
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        command_string="XQ#%s,%s" % ('GETHRAZ', '7')
        reply=self._do_status_query(command_string)
        return self._lastknownPositionWrapper('HRAZ', reply, stringIsNumber)
    
    def get_ges(self):
        """ Return the disperser slide status """
        command_class='GES'
        command_string="XQ#%s,%s" % ('GETGES2', '7')
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        reply=self._do_status_query(command_string)
        func=lambda x: x[:5] in ('HIRES','LORES', 'LRSWAP')
        return self._lastknownPositionWrapper('GES', reply, func)
    
    def get_foc(self):
        """ Return the focus position """
        command_string="XQ#%s,%s" % ('GETFOC', '7')
        return self._do_status_query(command_string)
    
    def get_flsim(self):
        """ Return the FLS imager pickoff position """
        command_class='FLSIM'
        command_string="XQ#%s,%s" % ('GETFLSI', '7')
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        return self._do_status_query(command_string)
    
    def set_filter(self, filter):
        """ Select a filter position """
        if filter not in ['1','2','3','4','5','6','7','8','9','10']:
            return '!ERROR: Valid fliter choices are 1-10. 9=None 10=load.'
        command_class='FILTER'
        command_string="a[<threadID>]=%s;XQ#PICKFIL,<threadID>" % filter
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        return self._do_motion_command(command_class, command_string)
    
    def set_loel(self, position):
        """ Set the Lores elevation """
        try:
            int(position)
        except ValueError:
            return '!ERROR: Lores elevation must be specified as an integer.'
        command_class='LREL'
        command_string="a[<threadID>]=%s;XQ#SETLRTL,<threadID>" % position
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        m2fsConfig.setGalilLastPosition(self.SIDE, 'LREL', None)
        return self._do_motion_command(command_class, command_string)
        
    def set_hrel(self, position):
        """ Set the Hires elevation """
        try:
            int(position)
        except ValueError:
            return '!ERROR: Hires elevation must be specified as an integer.'
        command_class='HREL'
        command_string="a[<threadID>]=%s;XQ#SETHRTL,<threadID>" % position
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        m2fsConfig.setGalilLastPosition(self.SIDE, 'HREL', None)
        return self._do_motion_command(command_class, command_string)
    
    def set_hraz(self, position):
        """ Set the Hires azimuth """
        try:
            int(position)
        except ValueError:
            return '!ERROR: Hires azimuth must be specified as an integer.'
        command_class='HRAZ'
        command_string="a[<threadID>]=%s;XQ#SETHRAZ,<threadID>" % position
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        m2fsConfig.setGalilLastPosition(self.SIDE, 'HRAZ', None)
        return self._do_motion_command(command_class, command_string)
    
    def set_foc(self, position):
        """ Set the focus value """
        try:
            float(position)
        except ValueError:
            return '!ERROR: Focus must be specified as a number.'
        command_class='FOCUS'
        command_string="a[<threadID>]=%s;XQ#SETFOC,<threadID>" % position
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        return self._do_motion_command(command_class, command_string)
    
    def set_ges(self, position):
        """Position should be either HIRES, LORES, or LRSWAP"""
        if position not in ['HIRES','LORES','LRSWAP']:
            return '!ERROR: %s is not one of HIRES, LORES, or LRSWAP' % position
        if 'LRSWAP' in position:
            command_class=['GES', 'LREL']
            try:
                return self._getErrorMessage(command_class)
            except ValueError:
                pass
            m2fsConfig.setGalilLastPosition(self.SIDE, 'GES', None)
            m2fsConfig.setGalilLastPosition(self.SIDE, 'LREL', None)
        else:
            command_class='GES'
            try:
                return self._getErrorMessage(command_class)
            except ValueError:
                pass
            m2fsConfig.setGalilLastPosition(self.SIDE, 'GES', None)
        command_string="XQ#%s,<threadID>" % position
        return self._do_motion_command(command_class, command_string)
    
    def insert_filter(self, *args):
        """
        Command the insertion of the current filter
        
        Note that FILTER automatically inserts and removes as needed. This is a 
        debugging convenience routine.
        """
        command_class='FILTER'
        command_string="XQ#INFESIN,<threadID>"
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        return self._do_motion_command(command_class, command_string)
    
    def remove_filter(self, *args):
        """
        Command the removal of the current filter
        
        Note that FILTER automatically inserts and removes as needed. This is a
        debugging convenience routine.
        """
        command_class='FILTER'
        command_string="XQ#RMFESIN,<threadID>"
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        return self._do_motion_command(command_class, command_string)
    
    def insert_flsim(self, *args):
        """ Command the insertion of the FLS imager pickoff """
        command_class='FLSIM'
        command_string="XQ#INFLSIN,<threadID>"
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        return self._do_motion_command(command_class, command_string)
    
    def remove_flsim(self, *args):
        """ Command the retraction of the FLS imager pickoff """
        command_class='FLSIM'
        command_string="XQ#RMFLSIN,<threadID>"
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        return self._do_motion_command(command_class, command_string)
    
    def calibrate_lrel(self, *args):
        """ Force calibration of the Lores elevation axis """
        command_class='LREL'
        command_string="XQ#CALLRT,<threadID>"
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        m2fsConfig.setGalilLastPosition(self.SIDE, 'LREL', None)
        return self._do_motion_command(command_class, command_string)
        
    def calibrate_hrel(self, *args):
        """ Force calibration of the Hires elevation axis """
        command_class='HREL'
        command_string="XQ#CALHRTL,<threadID>"
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        m2fsConfig.setGalilLastPosition(self.SIDE, 'HREL', None)
        return self._do_motion_command(command_class, command_string)
    
    def calibrate_hraz(self, *args):
        """ Force calibration of the Hires azimuth axis """
        command_class='HRAZ'
        command_string="XQ#CALHRAZ,<threadID>"
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        m2fsConfig.setGalilLastPosition(self.SIDE, 'HRAZ', None)
        return self._do_motion_command(command_class, command_string)
    
    def calibrate_ges(self, *args):
        """ Force calibration of the disperser slide """
        command_class='GES'
        command_string="XQ#CALGES,<threadID>"
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        m2fsConfig.setGalilLastPosition(self.SIDE, 'GES', None)
        return self._do_motion_command(command_class, command_string)
    
    def nudge_ges(self, amount):
        """ Move the disperser slide by amount """
        try:
            int(amount)
        except ValueError:
            return '!ERROR: GES nudge amount must be specified as an integer.'
        command_class='GES'
        command_string="a[<threadID>]=%s;XQ#NUDGGES,<threadID>" % amount
        try:
            return self._getErrorMessage(command_class)
        except ValueError:
            pass
        m2fsConfig.setGalilLastPosition(self.SIDE, 'GES', None)
        return self._do_motion_command(command_class, command_string)
