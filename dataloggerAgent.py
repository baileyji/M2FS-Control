#!/usr/bin/python
import time
import argparse
import socket
import signal
import logging
import atexit
from construct import *

MAX_CLIENTS=2

class Command:
    def __init__(self, source, string,
                 args=None, function=None, state='recieved',
                 replyRequired=True, reply=None)
        self.source=source
        self.string=string
        self.args=args
        self.function=function
        self.state=state
        self.replyRequired=replyRequired
        self.reply=reply

class HandledSocket():

    def __init__(self, socket, message_callback=None):
        self.socket=socket
        self.in_buffer=''
        self.out_buffer=''
        self.message_recieved_callback=message_callback
        self.logger=
      
    def __getattr__(self, attr):
        return getattr(self.socket, attr)
    def __setattr__(self, attr, value):
        return setattr(self.socket, attr, value)   

    def handle_read(self):
        """Read from socket. Call callback"""
        try:
            # read a chunk from the serial port
            data = self.socket.recv(1024)
            if data:
                self.in_buffer += data
                count=self.in_buffer.find('\n')
                if count is not -1:
                    message_str=self.in_buffer[0:count]
                    self.in_buffer=self.in_buffer[count:]
                    self.message_recieved_callback(message_str)
            else:
                # empty read indicates disconnection
                self.handle_disconnect()
                self.logger.info("Client disconnected.")
        except socket.error:
            self.handle_socket_error()
            
    def handle_write(self):
        """Write to socket"""
        try:
            # write a chunk
            count = self.socket.send(self.out_buffer)
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
        
        
class HandledSerial(serial.Serial):
  """class that add select handlers to serial.Serial"""
    def __init__(self,serial,message_callback=None):
        self.serial=serial
        self.logger=logging.getLogger(str(self.port))
        self.in_buffer=''
        self.out_buffer=''
        self.message_recieved_callback=message_callback

    def __getattr__(self, attr):
        return getattr(self.serial, attr)
        
    def __setattr__(self, attr, value):
        return setattr(self.serial, attr, value)  

    def handle_read(self):
        bytes_in=self.read(self.inWaiting())
        self.in_buffer+=bytes_in
        #see if message is complete
        count=-1
        if bytes_in[0]='t' or bytes_in[0]=='?':
            count=1
        else if bytes_in[0]='L' and
                len(bytes_in) > 2 and
                len(bytes_in)>=ord(bytes_in[1]):
            count=ord(bytes_in[1])+2
        else if bytes_in[0]=='#':
            count=bytes_in.find('/n')
        if count != -1:
            """Complete mesage just recieved"""
            message_str=self.in_buffer[0:count]
            self.in_buffer=self.in_buffer[count:]
            self.message_recieved_callback(message_str)
            
    def handle_write(self):
        try:
            count=self.write(self.out_buffer)
            self.out_buffer=self.out_buffer[count:]
        except serial.SerialError,err:
            self.handle_error(error=err)

    def handle_error(self,error=None):
        self.close()
        self.logger.error('Serial port %s timed out.'% self.device)        

    def open(self):
        try:
            self.serial.open()
        except serial.SerialError,err:
            self.handle_error(error=err)



class DataloggerAgent(Agent):
    VERSION_STRING='0.1'
    
    def __init__(self):
        
        helpdesc="This is the shoe agent. It takes shoe commands via
            a socket connection (if started as a daemon) or via
            CLI arguments."
    
        name='Datalogger Agent'
        
        
        self.name=name
      
        #create the logger
        self.logger=logging.getLogger(self.agentName)
        self.logger.setLevel(logging.DEBUG)
        # create formatter
        formatter = logging.Formatter('%(asctime)s - \
                                       %(name)s - \
                                       %(levelname)s - \
                                       %(message)s')
        # create console handler and set level to debug
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # create console handler and set level to debug
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # create syslog handler and set level to debug
        sh = logging.SysLogHandler(facility=LOG_USER)
        sh.setLevel(logging.DEBUG)
        # add formatter to handlers
        ch.setFormatter(formatter)
        sh.setFormatter(formatter)
        # add handlers to logger
        self.logger.addHandler(ch)
        self.logger.addHandler(sh)
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


        #Create a parser for commands
        self.command_parser=argparse.ArgumentParser(description='',
                                                    add_help=True)
        subparsers = command_parser.add_subparsers(dest='command_name',
                                               help='sub-command help')
        self.add_command_parser=subparsers.add_parser
        
        
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
                #~ raise
            logger.info("%s: Waiting for connection on %s..." % (self.PORT))
        else:
            self.PORT=None
            self.server_socket=None
        
        #register an exit function
        atexit.register(exit_handler, self)
        
        #register a terminate signal handler
        signal.signal(signal.SIGTERM, lambda signum, stack_frame: exit(1))
        
        #configure specialized agent command parsing
        command_list=[
                ("commands",
                 {'name':"commands",
                  'help':"Return a list of commands"}),
                ("getTemps",
                 {'name':"getTemps",
                  'help':"Tell Position - Tell position of tetris"})
                ]

        subcommand_parsers={}
        for name,argparse_dict in command_list:
            subcommand_parsers[name] = self.add_command_parser(**argparse_dict)

        subcommand_parsers['getTemps'].add_argument('sensor',type=int,
                                    help='The sensor # to poll')
        #Open conections to the dataloggers
        dataloggerR=HandledSerial(serial.Serial(baudrate=115200,timeout=0))
        dataloggerR.port='/dev/dataloggerR'
        dataloggerR.open()
        dataloggerR.message_recieved_callback=process_datalogger_message
        dataloggerB=HandledSerial(serial.Serial(baudrate=115200,timeout=0))
        dataloggerB.port='/dev/dataloggerB'
        dataloggerB.open()
        dataloggerB.message_recieved_callback=process_datalogger_message
        dataloggerC=HandledSerial(serial.Serial(baudrate=115200,timeout=0))
        dataloggerC.port='/dev/dataloggerC'
        dataloggerC.open()
        dataloggerC.message_recieved_callback=process_datalogger_message
        self.devices=[dataloggerR,dataloggerB,dataloggerC,]

    def exit_handler(self):
        """Close all resources and unpublish service"""
        self.logger.info("exiting")
        self.alive = False
        if self.server_socket: self.server_socket.close()
        if self.socket: self.handle_disconnect()
        if self.on_exit is not None:
            # ensure it is only called once
            callback = self.on_close
            self.on_close = None
            callback(self)

    def on_exit(self):
        """Prepare to exit"""
        for d in self.devices:
          d.close()
        for s in self.sockets:
          s.handle_disconnect()
        #TODO: What else
        
    def handle_connect(self):
        """Server socket gets a connection"""
        # accept a connection in any case, close connection
        # below if already busy
        connection, addr = self.server_socket.accept()
        if len(self.sockets) < MAX_CLIENTS:
            socket = HandledSocket(connection)
            socket.setblocking(0)
            socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.logger.info('Connected with %s:%s' % (addr[0], addr[1]))
            self.sockets.append(HandledSocket(socket),
                                message_callback=socket_message_processor
                                )

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
        for socket in self.sockets:
            if self.socket is not None:
                # handle socket if connected
                read_map[socket] = socket.handle_read
                # only check for write readiness when there is data
                if socket.out_buffer:
                    write_map[socket] = socket.handle_write
                # always check for errors
                error_map[socket] = socket.handle_error
            else:
                # no connection, ensure clear buffer
                socket.out_buffer = ''
        #check device connections
        for device in self.devices:
            if device.isOpen():
                # always handle device reads & errors
                read_map[device] = device.handle_read
                error_map[device] = device.handle_error
                # handle serial port writes if buffer is not empty
                if device.out_buffer:
                    write_map[device] = device.handle_write

    def socket_message_processor(self, source, message_str)
        """for the shoe we won't ever get a response over a socket"""
        #if message is command
            self.socket_command_handler(source, message_str)
        #if message is response
        #   self.socket_response_handler(source, message_str)
    
    def socket_command_handler(self, source, message_str)
        """Create and execute a Command from the message"""
        #try parsing command
        try:
            command=command_parser.parse_args(message_str)
            #fetch the command function
            try:
                function=getattr(self,'command'+command[0].upper())
            except AttributeError:
                function=None
            #create the command
            command=Command(source, message_str,func=function,
                            args=command[1:])
        #command was bad
        except argparse.ArgumentError, err:
            err_str='command parse error %s on command \
                   string %s' % (str(err),command_str)
            err_str.replace('\n', '\r')
            self.logger.error(err_str)
            command=Command(source, message_str,state='error',
                            reply=err_str)

        #if command from device already exists
        if commands[source] is not None:
            #...respond error
            self.logger.warning('Command %s recieved \
                                 before command %s finished.' %
                                 (command_str,self.command_str))
        else:
            self.commands[device]=command
            if self.commands[device].function is not None:
                self.commands[device].function(self.commands[device])
    
    
    def process_datalogger_message(self, source, message):
        if message=='t':
			command=Command(source, message_str,func=command_TELLTIME)
        else if message=='?':
			command=Command(source, message_str,func=command_PING)
        else if message[0]='L':
            command=Command(source, message_str, args=messgage, 
                            func=command_LOG)
        else if message[0]='#':
            command=Command(source, message_str, args=messgage, 
                            func=command_DEBUGMSG)
		#if byteIn == 'B':
		#	receiveBatteryStatus(ser),
		#if byteIn == 'E':
		#	receiveError(ser)
        #if command from device already exists
        if self.commands[source] is not None:
            #...respond error
            self.logger.warning('Command %s recieved \
                                 before command %s finished.' %
                                 (command_str,self.command_str))
        else:
            self.commands[device]=command
            if self.commands[device].function is not None:
                self.commands[device].function(self.commands[device])
    
    
    def command_COMMANDS(self, command):
        """Report a list of all agent commands."""
        command.reply='list\rof\rcommands\n'
            
    def command_GETTEMP(self,command):
        #get temp sensor value from database
        
        #set command reply and state
        command.reply=temp_value
        command.state='complete'

    def command_TELLTIME(self,command):
        """Time request from datalogger"""
        utime=int(time.time())
        hexutime=hex(utime)[2:].upper()
        command.reply='t'+UBInt32("f").build(utime)
        command.state='complete'
        #NB this was requiredin the test script
        #ser.write(s[0])
        #ser.write('\x00'+s[1])
        #ser.write('\x00'+s[2])
        #ser.write('\x00'+s[3])
        #ser.write('\x00'+s[4])
    
    def command_PING(self,command):
        """Connection test command from datalogger"""
        command.reply='!'
        command.state='complete'
    
    def command_LOG(self,command):
        """Log data from datalogger"""
        if command.source == self.dataloggerR:
            log_data_from_R(command.arg)
        else if command.source == self.dataloggerB:
            log_data_from_B(command.arg)
        else if command.source == self.dataloggerC:
            log_data_from_C(command.arg)
        command.reply='#'
        command.state='complete'

    def command_DEBUGMSG(self, command)
        command.state='complete'


    def log_data_from_B(message):
        Num_Temp_Sensors=5
		FIFO_Length=32
		Acceleration_Record_Length=8+6*FIFO_Length
		Temp_Record_Length=8+4*Num_Temp_Sensors
		Combined_Record_Length=Acceleration_Record_Length+4*Num_Temp_Sensors
		
		tempConstruct=StrictRepeater(Num_Temp_Sensors,LFloat32('temps'))
		accelConstruct=StrictRepeater(FIFO_Length*3,SLInt16('accel'))
		
		self.temps=None
		self.accels=None
		self.unixtime=None
		self.millis=None
        
        record=message[2:]
				
		if len(record)==Combined_Record_Length:
			self.temps=tempConstruct.parse(record[0:4*Num_Temp_Sensors+1])
			self.accels=accelConstruct.parse(record[4*Num_Temp_Sensors+1:-8])
		
		if len(record)==Acceleration_Record_Length:
			self.temps=None
			self.accels=accelConstruct.parse(record[0:-8])
		
		if len(record)==Temp_Record_Length:
			self.accels=None
			self.temps=tempConstruct.parse(record[0:-8])
		
		if len(record)>=Temp_Record_Length:
			self.unixtime=ULInt32('foo').parse(record[-8:-4])
			self.millis=ULInt32('foo').parse(record[-4:])
		
		if self.accels!=None:
			self.accels=numpy.array(self.accels).reshape([FIFO_Length,3])
			self.accels*=0.00390625



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
                    read_map.keys(),
                    write_map.keys(),
                    error_map.keys(),
                    5
                )
            except select.error, err:
                if err[0] != EINTR:
                    raise
            select_end = time.time()
            self.logger.debug("select used %.3f s" % (select_end - 
                                                      select_start))
            for reader in readers:
                read_map[reader]()
            for writer in writers:
                write_map[writer]()
            for error in errors:
                error_map[error]()       
            self.logger.debug("select operation used %.3f s" % (time.time() 
                                                                - select_end))


            
            
        
            for source,command in self.commands:
                if command.state=='complete':
                    source.out_buffer=command.reply
            
            set any complete commands to NONE

            

if __name__=='main':
    agent=RedShoeAgent()
    agent.main_loop()

    
class Message:
  def __init__(self, string, sentCallback=None):
    self.msg=string
    self.calback=sentCallback
    
  def __str__():
    return self.msg

"""
  cout<<"PRx# Position Relative - Command tetris x to move #"<<endl;
  cout<<"SPx# Speed - Set the movement speed of tetris x to # (usteps/s)"<<endl;
  cout<<"ACx# Acceleration - Set the acceleration rate of tetris x to # (usteps/s^2)"<<endl;
  cout<<"SLx# Slit - Command tetris x to go to the position of slit #"<<endl;
  cout<<"SDx# Slit Define - Set slit # for tetris x to be at the current position"<<endl;
  cout<<"BLx# Backlash - Set the amount of backlash of tetris x to # (usteps)"<<endl;
"""
