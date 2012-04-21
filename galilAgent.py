#!/opt/local/bin/python2.7
import time
import argparse
import socket
import signal
import logging
import logging.handlers
import atexit
import serial
import sys
import select
sys.path.append('./galil/')
import galil
from HandledSocket import HandledSocket

MAX_CLIENTS=2
VERSION_STRING='0.1'

#http://stackoverflow.com/questions/5943249/python-argparse-and-controlling-overriding-the-exit-status-code
class ArgumentParser(argparse.ArgumentParser):    
    def _get_action_from_name(self, name):
        """Given a name, get the Action instance registered with this parser.
        If only it were made available in the ArgumentError object. It is 
        passed as it's first arg...
        """
        container = self._actions
        if name is None:
            return None
        for action in container:
            if '/'.join(action.option_strings) == name:
                return action
            elif action.metavar == name:
                return action
            elif action.dest == name:
                return action

    def error(self, message):
        exc = sys.exc_info()[1]
        if exc:
            exc.argument = self._get_action_from_name(exc.argument_name)
            raise exc
        super(ArgumentParser, self).error(message)

    def exit(self):
        pass
        

class Command:
    def __init__(self, source, command_string,
                 callback=None, state='recieved',
                 replyRequired=True, reply=None):
        self.source=source
        self.string=command_string
        self.callback=callback
        self.state=state
        self.replyRequired=replyRequired
        self.reply=reply
        
    def __str__(self):
        return ''.join([str(self.source),str(self.string),
                        str(self.state),str(self.reply)])


class GalilAgent():
    def __init__(self):
        
        helpdesc="This is the galil agent. It takes shoe commands via \
            a socket connection (if started as a daemon) or via \
            CLI arguments."
    
        self.agentName='Galil Agent'
        default_device='/dev/galilR'
        self.devices=[]
        self.commands={}
                
        #configure specialized agent command parsing
        self.configure_command_parser()

      
        #create the logger
        self.logger=logging.getLogger(self.agentName)
        self.logger.setLevel(logging.DEBUG)
        # create formatter
        formatter = logging.Formatter(
            '%(asctime)s:%(name)s:%(levelname)s - %(message)s')
        # create console handler and set level to debug
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # create syslog handler and set level to debug
        sh = logging.handlers.SysLogHandler(facility=
                logging.handlers.SysLogHandler.LOG_USER)
        sh.setLevel(logging.DEBUG)
        # add formatter to handlers
        ch.setFormatter(formatter)
        sh.setFormatter(formatter)
        # add handlers to logger
        self.logger.addHandler(ch)
        #self.logger.addHandler(sh)
        
        #Create a command parser with the default agent commands
        cli_parser = argparse.ArgumentParser(
                    description=helpdesc,
                    add_help=True)
        cli_parser.add_argument('--version',
                                action='version',
                                version=VERSION_STRING)
        cli_parser.add_argument('--device', dest='DEVICE',
                                action='store', required=False, type=str,
                                help='the device to control',
                                default=default_device)
        cli_parser.add_argument('-p','--port', dest='PORT',
                                action='store', required=False, type=int,
                                help='the port on which to listen')
        cli_parser.add_argument('-d','--daemon',dest='DAEMONIZE',
                                action='store_true', default=False,
                                help='Run agent as a daemon')
        cli_parser.add_argument('command',nargs='*',
                                help='Agent command to execute') 
        self.cli_parser=cli_parser

        #parse the args to grab a port, if found listen for connections
        args=self.cli_parser.parse_args()
        
        if args.DAEMONIZE:
            import pwd
            # do the UNIX double-fork magic, see Stevens' "Advanced
            # Programming in the UNIX Environment" for details 
            # (ISBN 0201563177)
            try:
                pid = os.fork()
                if pid > 0:
                    # exit first parent
                    sys.exit(0)
            except OSError, e:
                self.logger.error("fork #1 failed: %d (%s)\n" % 
                                  (e.errno, e.strerror))
                sys.exit(1)

            # decouple from parent environment
            os.chdir("/")   # don't prevent unmounting....
            os.setsid()
            os.umask(0)

            # do second fork
            try:
                pid = os.fork()
                if pid > 0:
                    # exit from second parent, print eventual PID before
                    # print "Daemon PID %d" % pid
                    if options.pid_file is not None:
                        open(options.pid_file,'w').write("%d"%pid)
                    sys.exit(0)
            except OSError, e:
                self.logger.error("fork #2 failed: %d (%s)\n" % 
                                  (e.errno, e.strerror))
                sys.exit(1)

            # ensure the that the daemon runs a normal user, if run as root
            #if os.getuid() == 0:
                #    name, passwd, uid, gid, desc, home, shell = pwd.getpwnam('someuser')
                #    os.setgid(gid)     # set group first
                #    os.setuid(uid)     # set user
      
        self.sockets=[]
        if args.PORT:
            #start the socket server, if required
            self.PORT=args.PORT
            self.server_socket = socket.socket(socket.AF_INET,
                                               socket.SOCK_STREAM)
            self.server_socket.setblocking(0)
            try:
                self.server_socket.bind( ('localhost', self.PORT) )
                self.server_socket.listen(1)
            except socket.error, msg:
                self.handle_server_error()
            self.logger.info(" Waiting for connection on %s:%s..." % 
                             ('localhost', self.PORT))
        else:
            self.PORT=None
            self.server_socket=None
        
        #register an exit function
        atexit.register(self.on_exit, self)
        
        #register a terminate signal handler
        signal.signal(signal.SIGTERM, lambda signum, stack_frame: exit(1))

        #Initialize the Galil
        try:
            galilR=galil.Galil(args.DEVICE, self.logger)
        except galil.GalilStartupException:
            exit(1)
        
        self.devices.append(galilR)
    
    def on_exit(self, arg):
        """Prepare to exit"""
        self.logger.info("exiting %s" % arg)
        if self.server_socket:
            self.server_socket.close()
        for d in self.devices:
            d.close()
        for s in self.sockets:
            s.handle_disconnect()
    
    def handle_connect(self):
        """Server socket gets a connection"""
        # accept a connection in any case, close connection
        # below if already busy
        connection, addr = self.server_socket.accept()
        if len(self.sockets) < MAX_CLIENTS:
            soc = HandledSocket(connection, logger=self.logger,
                                message_callback=self.socket_message_recieved_callback)
            soc.setblocking(0)
            soc.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.logger.info('Connected with %s:%s' % (addr[0], addr[1]))
            self.sockets.append(soc)
            self.commands[soc]=None
            
        else:
            # reject connection if there is already one
            connection.close()
            self.logger.info('Rejecting connect from %s:%s' %
                             (addr[0], addr[1]))
    
    def handle_server_error(self):
        """Socket server fails"""
        self.logger.error('Socket server error. exiting.')
        sys.exit(1)
        
    def configure_command_parser(self):
        #Create a parser for commands
        self.command_parser=ArgumentParser(description='Command Parser',
                                           add_help=True)
        subparsers = self.command_parser.add_subparsers(dest='command_name',
                                               help='sub-command help')
        #commands command
        subparsers.add_parser("commands", help="Return a list of commands")
        #TD command
        td=subparsers.add_parser("TD", help="Tell Position of tetris")
        td.add_argument('tetrisID',choices='ABCDEFGH',
                        help='The tetris to command')
        #DP command
        dp=subparsers.add_parser("DP", help="Define Position of tetris")
        dp.add_argument('tetrisID',choices='ABCDEFGH',
                        help='The tetris to command')
        dp.add_argument('pos', type=int,
                        help='The position to define as 0 \
                             (default: the current position)')
    
    def update_select_maps(self, read_map, write_map, error_map):
        """Update dictionaries for select call. insert fd->callback mapping"""
        # check the server socket
        read_map[self.server_socket] = self.handle_connect
        error_map[self.server_socket] = self.handle_server_error
        #check client sockets
        for s in self.sockets:
            if s.socket is not None:
                # handle socket if connected
                read_map[s] = s.handle_read
                # only check for write readiness when there is data
                if s.have_data_to_send():
                    write_map[s] = s.handle_write
                # always check for errors
                error_map[s] = s.handle_error
            else:
                # no connection, ensure clear buffer
                s.clear_output_buffer()
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
        dead_sockets=filter(lambda x: x.socket is None, self.sockets)
        #cull dead keys from self.commands
        #   and dead sockets from self.sockets
        if dead_sockets is not None:
            for dead_socket in dead_sockets:
                self.logger.debug("Cull dead socket:%s"% dead_socket)
                self.commands.pop(dead_socket,None)
                self.sockets.remove(dead_socket)
    
    
    def socket_message_recieved_callback(self, source, message_str):
        """Create and execute a Command from the message"""
        if False:#message_str is malformed:
            command=Command(source, message_str, state='complete',
                reply='!ERROR: Malformed Command', callback=None)
        else:
            command=Command(source, message_str, callback=None)
            
            if self.commands[source] is not None:
                #...ignore and log error
                self.logger.warning(
                    'Command %s recieved before command %s finished.' %
                    (command.string, self.commands[source].string))
            else:
                self.commands[source]=command
        
                if False:# TODO command is command for agent:
                    1
                else:
                    def responseCallback(response_string):
                        command.state='complete'
                        command.reply=response_string
                    def errorCallback(response_string):
                        command.state='complete'
                        command.reply='!ERROR:'+response_string
                    self.devices[0].executeCommand(
                        command.string,
                        responseCallback,
                        errorCallback
                        )
                
    def handle_completed_commands(self):
        """Return results of complete commands and cull the commands."""
        complete_command_keys=filter(lambda x: #TODO there is a bug here when the client disconnects
                self.commands[x] is not None and
                self.commands[x].state=='complete',
                self.commands.keys())
        if complete_command_keys is not None:  
            for key in complete_command_keys:
                command=self.commands[key]
                self.logger.debug("Closing out command %s" % command)
                command.source.out_buffer=command.reply #TODO: make this a function
                self.commands[key]=None
    
    def main(self):
        """
        Loop forever, acting on commands as received if on a port.
        
        Run once from command line if no port.
        
        """
        if self.PORT is None:
            """Run off command line argument and exit."""
         
            try:
                command_str=self.cli_parser.parse_args().command
                command=self.command_parser.parse_args(command_str)
                command={'string':command_str,
                         'callback':getattr(self,'command'+
                                            command[0].upper()),
                         'args':command[1:],
                         'state':'recieved'}
            except Exception,err:
                raise err
                
            #Act on the command
            
            #Get result of command
            
            #Report result of command
            
            #Exit
            sys.exit(0)
            
        while True:
            select_start = time.time()
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
            select_end = time.time()
            #self.logger.debug("select used %.3f s" % (select_end-select_start))
            for reader in readers: read_map[reader]()
            for writer in writers: write_map[writer]()
            for error  in errors:  error_map[error]()       
            #self.logger.debug("select operation used %.3f s" % (time.time() - select_end))

            #log commands
            for source, command in self.commands.items():
                self.logger.debug(command)
            
            self.cull_dead_sockets_and_their_commands()
            self.handle_completed_commands()
            


if __name__=='__main__':
    agent=GalilAgent()
    agent.main()

