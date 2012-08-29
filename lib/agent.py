import time, argparse, signal, atexit, sys, select
import socket
import logging, logging.handlers
from command import Command
from SelectedConnection import SelectedSocket
from m2fsConfig import m2fsConfig

SERVER_RETRY_TIME=10
class Agent(object):
    def __init__(self, basename):
        self.sockets=[]
        self.devices=[]
        self.commands=[]
        self.max_clients=1
        self.cookie=time.time().__str__()
        self.initialize_cli_parser()
        self.args=self.cli_parser.parse_args()
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
        signal.signal(signal.SIGTERM, lambda signum, stack_frame: exit(1))
        signal.signal(signal.SIGINT, lambda signum, stack_frame: exit(1))
        self.command_handlers={
            'STATUS':self.status_command_handler,
            'VERSION':self.version_request_command_handler}
    
    def initialize_logger(self):
        """Configure logging"""
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
        """Configure the command line interface"""
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
            
    def initialize_socket_server(self, tries=0):
        """ Start listening for socket connections """
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setblocking(0)
            self.server_socket.bind(self.listenOn())
            self.server_socket.listen(1)
            self.logger.info(" Waiting for connection on %s:%s..." % self.listenOn())
        except socket.error, msg:
            if tries > 0:
                self.logger.info('Server socket error %s, retrying %s more times.'%(msg,tries))
                time.sleep(SERVER_RETRY_TIME)
                self.initialize_socket_server(tries=tries-1)
            else:
                self.handle_server_error(error=msg)
    
    def listenOn(self):
        """ Implemented by subclass """
        pass
    
    def socket_message_received_callback(self, source, message_str):
        """Create and execute a Command from the message"""
        command_name=message_str.partition(' ')[0]
        command=Command(source, message_str)
        existing_commands_from_source=filter(lambda x: x.source==source, self.commands)
        if existing_commands_from_source:
            self.logger.warning('Command %s received before command %s finished.' %
                (message_str, existing_commands_from_source[0].string))
        else:
            self.commands.append(command)
            self.command_handlers.get(command_name.upper(), self.bad_command_handler)(command)
        
    def get_version_string(self):
        return 'AGENT Base Class Version 0.1'
    
    def on_exit(self, arg):
        """Prepare to exit"""
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
        """Server socket gets a connection"""
        # accept a connection in any case, close connection
        # below if already busy
        connection, addr = self.server_socket.accept()
        if len(self.sockets) < self.max_clients:
            connection.setblocking(0)
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            soc = SelectedSocket(addr[0],addr[1], self.logger,
                Live_Socket_To_Use=connection,
                default_message_received_callback=self.socket_message_received_callback)
            self.logger.info('Connected with %s:%s' % (addr[0], addr[1]))
            self.sockets.append(soc)
        else:
            connection.close()
            self.logger.info(
                'Rejecting connect from %s:%s' % (addr[0], addr[1]))
    
    def handle_server_error(self, error=''):
        """Socket server fails"""
        self.logger.error('Socket server error:%s'%error)
        sys.exit(1)
        
    def update_select_maps(self, read_map, write_map, error_map):
        """Update dictionaries for select call. insert fd->callback mapping"""
        # check the server socket
        read_map[self.server_socket] = self.handle_connect
        error_map[self.server_socket] = self.handle_server_error
        #check client sockets
        for socket in self.sockets:
            if socket.do_select_read():
                read_map[socket] = socket.handle_read
            if socket.do_select_write():
                write_map[socket] = socket.handle_write
            if socket.do_select_error():
                error_map[socket] = socket.handle_error
        #check device connections
        for device in self.devices:
            if device.do_select_read():
                read_map[device] = device.handle_read
            if device.do_select_write():
                write_map[device] = device.handle_write
            if device.do_select_error():
                error_map[device] = device.handle_error
    
    def cull_dead_sockets_and_their_commands(self):
        """Remove dead sockets from list of sockets & purge commands from same."""
        dead_sockets=filter(lambda x: not x.isOpen(), self.sockets)
        for dead_socket in dead_sockets:
            self.logger.debug("Cull dead socket: %s" % dead_socket)
            self.sockets.remove(dead_socket)
            dead_commands=filter(lambda x:x.source==dead_socket,self.commands)
            for dead_command in dead_commands:
                self.commands.remove(dead_command)
                
    def handle_completed_commands(self):
        """Return results of complete commands and cull the commands."""
        completed_commands=filter(lambda x: x.state=='complete',self.commands)
        for command in completed_commands:
            self.logger.debug("Closing out command %s" % command)
            command.source.sendMessage(command.reply)
            self.commands.remove(command)

    def not_implemented_command_handler(self, command):
        """ Placeholder command handler """
        command.setReply('!ERROR: Command not implemented.\n')
    
    def bad_command_handler(self, command):
        """ Handle an unrecognized command """
        command.setReply('!ERROR: Unrecognized command.\n')
        
    def version_request_command_handler(self,command):
        """ Handle a version request """ 
        command.setReply(self.get_version_string()+'\n')

    def status_command_handler(self,command):
        """ Handle a status request, reply with cookie"""
        command.setReply(self.cookie+'\n')

    def do_select(self):
        """ Perform the select operation on all devices and sockets whcih require it """
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
        pass

    def runOnce(self):
        self.logger.info('Command line commands not yet implemented.')
        sys.exit(0)
    
    def runSetup(self):
        pass

    def main(self):
        """
        Loop forever, acting on commands as received if on a port.
        
        Run once from command line if no port.
        
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
        
