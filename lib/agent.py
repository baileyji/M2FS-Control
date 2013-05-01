import time, argparse, signal, atexit, sys, select
import socket
import Queue
import logging, logging.handlers
from command import Command
from SelectedConnection import SelectedSocket, WriteError
import iorequest
import SelectedConnection
from m2fsConfig import m2fsConfig
import threading

SERVER_RETRY_TIME=10
DEFAULT_LOG_LEVEL=logging.DEBUG
SELECT_TIMEOUT=.25

MAX_ATTEMPTS=100

def escapeString(string):
    return string.replace('\n','\\n').replace('\r','\\r')

class Agent(object):
    """
    Base Class for (nearly) all M2FS control programs
    
    The base class provides the basic functionality for the program. 
    It configures logging.
    It handles incomming socket connections
    It does the basic grunt work of listening for incomming commands and calling
    the appropriate handler.
    It sends the command responses to the source of the command after the
        command has completed.
    It runs the main event loop which uses select to read and write on all agent
    conections, whether inbound or outbound.
    
    Agents have connections (SelectedConnections) to other entities. The 
    connections are mantained in the connections dictionary. Subclasses
    should create SelectedConnections in __init__ and add them to 
    connections. Keys are strings and may not begin with 'INCOMING', which is
    reserved for inbound connections.
    
    The inter-agent command protocol consists of \n terminated strings, the 
    first word (everything up to the first space) of which is the  command name.
    Sided commands (i.e. commands which act on the R or B side of the instrument
    have the additional constraint that the second word is either R or B. By
    convention polling commands typically have a ? as the second word (or third
    when R or B is present).
    
    The agent supports the default commands STATUS and VERSION. Subclasses add
    support for additional commands by adding a command & handler pair to the
    command_handlers dictionary (e.g. 
        self.command_handlers['NEW_COMMAND']=self.NEW_COMMAND_handler_func
    the command handler function must accept two arguments self & command. Ther
    latt of which will be a Command object.
    
    Handler functions which can execute fully in under about 1 second should do
    what they need to do and return. Any communication on any of the connections
    must be performed blocking if it must complete during the handler: data 
    sent via sendMessage will go out no sooner than the next iteration of the 
    main loop. Long running command handlers should start a worker thread with
    the function startWorkerThread after acknowledging the command by calling 
    setReply('OK').
    While the worker thread is active, new commands to the agent are serviced
    normally or, if they are blocked (whether by a call to block or as an 
    argument to startWorkerThread), with a try again later error. 
    
    Caution should be exerciese in handlers that run in the main thread if they 
    use a connection a worker thread also uses. Althrough the send and receive 
    calls are thread safe, the inability of the main thread handler to attain 
    the lock (due to a worker thread holding it) could casue an agent to 
    temporarily appear unresponsive. For an example see the shoeAgent SLITS and
    TEMP command handlers. Instead of blocking the temp command, the temp
    handler attempts to acquire the shoe connection lock and if it can't simply
    responds try again later.
    
    During thread execution 
    
    Worker threads must call returnFromWorkerThread immediately prior to 
    returning. 

    The worker thread should use the functions:
        set_command_state
        block
        unblock
        returnFromWorkerThread
    """ 
    def __init__(self, basename):
        """
        Initialize the agent
        
        Set max clients to 1 (Only receive commands from one connection).
        Create an instance cookie from the current time.
        Configure command line arguments (change defaults by overriding
        initialize_cli_parser() or add_additional_cli_arguments()
        Parse the command line arguments and place in self.args
        Register default command handlers for STATUS and VERSION
        Define the agent name, appending SIDE if an argument
        Initialize logging.
        Start listening for connections on user supplied port. If no port 
        supplied, get port for agent from m2fsconfig based on agent name.
        Register atexit function for cleanup.
        Register exit handler for SIGSTOP, SIGTERM, & SIGINT
        """
        self.connections={}
        self.commands=[]
        self.command_state={}
        self._blocked={}
        self.max_clients=1
        self.cookie=str(int(time.time()))
        self.initialize_cli_parser()
        self.args=self.cli_parser.parse_args()
        self.command_handlers={
            'STATUS':self.status_command_handler,
            'VERSION':self.version_request_command_handler}
        if 'SIDE' in self.args:
            self.name=basename+self.args.SIDE
        else:
            self.name=basename
        self.args.LOG_LEVEL=self.args.LOG_LEVEL.upper()
        if self.args.LOG_LEVEL == 'DEBUG':
            self.args.LOG_LEVEL=logging.DEBUG
        elif self.args.LOG_LEVEL == 'ERROR':
            self.args.LOG_LEVEL=logging.ERROR
        elif self.args.LOG_LEVEL == 'INFO':
            self.args.LOG_LEVEL=logging.INFO
        else:
            self.args.LOG_LEVEL=DEFAULT_LOG_LEVEL
        self.initialize_logger(self.args.LOG_LEVEL)
        if self.args.PORT:
            self.PORT=self.args.PORT
            self.initialize_socket_server(tries=5)
        else:
            port=m2fsConfig.getPort(self.name)
            if port:
                self.PORT=port
                self.initialize_socket_server(tries=5)
            else:
                self.PORT=None
                self.server_socket=None
        #register an exit function
        atexit.register(self.on_exit, self)
        #Register a terminate signal handler
        signal.signal(signal.SIGTERM, lambda signum, stack_frame: exit(0))
        signal.signal(signal.SIGINT, lambda signum, stack_frame: exit(0))
        self.logger.info("----%s Startup Complete @ %s-----" %
                         (self.name, self.cookie) )
    
    def initialize_logger(self, level):
        """
        Configure logging
        
        Set logging level to DEBUG, set message format, log to stdout
        Set self.logger to logger of self.name
        """
        #Configure the root logger
        self.logger=logging.getLogger()
        # create console handler
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(name)s:%(levelname)s: %(message)s'))
        ch.setLevel(level)
        # add handlers to logger
        self.logger.addHandler(ch)
        self.logger.setLevel(level) 
        #Get a logger for the agent
        self.logger=logging.getLogger(self.name)
    
    def initialize_cli_parser(self):
        """
        Configure the command line interface
        
        NB If an argument is stored to dest=SIDE it will be appended to the
        agent name by __init__.
        """
        #Create a command parser with the default agent commands
        helpdesc=self.get_cli_help_string()
        cli_parser = argparse.ArgumentParser(
                    description=helpdesc,
                    add_help=True)
        cli_parser.add_argument('--version',
                                action='version',
                                version=self.get_version_string())
        cli_parser.add_argument('-p','--port', dest='PORT',
                                action='store', required=False, type=int,
                                help='the port on which to listen')
        cli_parser.add_argument('--log', dest='LOG_LEVEL',
                                action='store', required=False, default='',
                                type=str,
                                help='log level: INFO, DEBUG, ERROR')
        self.cli_parser=cli_parser
        self.add_additional_cli_arguments()
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """ 
        return "Subclass should override to provide help"
    
    def add_additional_cli_arguments(self):
        """
        Additional CLI arguments may be added by implementing this function.
        
        Arguments should be added as:
        self.cli_parser.add_argument(See ArgumentParser.add_argument for syntax)
        """
        pass
    
    def initialize_socket_server(self, tries=0):
        """
        Start listening for socket connections
        
        Creat a non-blocking server socket on self.listenOn()
        In the even of a socket error sleep SERVER_RETRY_TIME and retry
         tries times. Tries should be less than any recursion limit.
        If unable to initialize the socket call handle_server_error
        """
        try:
            self.server_socket = socket.socket(socket.AF_INET,
                                               socket.SOCK_STREAM)
            self.server_socket.setblocking(0)
            self.server_socket.setsockopt(socket.SOL_SOCKET,
                                          socket.SO_REUSEADDR, 1)
            self.server_socket.bind(self.listenOn())
            self.server_socket.listen(1)
            self.logger.info("Waiting for connection on %s:%s..." %
                             self.listenOn())
        except socket.error, e:
            if tries > 0:
                self.logger.error(
                    'Server socket error %s, retrying %s more times.' %
                    (set(e),tries))
                time.sleep(SERVER_RETRY_TIME)
                self.initialize_socket_server(tries=tries-1)
            else:
                self.handle_server_error(error=str(e))
    
    def listenOn(self):
        """
        Return an address tuple on which the server shall listen. 
        
        Must return a tuple of form (address, port) address must be a string,
        port a number, self.PORT may be used for the default port.
        
        For most agents overriding this function is unnecessary.
        """
        return ('localhost', self.PORT)
    
    def socket_message_received_callback(self, source, message_str):
        """
        Create a Command from the message and execute the proper handler.
        
        This is intended to be the callback for any SelectedConnections created
        from incomming connections.
        
        A Command is created from the received string and source.
        If a command exists from the source log a warning and ignore the 
            command.
        Otherwise add the Command to the list of commands. Then get the command
            handler from command_handlers using the first word in the message
            as a key after converting it to uppercase. Finally, call the command
            handler with the Command.
        """
        #create a command object
        command=Command(source, message_str)
        #Verify there are no existing commands from this source, if so fail and
        # return
        existing_from_source=filter(lambda x: x.source==source, self.commands)
        if existing_from_source:
            warning="Command '%s' received before command '%s' finished. Ignoring"
            warning=escapeString(warning % (message_str, existing_from_source[0]))
            self.logger.warning(warning)
            return
        self.logger.info('Received command %s' % escapeString(command.string))
        self.commands.append(command)
        #Check to see if command is blocked by a worker thread
        blockReason=self.getBlockReason(command)
        if blockReason != None:
            response='ERROR: Command is blocked.'
            if blockReason !='':
                response+=' '+blockReason
            self.logger.debug(response)
            command.setReply(response)
            return
        #Try to get the state of the command
        # If the command is not a query and is already running, it would have
        # been blocked. If the command doesn't have a worker thread we will get
        # the exception.
        try:
            workerState=self._getWorkerThreadState(command)
            self.logger.debug("Worker thread running: %s " % workerState)
            command.setReply(workerState)
            return
        except KeyError:
            pass
        #Execute the command's handler
        command_name=self.getCommandName(command)
        handler=self.command_handlers.get(command_name, self.bad_command_handler)
        handler(command)
    
    def get_version_string(self):
        """ Return a string with the version. Subclasses should override. """
        return 'AGENT Base Class Version 0.1'
    
    def _stowShutdown(self):
        """
        Stowed shutdown hook, called prior to shutting down agent
        
        Only called if a stowed shutdown is required.
        """
        pass
    
    def _exitHook(self):
        """Called on agent exit, hook for subclass """
        pass
    
    def on_exit(self, arg):
        """
        Prepare to exit
        
        call the stowed shutdown hook if necessary 
        Log exit
        shutdown server socket
        close all open connections
        wait 1 second to ensure all messages make it into the system log
        """
        self._exitHook()
        if m2fsConfig.doStowedShutdown():
            self._stowShutdown()
        self.logger.info("----%s exiting: %s-----" % (self.name, str(arg)))
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_WR)
            except socket.error:
                pass
            self.server_socket.close()
        for c in self.connections.values():
            c.close()
        time.sleep(1)
    
    def handle_connect(self):
        """
        Callback for when select indicates read on a server socket connection.
        
        Accept connection. 
        Close if already have self.max_clients connections
        Else,
        Create a SelectedSocket from the socket with
            self.socket_message_received_callback as the 
            default_message_received_callback.
        log connection
        Add it to self.connections
        """
        #Accept the connection
        connection, addr = self.server_socket.accept()
        #Count the number of existing inbound connections
        str_keys=filter(lambda x: type(x)==str, self.connections.keys())
        n_in=len(filter(lambda x: x.startswith('INCOMING'), str_keys))
        #Close the connection and return if we've got too many
        if n_in >= self.max_clients:
            connection.close()
            self.logger.info('Rejecting connection from %s:%s, have %s already.'
                              % (addr[0], addr[1], self.max_clients))
            return
        #Configure the connection and add it to connections
        connection.setblocking(0)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        soc = SelectedSocket(addr[0],addr[1], Live_Socket_To_Use=connection,
            default_message_received_callback=self.socket_message_received_callback)
        self.logger.info('Connected with %s:%s' % (addr[0], addr[1]))
        self.connections['INCOMING%i' % n_in]=soc
    
    def handle_server_error(self, error=''):
        """
        Callback for when select indicates error on a server socket.

        log error
        exit
        """
        self.logger.error('Socket server error: "%s"' % error)
        sys.exit(1)
    
    def update_select_maps(self, read_map, write_map, error_map):
        """
        Update dictionaries for select call. 
        
        always select on server reads (incomming connection) or errors (fatal)
            with self.handle_connect and self.handle_server_error as the 
            handlers
        select on each of the connections for read, write, and error if the
            connection reports it needs selecting on
        Use the read, write, & error handlers defined by SelectedConnection
        
        In case it isn't clear: The select maps are key value pairs of 
            selectable_object:handler_for_when_select_indicates_object_is_ready
            
        Function aquires locks for all the items in the select map, if it
        is unable to do so, it will not add an item to the map. They must all be
        released after the select call. A list of aquired locks is returned
        """
        # check the server socket
        read_map[self.server_socket] = self.handle_connect
        error_map[self.server_socket] = self.handle_server_error
        #check all other connections
        locks=[]
        for selectedconn in self.connections.values():
            if selectedconn.rlock.acquire(False):
                releaseLock=True
                if selectedconn.do_select_read():
                    read_map[selectedconn] = selectedconn.handle_read
                    releaseLock=False
                if selectedconn.do_select_write():
                    write_map[selectedconn] = selectedconn.handle_write
                    releaseLock=False
                if selectedconn.do_select_error():
                    error_map[selectedconn] = selectedconn.handle_error
                    releaseLock=False
                if releaseLock:
                    selectedconn.rlock.release()
                else:
                    locks.append(selectedconn.rlock)
        return locks

    def cull_dead_sockets_and_their_commands(self):
        """
        Remove dead sockets from connections & purge their commands.
        
        Find all closed socket connections (commands come from connections with
        keys starting with INCOMING.
        Remove the socket from connections
        Find any commands that came from the socket and remove them
        """
        incomingKeys=filter(lambda x: x.startswith('INCOMING'),
                            self.connections.keys())
        deadKeys=filter(lambda x: not self.connections[x].isOpen(), incomingKeys)
        for deadKey in deadKeys:
            deadSocket=self.connections.pop(deadKey)
            self.logger.debug("Cull dead socket: %s" % deadSocket)
            dead_commands=filter(lambda x:x.source==deadSocket, self.commands)
            for dead_command in dead_commands:
                self.commands.remove(dead_command)
    
    def handle_completed_commands(self):
        """
        Return results of complete commands and cull the commands.
        
        Find all commands that are 'complete'.
        For each command, send the reply to the source
        Remove the command
        """
        completed_commands=filter(lambda x: x.state=='complete',self.commands)
        for command in completed_commands:
            self.logger.info("Closing out command %s" % command)
            try:
                if command.reply=='':
                    #Force sending of the empty response
                    command.source.sendMessage('\n')
                else:
                    command.source.sendMessage(command.reply)
                self.commands.remove(command)
            except WriteError:
                pass
    
    def not_implemented_command_handler(self, command):
        """
        Placeholder command handler 
        
        Agents may use this command handler as a placeholder.
        """
        command.setReply('ERROR: Command not implemented.')
    
    def bad_command_handler(self, command):
        """
        Handle an unrecognized command 
        
        Agents may use this command handler if a command is found to be invalid.
        """
        command.setReply('!ERROR: Unrecognized command.')
    
    def version_request_command_handler(self,command):
        """ Handle a version request """ 
        command.setReply(self.get_version_string())
    
    def status_command_handler(self,command):
        """
        Handle a status request
        
        Calls the get_status_list method to retrieve a list of key value tuples,
        which are then formatted into a response per the agreed upon protocol.
        
        Staus responses shall be in the form of key:value pairs, with the
        first pair the name of the agent with version and the value the agent's
        cookie. Keys and values must use _ in lieu of spaces. Pairs are to be 
        seperated by spaces. Any \r or \n in the response should be escaped, 
        except for when joining status responses of child agents, in which case
        they are to be seperated by a \r.
        """
        list=self.get_status_list()
        reply=''
        for i in list:
            try:
                if type(i)==str:
                    reply+='\r'+i
                else:
                    item="%s:%s" % (i[0].replace(':','_'), i[1].replace(':','_'))
                    item=item.encode('string_escape') #escape non-printable
                    reply+=item.replace(' ','_')+' '
            except Exception, e:
                self.logger.warning(
                'Caught exception while processing status key,'+
                ' check get_status_list for bugs')
        command.setReply(reply+'\n') # incase reply is empty, shouldn't be

    def get_status_list(self):
        """
        Return a list of tuples & strings to be formatted into a status reply
        
        Subclasses may implement this function to avoid worrying about status 
        command reply syntax. It is called automatically by the agent base class
        to get the contents of the status reply.
        
        The tuples in the list should consist of strings and two element tuples
        of strings only, with strings listed after the tuples. The first tuple
        should be a two element tuple with the agent name and cookie. Subsequent
        tuples should be two element key value pairs reporting the status of the
        agent. The keys and values will be coerced into obeying the status
        syntax: spaces and colons will be replaced by underscores and \r & \n 
        will be escaped. Non printable characters will be replaced with escaped
        hexadecimal.
        
        Finally single element strings are to contain the properly formatted 
        status replies from any child agents. Provided they were obtained 
        via the STATUS command to the child agent, they will a meet all
        requirements.
        """
        return [(self.get_version_string(), self.cookie)]
    
    def do_select(self):
        """
        Select on all connections which require it.
        
        First call update_select_maps to get object:handler pairs on which to
            select for reading, writing, & errors.
        Perform the select call
        Call the appropriate handlers for each of the objects returned by select 
        """
        read_map, write_map, error_map = {}, {}, {}

        #We can select on connections, but we should make sure that we lock all
        # the connections we are going to use. To keep the main loop moving we
        # don't want to block on any that are locked, rather we just don't
        # select on them
        locks=self.update_select_maps(read_map, write_map, error_map)
        try:
            readers, writers, errors = select.select(
                read_map.keys(), write_map.keys(),
                error_map.keys(), SELECT_TIMEOUT)
        except select.error, err:
            if err[0] != EINTR:
                for lock in locks:
                    lock.release()
                raise
        #select_end = time.time()
        #self.logger.debug("select used %.3f s" % (select_end-select_start))
        for reader in readers: read_map[reader]()
        for writer in writers: write_map[writer]()
        for error  in errors:  error_map[error]()
        for lock in locks:
            lock.release()
        #self.logger.debug("select operation used %.3f s" % (time.time() - select_end))
    
    def run(self):
        """
        Called once per main loop, after select & any handlers but
            before closing out commands.
        Implement in subclass
        """
        pass
    
    def runOnce(self):
        """
        Main for standalone, no-server-socket operation.
        
        Not used at present. Override in subclass
        """
        self.logger.critical('Command line commands not yet implemented.')
        sys.exit(0)
    
    def runSetup(self):
        """
        Called once before entering main loop.
        Implement in subclass
        """
        pass
    
    def getConnectionByName(self, name):
        """ Return the SelectedConnection named name or rase KeyError """
        return self.connections[name]
    
    def getCommandName(self, command):
        """ Return the command_name for the command object
        
        This is the string which maps to the commands callback in 
        command_handlers
        """
        return command.string.partition(' ')[0]
    
    def commandIsQuery(self, command):
        """ Return true if the command is a query 
        
        Subclasses may need to override this.
        """
        try:
            return command.string.split(' ')[1]=='?'
        except IndexError:
            return False
    
    def block(self, command_or_name, reason='', blockingID=None):
        """
        Cause command to be blocked by the current thread. Queries never block.
        
        If command_or_name is a name (a string) it must correspond to of the
        keys of command_handlers else a KeyError is raised.
        
        Reason may be set to a reason for the block
        
        If set, blockingID should be the thread identifier that is the source of
        the block. If not set the current thread's identifier is used.
        
        _blocked is a dictionary, keys are the commands that are currently 
        blocked. values ate 2-tuples consisting of blocking thread id and the 
        reason for the block.
        """
        #Get the thread id that is responsible for the block
        if not blockingID:
            blockingID=threading.current_thread().ident
        #Log some info
        self.logger.debug("Block %s, id= %i" % (command_or_name, blockingID))
        self.logger.debug("Befor block: "+str(self._blocked))
        #Extract the command name to be blocked
        if type(command_or_name) == str:
            self.command_handlers[command_or_name]
            blocked_command_name=command_or_name
        else:
            blocked_command_name=self.getCommandName(command_or_name)
        #Grab the list of blocks for the command
        blocks=self._blocked.get(blocked_command_name,[])
        #Add the new block to the list
        blocks.append((blockingID, reason))
        self._blocked[blocked_command_name]=blocks
        self.logger.debug("blocks added: "+str(blocks))
        self.logger.debug("After block: "+str(self._blocked))
    
    def unblock(self, command_or_name, blockingID=None):
        """ Unblock command.
        
        If set, blockingID should be the thread identifier that is the source of
        the block. If not set the current thread's identifier is used.

        If command_or_name is a name (a string) it
        must correspond to of the keys of command_handlers else a KeyError is
        raised.
        """
        if not blockingID:
            blockingID=threading.current_thread().ident
        self.logger.debug("Unblock %s, id= %i" % (command_or_name,blockingID))
        self.logger.debug("Befor unblock: "+str(self._blocked))
        if type(command_or_name) == str:
            self.command_handlers[command_or_name]
            blocked_command_name=command_or_name
        else:
            blocked_command_name=self.getCommandName(command_or_name)
        #Get the list of blocks
        blocks=self._blocked.get(command_name, [])
        #Find all the blocks for the current thread (there should only be one)
        blocksToClear=[i for i,x in enumerate(blocks) if x[0]==blockingID]
        #Remove them
        for i in blocksToClear:
             blocks.pop(i)
        self.logger.debug("After unblock: "+str(self._blocked))
             
    def removeBlocksOfThread(self, threadID=None):
        if not threadID:
            threadID=threading.current_thread().ident
        for blockSet in self._blocked.values():
            blocksToClear=[i for i,x in enumerate(blockSet) if x[0]==threadID]
            #Remove them
            for i in blocksToClear:
                blockSet.pop(i)
        
    def getBlockReason(self, command):
        """ Report the blocking reason if command is blocked, None if not.
        
        Query commands never block.
        
        Return a string specifying the blocking reason. A null string means no
        reason was specified in the call to block.
        Returns None if command is not blocked.
        """
        if self.commandIsQuery(command):
            return None
        self.logger.debug("Current blocks: "+str(self._blocked))
        blocks=self._blocked.get(self.getCommandName(command),[])
        if len(blocks) != 0:
            #Return the reason for the first block
            return blocks[0][1]
        return None
    
    def set_command_state(self, command_name, state):
        """ Set the thread state for command_name.
        
        command_name must match the string for the callback that started the 
        worker thread.
        
        While the state is set, sending the agent the named command will return
        the specified state. The command's callback will NOT be called.
        """
        self.command_state[command_name]=state
    
    def clear_command_state(self, command_name):
        """ Clear the thread state for command_name 

        command_name must match the string for the callback that started the
        worker thread.
        """
        self.command_state.pop(command_name, None)
    
    def _getWorkerThreadState(self, command):
        """ Return the set statue of the command
        
        This function takes a command object and extracts the command name to
        retrieve to command state for the command name. If no command state
        exists it raises KeyError
        """
        ret=self.command_state[self.getCommandName(command)]
        if not self._isWorkerThreadRunning(command):
            self.clear_command_state(self.getCommandName(command))
        return ret

    def _isWorkerThreadRunning(self, command):
        """ Return true if a worker thread is running for command """
        command_name=self.getCommandName(command)
        return next((True for thread in threading.enumerate() if thread.name==command_name), False)

    def startWorkerThread(self, command, initialState, func,
                          args=(), kwargs={}, block=()):
        command_name=self.getCommandName(command)
        #Set the initial state of the command
        self.set_command_state(command_name, initialState)
        #Start the worker thread
        worker=threading.Thread(target=func,name=command_name, args=args,kwargs=kwargs)
        worker.daemon=True
        worker.start()
        #Tie all the requested blocks to the worker thread
        self.block(command_name, blockingID=worker.ident)
        for blockable in block:
            self.block(blockable,blockingID=worker.ident)

    def returnFromWorkerThread(self, command_name, finalState=''):
        if finalState:
            self.set_command_state(command_name, finalState)
        else:
            self.clear_command_state(command_name)
        self.removeBlocksOfThread()
    
    def main(self):
        """
        Main loop (or one shot if no port). Act on commands as received.
        
        The general (only at time of writing) case assumes operation with a
        port. The typical flow is as follows:
        
        Agent has been initialized and SelectedConnections to all other devices
        and agents required have been created and are self.connections.
        Main calls runSetup to allow subclasses to perform any additional setup
        and then enters the main loop.
        
        In the main loop:
        
        Then do_select is run, which checks each connection to see
        if it needs reading, writing, or checking for errors. It then selects
        on those connections, finally executing the read, write, or error 
        callbacks for each connected as indicated. For details of what these
        handlers do, see SelectedConnection. In essence they grab received data
        into an internal buffer until some criterion is met; transmit any
        pending data, & deal with an error, respectively.
        Next, any dead socket conectionions are dropped along with all commands
        received from those connections. Note that commands can only arrive from
        a connections with a key that starts with INCOMING. Also note that
        the dropped commands(') callback(s) will already have been executed.
        Finally, the loop closes out any completed commands. Essentially this
        means taking the command response and sending it to the source. Note 
        the data isn't actually sent until the next do_select call, at the
        earliest
        """
        self.runSetup()
        if self.PORT is None:
            self.runOnce()
        while True:
            self.do_select()
            
            self.run()
            
            #log commands
            for command in self.commands:
                self.logger.debug(command)
            
            self.cull_dead_sockets_and_their_commands()
            self.handle_completed_commands()
        
