import time, argparse, signal, atexit, sys, select
import socket
import logging, logging.handlers
from command import Command
from SelectedConnection import SelectedSocket
from m2fsConfig import m2fsConfig

SERVER_RETRY_TIME=10
class Agent(object):
    """
    Base Class for (nearly) all M2FS control programs
    
    The base class provides the basic functionality for the program. 
    It configures logging.
    It handles incomming socket connections
    It does the basic grunt work of listening for incomming commands and calling
    the appropriate handler.
    It sends the command responses to the source of the sommand after the
        command has completed.
    It runs the main event loop which uses select to read and write on all agent conections, whether inbound or outbound.
    
    It is my intention to make either the individual connections or the commands
        themselves into their own threads, thereby removing the necessity of the
        select call in the event loop and allowing non-blocking sends/receives
        within command handlers. I've not come up with a good implementation 
        yet.
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
        self.sockets=[]
        self.devices=[]
        self.commands=[]
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
        self.initialize_logger()
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
    
    def initialize_logger(self):
        """
        Configure logging
        
        Set logging level to DEBUG, set message format, log to stdout
        Set self.logger to logger of self.name
        """
        #Configure the root logger
        self.logger=logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        # create formatter
        formatter = logging.Formatter('%(name)s:%(levelname)s: %(message)s')
        # create console handler and set level to debug
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # add formatter to handlers
        ch.setFormatter(formatter)
        # add handlers to logger
        self.logger.addHandler(ch)
        #Get a logger for the agent
        self.logger=logging.getLogger(self.name)
    
    def initialize_cli_parser(self):
        """Configure the command line interface
        
        NB If an argument is stored to dest=SIDE it will be appended to the
        agent name by __init__.
        """
        #Create a command parser with the default agent commands
        helpdesc="This is the instrument interface"
        cli_parser = argparse.ArgumentParser(
                    description=helpdesc,
                    add_help=True)
        cli_parser.add_argument('--version',
                                action='version',
                                version=self.get_version_string())
        cli_parser.add_argument('-p','--port', dest='PORT',
                                action='store', required=False, type=int,
                                help='the port on which to listen')
        self.cli_parser=cli_parser
        self.add_additional_cli_arguments()
    
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
            self.logger.info(" Waiting for connection on %s:%s..." %
                             self.listenOn())
        except socket.error, e:
            if tries > 0:
                self.logger.info('Server socket error %s, retrying %s more times.'%(set(e),tries))
                time.sleep(SERVER_RETRY_TIME)
                self.initialize_socket_server(tries=tries-1)
            else:
                self.handle_server_error(error=msg)
    
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
            
        A major limitation of the current design is that this function will not
            return until the handler does, which means that any sequenced
            actions that are IO dependant must use blocking IO. This effectively
            prevents closing out the command and transmitting the response
            unless the handler spawns a thread (I've not done this anywhere)
            uses a nasty system of nested callbacks or some other hack.
        """
        command_name=message_str.partition(' ')[0]
        command=Command(source, message_str)
        existing_commands_from_source=filter(lambda x: x.source==source, self.commands)
        if existing_commands_from_source:
            warning=('Command "%s" received before command "%s" finished.' %
                     (message_str, existing_commands_from_source[0])
            ).replace('\n','\\n').replace('\r','\\r')
            self.logger.warning(warning)
        else:
            self.commands.append(command)
            self.command_handlers.get(command_name.upper(), self.bad_command_handler)(command)
    
    def get_version_string(self):
        """ Return a string with the version. Subclasses should override. """
        return 'AGENT Base Class Version 0.1'
    
    def on_exit(self, arg):
        """
        Prepare to exit
        
        Log exit
        shutdown server socket
        close all open connections
        wait 1 second to ensure all messages make it into the system log
        """
        self.logger.info("exiting %s" % arg)
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_WR)
            except socket.error:
                pass
            self.server_socket.close()
        for d in self.devices:
            d.close()
        for s in self.sockets:
            s.close()
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
        Add it to self.sockets
        """
        # accept a connection in any case, close connection
        # below if already busy
        connection, addr = self.server_socket.accept()
        if len(self.sockets) < self.max_clients:
            connection.setblocking(0)
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            soc = SelectedSocket(addr[0],addr[1],
                Live_Socket_To_Use=connection,
                default_message_received_callback=self.socket_message_received_callback)
            self.logger.info('Connected with %s:%s' % (addr[0], addr[1]))
            self.sockets.append(soc)
        else:
            connection.close()
            self.logger.info(
                'Rejecting connect from %s:%s' % (addr[0], addr[1]))
    
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
        select on each of the sockets & devices (they all implement 
            SelectedConnection) for read, write, and error if the connection
            reports it needs selecting on
        Use the read, write, & error handlers defined by SelectedConnection
        
        In case it isn't clear the select maps are key value pairs of 
            selectable_object:handler_for_when_select_indicates_object_is_ready
        """
        # check the server socket
        read_map[self.server_socket] = self.handle_connect
        error_map[self.server_socket] = self.handle_server_error
        #check all other connections
        for selectedconn in self.sockets + self.devices:
            if selectedconn.do_select_read():
                read_map[selectedconn] = selectedconn.handle_read
            if selectedconn.do_select_write():
                write_map[selectedconn] = selectedconn.handle_write
            if selectedconn.do_select_error():
                error_map[selectedconn] = selectedconn.handle_error
    
    def cull_dead_sockets_and_their_commands(self):
        """
        Remove dead sockets from list of sockets & purge commands from same.
        
        Find all closed socket connections (commands can't come from
            devices, so no need to check)
        Remove the socket from sockets
        Find any commands that came from the socket and remove them
        """
        dead_sockets=filter(lambda x: not x.isOpen(), self.sockets)
        for dead_socket in dead_sockets:
            self.logger.debug("Cull dead socket: %s" % dead_socket)
            self.sockets.remove(dead_socket)
            dead_commands=filter(lambda x:x.source==dead_socket,self.commands)
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
            self.logger.debug("Closing out command %s" % command)
            command.source.sendMessage(command.reply)
            self.commands.remove(command)
    
    def not_implemented_command_handler(self, command):
        """
        Placeholder command handler 
        
        Agents may use this command handler as a placeholder.
        """
        command.setReply('!ERROR: Command not implemented.')
    
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
        Handle a status request, reply with cookie
        
        Agents will generally override this command handler
        """
        command.setReply(self.cookie)
    
    def do_select(self):
        """
        Select on all devices and sockets whcih require it.
        
        First call update_select_maps to get object:handler pairs on which to
            select for reading, writing, & errors.
        Perform the select call
        Call the appropriate handlers for each of the objects returned by select 
        """
        #select_start = time.time()
        read_map = {}
        write_map = {}
        error_map = {}
        self.update_select_maps(read_map, write_map, error_map)
        try:
            readers, writers, errors = select.select(
                read_map.keys(),write_map.keys(),error_map.keys(), 5)
        except select.error, err:
            if err[0] != EINTR:
                raise
        #select_end = time.time()
        #self.logger.debug("select used %.3f s" % (select_end-select_start))
        for reader in readers: read_map[reader]()
        for writer in writers: write_map[writer]()
        for error  in errors:  error_map[error]()       
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
        self.logger.info('Command line commands not yet implemented.')
        sys.exit(0)
    
    def runSetup(self):
        """
        Called once before entering main loop.
        Implement in subclass
        """
        pass
    
    def main(self):
        """
        Main loop (or one shot if no port). Act on commands as received.
        
        The general (only at time of writing) case assumes operation with a
        port. The typical flow is as follows:
        
        Agent has been initialized and SelectedConnections to all other devices
        and agents required have been created and are in devices & sockets.
        Main calls runSetup to allow subclasses to perform any additional setup
        and then enters the main loop.
        In the main loop, do_select is run, which checks each connection to see
        if it needs reading, writing, or checking for errors. It then selects
        on those connections, finally executing the read, write, or error 
        callbacks for each connected as indicated. For details of what these
        handlers do, see SelectedConnection. In essence they grab received data
        into an internal buffer until some criterion is met; transmit any
        pending data, & deal with an error, respectively.
        Next, any dead socket conectionions are dropped along with all commands
        received from those connections. Note that commands can only arrive from
        a connection in self.sockets and never in self.devices. Also note that
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
        
