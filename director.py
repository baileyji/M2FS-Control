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
    def __init__(self, source, string, parsedCommand,
                 callback=None, state='recieved',
                 replyRequired=True, reply=None):
        self.source=source
        self.string=string
        self.callback=callback
        self.state=state
        self.replyRequired=replyRequired
        self.reply=reply
        self.parsedCommand=parsedCommand
        
    def __str__(self):
        return ''.join([str(self.source),str(self.string),
                        str(self.state),str(self.reply)])

class HandledSocket():
    def __init__(self, sock, message_callback=None,logger=None):
        self.__dict__['socket']=sock
        self.__dict__['logger']=logger
        self.__dict__['in_buffer']=''
        self.__dict__['out_buffer']=''
        self.__dict__['message_recieved_callback']=message_callback

    def __getattr__(self, attr):
        return getattr(self.socket, attr)
    #def __setattr__(self, attr, value):
        #return setattr(self.socket, attr, value)   

    def handle_read(self):
        """Read from socket. Call callback"""
        try:
            # read a chunk from the serial port
            data = self.socket.recv(1024)
            if data:
                self.in_buffer += data
                count=self.in_buffer.find('\n')
                if count is not -1:
                    message_str=self.in_buffer[0:count+1]
                    self.in_buffer=self.in_buffer[count+1:]
                    self.logger.info("Recieved command %s on %s" % 
                        (message_str, self))
                    self.message_recieved_callback(self,message_str)
            else:
                # empty read indicates disconnection
                self.handle_disconnect()
        except socket.error:
            self.handle_socket_error()
            
    def handle_write(self):
        """Write to socket"""
        try:
            if self.out_buffer and '\n' not in self.out_buffer:
                self.out_buffer+='\n'
            # write a chunk
            count = self.socket.send(self.out_buffer)
            self.logger.debug('Attempted write: "%s" , Wrote: "%s"' %
                              (self.out_buffer,self.out_buffer[count:]))
            # and remove the sent data from the buffer
            self.out_buffer = self.out_buffer[count:]
        except socket.error,err:
            self.handle_socket_error(err)

    def handle_error(self, error=None):
        """Socket connection fails"""
        self.logger.error("Socket error %s, disconnecting." % socket.error)
        self.handle_disconnect()
        
    def handle_disconnect(self):
        """Socket gets disconnected"""
        # close network connection
        if self.socket is not None:
            self.socket.close()
            self.socket = None
            self.logger.info('Client disconnected')
        
        
class HandledSerial():
    """class that add select handlers to serial.Serial
    
    messageComplete shall be a function which accepts a string
    and returns the length of the complete message, <1 indicate message 
    is incomplete
    """
    def __init__(self, baudrate=115200, timeout=0, logger=None,
                 sendTerminator='\r', messageComplete=None):
        self.serial=serial.Serial(baudrate=baudrate,timeout=timeout)
        self.logger=logger
        self.in_buffer=''
        self.out_buffer=''
        self.message_sent_callback=None
        self.message_recieved_callback=None
        self.sendTerminator=sendTerminator
        if messageComplete is None:
            self.messageComplete=lambda msg: msg.find('\n')+1
        else:
            self.messageComplete=messageComplete

    def __getattr__(self, attr):
        return getattr(self.serial, attr)

    def handle_read(self):
        bytes_in=self.read(self.inWaiting())
        self.in_buffer+=bytes_in
        #see if message is complete
        msg_len=self.messageComplete(self.in_buffer)
        if msg_len > 0:
            #Complete mesage just recieved
            message_str=self.in_buffer[0:msg_len]
            self.in_buffer=self.in_buffer[msg_len:]
            #message is a response
            self.logger.info("Recieved serial data %s on %s" % 
                (message_str, self))
            if self.message_recieved_callback:
                self.message_recieved_callback(self, message_str)

    def handle_write(self):
        if self.out_buffer:
            try:
                count=self.write(self.out_buffer)
                self.out_buffer=self.out_buffer[count:]
                if (not self.out_buffer and 
                    self.message_sent_callback is not None):
                    self.message_sent_callback(self)
            except serial.SerialException,err:
                self.handle_error(error=err)

    def handle_error(self,error=None):
        self.close()
        if error is not None:
            self.logger.error('%s error %s' % (self.port,error))
        else:
            self.logger.error('Serial port %s error.' % self.port)

    def send_message(self, msg, sentCallback=None, recievedCallback=None):
        """Add message to output buffer and register callbacks
        
        Message may have at most one terminator and it must be at the end of
        the message. If message does not have a terminator one will be added.
        """
        if self.out_buffer:
            raise Exception("Message pending")
        msg_str=str(msg)
        terminator_count=msg_str.count(self.sendTerminator)
        if terminator_count == 0:
            msg_str=msg_str+self.sendTerminator
        elif terminator_count == 1:
            if msg_str[-1] != self.sendTerminator:
                raise Exception("Message terminator not and end of message")
        else:
            raise Exception("Message malformed: has multiple terminators.")
        self.flushInput()
        self.out_buffer=msg_str
        if sentCallback is not None:
            self.message_sent_callback=sentCallback
        if recievedCallback is not None:
            self.message_recieved_callback=recievedCallback


class RedShoeAgent():
    def __init__(self):
        
        helpdesc="This is the shoe agent. It takes shoe commands via \
            a socket connection (if started as a daemon) or via \
            CLI arguments."
    
        name='Shoe Agent'
        self.agentName=name
      
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
        
        
        #configure specialized agent command parsing
        self.configure_command_parser()

        #Open the shoe
        def shoeMsgCompleteFunc(msg):
            """
            Determine if message from shoe is complete.
            
            Shoe ends response with : or ? based on command being good
            or bad. The colon and question mark are not used anywhere else.
            """
            #0 if no : or ?
            #-1 plus location of : or ? plus 2 is length of message, otherwise
            return msg.find(':')+msg.find('?')+2
            
        shoe=HandledSerial(baudrate=115200,timeout=0,
                           logger=self.logger,
                           sendTerminator='\n', 
                           messageComplete=shoeMsgCompleteFunc
                           )
        shoe.serial.port='/dev/tty.usbmodemfd14711'
        try:
            shoe.open()
        except serial.SerialException,err:
            shoe.handle_error(error=err)
            
        self.devices=[shoe]
        self.commands={}
        
    def on_exit(self, arg):
        """Prepare to exit"""
        self.logger.info("exiting %s" % arg)
        if self.server_socket:
            self.server_socket.close()
        for d in self.devices:
            d.close()
        for s in self.sockets:
            s.handle_disconnect()
            
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
    
    def handle_connect(self):
        """Server socket gets a connection"""
        # accept a connection in any case, close connection
        # below if already busy
        connection, addr = self.server_socket.accept()
        if len(self.sockets) < MAX_CLIENTS:
            soc = HandledSocket(connection,logger=self.logger,
                                message_callback=self.socket_message_processor)
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
                if s.out_buffer:
                    write_map[s] = s.handle_write
                # always check for errors
                error_map[s] = s.handle_error
            else:
                # no connection, ensure clear buffer
                s.out_buffer = ''
        #check device connections
        for device in self.devices:
            if not device.isOpen():
                try:
                    device.open()
                except serial.SerialException,e:
                    self.logger.debug("couldn't open shoe for command")
                    for key in filter(lambda k: self.commands[k] is not None,
                                      self.commands.keys()):
                        self.commands[key].state='complete'
                        self.commands[key].reply='Device not available'
            else:    
                # always handle device reads & errors
                read_map[device] = device.handle_read
                error_map[device] = device.handle_error
                # handle serial port writes if buffer is not empty
                if device.out_buffer:
                    write_map[device] = device.handle_write
    
    def socket_message_processor(self, source, message_str):
        """for the shoe we won't ever get a response over a socket"""
        #if message is command
        self.socket_command_handler(source, message_str)
        #if message is response
        #   self.socket_response_handler(source, message_str)
    
    def socket_command_handler(self, source, message_str):
        """Create and execute a Command from the message"""
        #try parsing command
        try:
            from cStringIO import StringIO
            sys.stderr = mystderr = StringIO()
            command=self.command_parser.parse_args(message_str.split())
            sys.stderr = sys.__stderr__
            cmderrmsg=mystderr.getvalue()
            #fetch the command callback
            callback=getattr(self,'command_'+command.command_name.upper())
            #create the command
            command=Command(source, message_str,command, callback=callback)
        #command was bad
        except argparse.ArgumentError, err:
            sys.stderr = sys.__stderr__
            cmderrmsg=mystderr.getvalue()
            err_str='command parse error %s on command \
                   string %s' % (str(err),message_str)
            err_str.replace('\n', '\r')
            self.logger.error(err_str)
            self.logger.error(mystderr.getvalue())
            command=Command(source, message_str, None,state='complete',
                            reply=err_str)
        #if command from device already exists
        if self.commands[source] is not None:
            #...ignore and log error
            self.logger.warning('Command %s recieved \
                                 before command %s finished.' %
                                 (command.string,self.commands[source].string))
        else:
            self.commands[source]=command
            if self.commands[source].callback is not None:
                self.commands[source].callback(self.commands[source])
    
                    
    def cull_dead_sockets_and_their_commands(self):
        dead_sockets=filter(lambda x: x.socket is None, self.sockets)
        #cull dead keys from self.commands
        #   and dead sockets from self.sockets
        if dead_sockets is not None:
            for dead_socket in dead_sockets:
                self.logger.debug("Cull dead socket:%s"% dead_socket)
                self.commands.pop(dead_socket,None)
                self.sockets.remove(dead_socket)
                
    def handle_completed_commands(self):
        """Return results of complete commands and cull the commands."""
        complete_command_keys=filter(lambda x: 
                self.commands[x] is not None and
                self.commands[x].state=='complete',
                self.commands.keys())
        if complete_command_keys is not None:  
            for key in complete_command_keys:
                command=self.commands[key]
                self.logger.debug("Closing out command %s" % command)
                command.source.out_buffer=command.reply
                self.commands[key]=None
    
    def command_COMMANDS(self, command):
        """Report a list of all agent commands."""
        command.state='complete'
        command.reply='list\rof\rcommands\n'
        self.logger.info('commands callback')
    
    def command_TD(self,command):
        command.state='pending'
        msg='TD'+command.parsedCommand.tetrisID
        self.logger.info('%s to device %s' % (msg,self.devices[0]))
        def callback(source, message):
            self.logger.debug("Response callback: %s, %s" % (source, message))
            if '?' in message:
                command.reply='Bad command. The offending command should never have been sent to the device.'
            else:
                command.reply=message.strip('\n\r?:')
            command.state='complete'
        self.devices[0].send_message(msg, recievedCallback=callback)
    
    def command_SP(self,command):
        command.state='pending'
        msg='SP'+command.parsedCommand.tetrisID+command.parsedCommand.speed
        self.logger.info('%s to device %s' % (msg,self.devices[0]))
        def callback(source, message):
            if ':' in message:
                command.reply='OK'
            else:
                command.reply='INVALID'
            command.state='complete'
        self.devices[0].send_message(msg, recievedCallback=callback)
    
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
            
        while 1:
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
            #self.logger.debug("select used %.3f s" % (select_end - 
            #                                          select_start))
            for reader in readers:
                read_map[reader]()
            for writer in writers:
                write_map[writer]()
            for error in errors:
                error_map[error]()       
            #self.logger.debug("select operation used %.3f s" % (time.time() - select_end))

            #log commands
            for source, command in self.commands.items():
                self.logger.debug(command)
            
            self.cull_dead_sockets_and_their_commands()
            self.handle_completed_commands()
            


if __name__=='__main__':
    agent=RedShoeAgent()
    agent.main()

    


"""
  cout<<"PRx# Position Relative - Command tetris x to move #"<<endl;
  cout<<"SPx# Speed - Set the movement speed of tetris x to # (usteps/s)"<<endl;
  cout<<"ACx# Acceleration - Set the acceleration rate of tetris x to # (usteps/s^2)"<<endl;
  cout<<"SLx# Slit - Command tetris x to go to the position of slit #"<<endl;
  cout<<"SDx# Slit Define - Set slit # for tetris x to be at the current position"<<endl;
  cout<<"BLx# Backlash - Set the amount of backlash of tetris x to # (usteps)"<<endl;
"""
