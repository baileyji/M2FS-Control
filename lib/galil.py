import serial, termios
import SelectedConnection
from m2fsConfig import m2fsConfig

EXPECTED_M2FS_DMC_VERSION='0.1000'

class GalilThreadUpdateException(IOError):
    """ Unable to update list of threads executing on the Galil """
    pass

class GalilCommandNotAcknowledgedError(IOError):
    """ Gaili fails to acknowledge a command, e.g. didn't respond with ':' """
    pass

class GalilSerial(SelectedConnection.SelectedSerial):
    """ 
    Galil DMC-4183 Controller Class
    
    This class extents the SelectedSerial implementation of SelectedConnection
    with routines needed to control the Galil. It grew out of a potentially
    misguided desire to abstract some stuff ouut of the galil agent.
    As is all sends and receives are performed using blocking sends and receives
    so it never really makes use of the whole Selected bit. It does get used as
    it allows trapping of unsolicited messages from the galil, which would
    otherwise clog things up. 
    
    The controller uses the concept of command classes to keep track of which
    commands block other commands. E.g. if a command in class GES is executing 
    changing a parameter with the same class would be blocked. The classes are
    FOCUS, FILTER, FLSIM, LREL, HREL, HRAZ, GES, & SHUTDOWN.
    
    General flow is:
        initialize attributes
        initialize the SelectedSerial superclass
            _postconnect hook is used to verify galil is running and has proper
            version software
        initialize the galil with all the user parameters stored in the 
            appropriate m2fs_galil (R|B) conf file.
        get a command
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
    def __init__(self, *args, **kwargs):
        """
        Initialize the Galil object
        
        Requires keyword argument SIDE to indicate which M2FS galil we are working
        with ('R' or 'B') 
        Additional rguments are as defined in SelectedSerial
        """
        self.SIDE=kwargs.pop('SIDE')
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
        self.thread_command_map={
            '0':'AUTO','1':'ANAMAF','2':'MOMONI','3':None,
            '4':None,'5':None,'6':None,'7':None}
        #Perform superclass initialization, note we implement the _postConnect
        # hook for the galil, see below
        SelectedConnection.SelectedSerial.__init__(self,*args,**kwargs)
        #TODO what is this for again
        self.config={}
        #If we've sucessfully connected, go ahead and initialize the galil
        # see the command for what this means
        if self.isOpen():
            self._initialize_galil()
    
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
                self._send_command_to_gail('XQ#AUTO,0')
                self.logger.warning("Executing #AUTO manually")
                self._update_executing_threads_and_commands()
            except GalilCommandNotAcknowledgedError:
                error_message="Galil not programed"
                raise SelectedConnection.ConnectError(error_message)
        #Get the software version
        response=self._send_command_to_gail('MG m2fsver')
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
        bootup1=self._send_command_to_gail('MG bootup1')
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
                    config[settingName]=self._send_command_to_gail('MG '+variableName)
                m2fsConfig.setGalilDefaults(self.SIDE, config)
                self.config=config
                self._send_command_to_gail('bootup1=0')
                config={}
                self.logger.warning('Galil'+self.SIDE+' configFile rebuilt.')
                return
            except IOError,e:
                raise IOError("Failure during rebuild of defaults file.")
        #Send the config to the galil
        if config:
            try:
                #NB we are only here if bootup1=1, which implies nothing but the
                # basic threads are running and thus we are guaranteed the
                # settings are not blocked by some executing thread
                for settingName, value in config.items():
                    variableName=self.settingName_to_variableName_map[settingName]
                    self._send_command_to_gail('%s=%s' % (variableName, value))
                self.config=config
                self._send_command_to_gail('bootup1=0')
            except IOError, e:
                raise IOError("Can not set galil defaults.") 
    
    def _send_command_to_gail(self, command_string):
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
                "Galil did not acknowledge command '%s' (%s)" %
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
        response=self._send_command_to_gail(
            'MG "HX=",_HX0,_HX1,_HX2,_HX3,_HX4,_HX5,_HX6,_HX7')
        if response[-1] == '?' or response[0:3] !='HX=':
            raise GalilThreadUpdateException("Could not update galil threads.")
        #Extract the part we care about
        response=response[4:response.find('\r')]
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
                    self.thread_command_map["%i"%thread_number]=(
                        'FOCUS FILTER FLSIM LREL HREL HRAZ GES')
    
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
            
    def _add_galil_command_to_executing_commands(self, command, thread):
        """
        Mark command as executing on thread.
        
        Honestly, a function for this!
        """
        self.thread_command_map[thread]=command
    
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
            if False and self.check_elo_switch():
                return "ERROR: ELO switch engaged."
            #Get a thread for the command
            thread_number=self._get_motion_thread()
            if thread_number is None:
                return "ERROR: All available galil threads in use. Try again later"
        except IOError, e:
            return "ERROR: "+str(e)
        try:
            #Send the command to the galil
            self._send_command_to_gail(
                command_string.replace('<threadID>', thread_number))
            return 'OK'
        except IOError, e:
            return "ERROR: "+str(e)
        finally:
            # assume that the command is blocked anyway
            self._add_galil_command_to_executing_commands(command_class, thread_number)
    
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
            self._send_command_to_gail(command_string)
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
        
        Look through thread_command_map and find all threads running the
        command class cclass or 'SHUTDOWN' (which blocks everything).
        If any threads were found return true. 
        """
        blockingThreads=filter(lambda x: x[1] and
                               (cclass in x[1] or 'SHUTDOWN' in x[1]),
            self.thread_command_map.items())
        return blockingThreads!=[]
    
    def check_abort_switch(self):
        """ 
        Return True if abort switch engaged
        
        This doesn't work reliably due to poorly defined issues with the 
        underlying hardware.
        """
        try:
            val=int(float(self._send_command_to_gail('MG _AB')))
        except ValueError,e:
                raise IOError(str(e))
        return val != 1
    
    def check_elo_switch(self):
        """
        Return True if elo switch engaged
        
        This doesn't work reliably due to poorly defined issues with the
        underlying hardware. TODO need to verify this routine won't cause a
        fault while a command is running (because of MO*).
        """
        try:
            val=int(float(self._send_command_to_gail('MG _TA3')))
            #Galil doesn't reset the ELO status automatically, need to do
            #MO*;SHA;MOA;MG _TA3 to confirm the reading
            # This means that we may also return false negatives, but there is
            # no good way to check you need to turn an axis on to make the bit
            # update and that carries all the extra logic required to pick which
            # axis you want to toggle 
            if val != 0:
                self.sendMessageBlocking('MO*;SHA;MOA;MG _TA3', connect=False)
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
    
    def reset(self):
        """ Reset the galil
        
        Directly use the underlying serial functions. self.connect may fail if
        the galil has entered some weird state. 
        """
        try:
            self.connection.open()
            self.connection.write('RS\r')
            self.connection.flush()
            self.connection.close()
            self.connect()
            return 'OK'
        except (IOError, serial.SerialException), e:
            return str(e)
    
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
            self._send_command_to_gail('HX3;XQ#SHTDWN,3')
            return 'OK'
        except IOError, e:
            return str(e)
        finally:
            self._add_galil_command_to_executing_commands('SHUTDOWN', 3)

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
            self._send_command_to_gail('MG '+variableName)
            val=self.receiveMessageBlocking(nBytes=20)
            if val=='':
                val="ERROR: Galil failed to return value"
            return val
        except IOError, e:
            return str(e)
    
    def setDefault(self, settingName, value):
        """
        Set a new value for galil setting
        
        make sure we are connected and update the currently executing threads
        ensure the setting is a real setting
        ensure the setting isn't blocked by an executing thread
            return error message if so
        Set the new value on the galil, in the config dict, and with m2fsConfig
        No provision is made to ensure the value is suitable
        return 'OK'
        """
        try:
            variableName=self.settingName_to_variableName_map[settingName]
        except KeyError:
            return "!ERROR: %s not a valid setting" % settingName
        try:
            self.connect()
            self._update_executing_threads_and_commands()
            #Check to see if the command is blocked
            if self._command_class_blocked(settingNameCommandClasses[settingName]):
                return "ERROR: Command is blocked. Try again later."
            self._send_command_to_gail('%=%s' % (variableName, value))
            self.config[settingName]=value
            m2fsConfig.setGalilDefaults(self.SIDE, config)
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
            response=response.replace('\r','\\r').replace('\n','\\n')
            #Update galil thread statuses
            self._update_executing_threads_and_commands()
            return response
        except IOError, e:
            self.logger.error(str(e))
            return "ERROR: "+str(e)

    #The remaining commands are wrappers for each of the galil tasks
    #They generate a basic command string to be sent to the galil
    # for the motion command, the thread ID is determined later and a
    # placeholder is used, which is filled in when _do_motion_command determines
    # which thread is to be used.
    # Note that the setting routines may start a move which takes 10s of seconds
    # to complete. The 'OK' returned only indicates that the move has begun

    def get_filter(self):
        """ Return the current filter position """
        command_string="XQ#%s,%s" % ('GETFILT', '7')
        return self._do_status_query(command_string)
    
    def get_loel(self):
        """ Return the Lores Elevation """
        command_string="XQ#%s,%s" % ('GETLRTL', '7')
        return self._do_status_query(command_string)
        
    def get_hrel(self):
        """ Return the Hires Elevation """
        command_string="XQ#%s,%s" % ('GETHRTL', '7')
        return self._do_status_query(command_string)
    
    def get_hraz(self):
        """ Return the Hires azimuth """
        command_string="XQ#%s,%s" % ('GETHRAZ', '7')
        return self._do_status_query(command_string)
    
    def get_foc(self):
        """ Return the focus position """
        command_string="XQ#%s,%s" % ('GETFOC', '7')
        return self._do_status_query(command_string)
    
    def get_ges(self):
        """ Return the disperser slide status """
        command_string="XQ#%s,%s" % ('GETGES2', '7')
        return self._do_status_query(command_string)
        
    def get_flsim(self):
        """ Return the FLS imager pickoff position """
        command_string="XQ#%s,%s" % ('GETFLSI', '7')
        return self._do_status_query(command_string)
        
    def set_filter(self, filter):
        """ Select a filter position """
        if filter not in ['1','2','3','4','5','6','7','8','9','10']:
            return '!ERROR: Valid fliter choices are 1-10. 9=None 10=load.'
        command_class='FILTER'
        command_string="a[<threadID>]=%s;XQ#PICKFIL,<threadID>" % filter
        return self._do_motion_command(command_class, command_string)
    
    def set_loel(self, position):
        """ Set the Lores elevation """
        try:
            int(position)
        except ValueError:
            return '!ERROR: Lores elevation must be specified as an integer.'
        command_class='LREL'
        command_string="a[<threadID>]=%s;XQ#SETLRTL,<threadID>" % position
        return self._do_motion_command(command_class, command_string)
        
    def set_hrel(self, position):
        """ Set the Hires elevation """
        try:
            int(position)
        except ValueError:
            return '!ERROR: Hires elevation must be specified as an integer.'
        command_class='HREL'
        command_string="a[<threadID>]=%s;XQ#SETHRTL,<threadID>" % position
        return self._do_motion_command(command_class, command_string)
    
    def set_hraz(self, position):
        """ Set the Hires azimuth """
        try:
            int(position)
        except ValueError:
            return '!ERROR: Hires azimuth must be specified as an integer.'
        command_class='HRAZ'
        command_string="a[<threadID>]=%s;XQ#SETHRAZ,<threadID>" % position
        return self._do_motion_command(command_class, command_string)
    
    def set_foc(self, position):
        """ Set the focus value """
        try:
            float(position)
        except ValueError:
            return '!ERROR: Focus must be specified as a number.'
        command_class='FOCUS'
        command_string="a[<threadID>]=%s;XQ#SETFOC,<threadID>" % position
        return self._do_motion_command(command_class, command_string)
    
    def set_ges(self, position):
        """Position should be either HIRES, LORES, or LRSWAP"""
        if position not in ['HIRES','LORES','LRSWAP']:
            return '!ERROR: %s is not one of HIRES, LORES, or LRSWAP' % position
        if 'LRSWAP' in position:
            command_class='GES LREL'
        else:
            command_class='GES'
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
        return self._do_motion_command(command_class, command_string)
    
    def remove_filter(self, *args):
        """
        Command the removal of the current filter
        
        Note that FILTER automatically inserts and removes as needed. This is a
        debugging convenience routine.
        """
        command_class='FILTER'
        command_string="XQ#RMFESIN,<threadID>"
        return self._do_motion_command(command_class, command_string)
    
    def insert_flsim(self, *args):
        """ Command the insertion of the FLS imager pickoff """
        command_class='FLSIM'
        command_string="XQ#INFLSIN,<threadID>"
        return self._do_motion_command(command_class, command_string)
    
    def remove_flsim(self, *args):
        """ Command the retraction of the FLS imager pickoff """
        command_class='FLSIM'
        command_string="XQ#RMFLSIN,<threadID>"
        return self._do_motion_command(command_class, command_string)
    
    def calibrate_lrel(self, *args):
        """ Force calibration of the Lores elevation axis """
        command_class='LREL'
        command_string="XQ#CALLRT,<threadID>"
        return self._do_motion_command(command_class, command_string)
        
    def calibrate_hrel(self, *args):
        """ Force calibration of the Hires elevation axis """
        command_class='HREL'
        command_string="XQ#CALHRTL,<threadID>"
        return self._do_motion_command(command_class, command_string)
    
    def calibrate_hraz(self, *args):
        """ Force calibration of the Hires azimuth axis """
        command_class='HRAZ'
        command_string="XQ#CALHRAZ,<threadID>"
        return self._do_motion_command(command_class, command_string)
    
    def calibrate_ges(self, *args):
        """ Force calibration of the disperser slide """
        command_class='GES'
        command_string="XQ#CALGES,<threadID>"
        return self._do_motion_command(command_class, command_string)
    
    def nudge_ges(self, amount):
        """ Move the disperser slide by amount """
        try:
            int(amount)
        except ValueError:
            return '!ERROR: GES nudge amount must be specified as an integer.'
        command_class='GES'
        command_string="a[<threadID>]=%s;XQ#NUDGGES,<threadID>" % amount
        return self._do_motion_command(command_class, command_string)
