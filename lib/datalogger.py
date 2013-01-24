import time, re
from construct import *
import SelectedConnection

class PlateManager(threading.Thread):
  """
    Class for Managing database of plates
    
    Runs as a daemon thread, automatically maintaining
    database of plates. The manager check the plate upload directory every
    UPLOAD_CHECK_INTERVAL seconds for files, exclusive of dotfiles, README,
    sample.plate, symlinks, & directories. If it finds any it attempts deletion
    of those larger than 1MB or not ending in .plate (case-insensitive).
    
    Of the remaining files, it verifies that they are valid plates (e.g.
    Plate(file) does not throw an exception). Valid plates are moved to the
    plates directory, while enforcing lowercase files names, and added to the
    plate database (I use the term loosely). Invalid plates are moved to the
    rejected directory and a file named platefile.reject is created with an
    explanation of why the plate was rejected. A plate with the same name as
    an existing plate is considered invalid.
    """
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon=True
        self.lock=threading.Lock()
        self.initialize_logger()
        self._plates={}
        self._plateDir=m2fsConfig.getPlateDir()
        self._rejectDir=m2fsConfig.getPlateRejectDir()
        self._uploadDir=m2fsConfig.getPlateUploadDir()
        #Load all of the existing platefiles as filenames
        for file in glob(self._plateDir+'*.plate'):
          self._plates[os.basename(file)]=file
        self.logger.info("Plates database initialized with %i plates" %
                         len(self._plates))

    def initialize_logger(self):
        """ Configure logging"""
        #create the logger
        self.logger=logging.getLogger('PlateManager')
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
  
  def run(self):
    """
      Main loop for the plate manager thread
      
      Run forever, monitoring the upload directory for files, when found
      (Barring the readme or sample plate) they are:
      1) If ending in .plate and <1MB, checked for validity and and moved to
      either the plate repository or the rejected plates directory. Valid
      plates are also added to the database of known plates.
      2) If not ending in .plate or >1MB they are deleted.
      """
    while True:
      #Get list of files in upload directory
      try:
        #Get list of all non dotfiles, non symlink files in upload dir
        # not having name in EXCLUDE_FILES. Search any subdirectories
        os.chdir(self._uploadDir)
        files=os.listdir('.')
        files=filter(files, lambda x: not (fnmatch(n, '.*') or
                                           fnmatch(n, 'README') or
                                           fnmatch(n, 'sample.plate') or
                                           os.path.isdir(x) or
                                           os.path.islink(x)))
      except OSError:
        files=[]
      #Filter on size, type and functionality
      rejectFiles=[]
      trashFiles=[]
      goodFiles=[]
      for fname in files:
        try:
          if (len(fname) < 6 or
              fname[-6].lower() != '.plate' or
              os.path.getsize(fname) > FILE_SIZE_LIMIT_BYTES):
            trashFiles.append(f)
          else:
            try:
              #Reject if plate isn't a valid plate, or plate by
              # same name already exists, file case is ignored
              # for name comparison. All plates are copied
              # in lower case
              Plate(f)
              if os.path.exists(self._goodDir+fname.lower()):
                raise Exception('Plate already exists.')
              goodFiles.append(f)
            except Exception, e:
              rejectFiles.append((f,e))
        except Exception:
          trashFiles.append(f)
      #Delete all files >1MB or not ending in plate
      for f in trashFiles:
        try:
          os.remove(f)
        except:
          pass
      #Log and move bad files to reject directory, with reason
      for f,reason in rejectFiles:
        logger.info("%s has issue %s" % (f,str(reason)))
        try:
          shutil.move(f, rejectDir)
          reasonFile=file(rejectDir+fname+'.reject',"w")
          reasonFile.write(str(reason))
          reasonFile.close()
        except Exception, e:
          self.logger.error('Caught while rejecting plate: %s' % str(e))
      #Log and move good files into plates directory, add to database
      for f in goodFiles:
        self.logger.info("Plate %s added to database." % f)
        try:
          importpath=self._goodDir+f.lower()
          shutil.move(f, importPath)
          self.lock.acquire(True)
          #Store plate with name as key, fully qualified path as item
          self._plates[f.lower()[:-6]]=importPath
        except Exception, e:
          self.logger.error('Caught while importing plate: %s' % str(e))
        finally:
          self.lock.release()
  

    def have_unfetched_temps(self):
        self.lock.acquire(True)
        ret=self._have_unfetched_temps
        self.lock.release()
        return ret
    
    def have_unfetched_accels(self):
        return self._have_unfetched_accels

    def fetch_temps(self):
        self._have_unfetched_temps=False
        return (self.temps_timestamp, self.current_temps)

    def fetch_accels(self):
        self._have_unfetched_accels=False
        return (self.accels_timestamp, self.current_accels)



class Datalogger(SelectedConnection.SelectedSerial):
    """ Datalogger  Controller Class """
    def __init__(self, device):
        """open a threaded serial port connection with the controller
        assert the controller is running the correct version of the code
        """
        self.mode='default'
        self.n_temp_sensors=5
        self.messageHandler=None
        self._have_unfetched_temps=False
        self._have_unfetched_accels=False
        SelectedConnection.SelectedSerial.__init__(self, device, 115200)
  
    def handle_read(self):
        """Read from serial. Call callback"""
        try:
            self.in_buffer += self.connection.read(self.connection.inWaiting())
            if not self.in_buffer:
                raise IOError('Empty read')
        except Exception, err:
            self.handle_error(err)
        if self.mode=='default':
            byteIn=self.in_buffer[0]
            self.in_buffer=self.in_buffer[1:]
            if byteIn not in 't?BE#L':
                self.logger.debug("Out of sync, flushing buffer.")
                self.in_buffer=''
                byteIn=''
            self._setModeAndHandlerFromByte(byteIn)
        if self.mode=='listen4N' and len(self.in_buffer)>0:
            # listen for number of bytes to listen for mode
            self.length_of_incomming_message=ord(self.in_buffer[0])
            self.in_buffer=self.in_buffer[1:]
            #self.logger.debug("listen4N message of length %i" % 
            #    self.length_of_incomming_message)
            self.mode='listenN'
        if self.mode=='listenN' and len(self.in_buffer) >= self.length_of_incomming_message: 
            #listen for N bytes mode
            message_str=self.in_buffer[:self.length_of_incomming_message]
            self.in_buffer=self.in_buffer[self.length_of_incomming_message:]
            #self.logger.debug("Received message of length %i on %s" % 
            #    (self.length_of_incomming_message, self))
            if self.messageHandler:
                self.connection.write('\x23');self.logger.debug("Send #")
                callback=self.messageHandler
                self.messageHandler=None
                #callback(message_str)
            self.mode='default'
        if self.mode=='listen/n':
            count=self.in_buffer.find('\n')
            if count is not -1:
                message_str=self.in_buffer[0:count+1]
                self.in_buffer=self.in_buffer[count+1:]
                #self.logger.debug("Received message '%s'" % message_str.encode('string_escape'))
                if self.messageHandler:
                    callback=self.messageHandler
                    self.messageHandler=None
                    callback(message_str[:-1])
                self.mode='default'

    def _setModeAndHandlerFromByte(self, byteIn):
        #self.logger.debug("ByteIn:%s"%byteIn)
        if  byteIn == 't':
            self.send_time_to_datalogger()
        elif byteIn == 'B':
            self.length_of_incomming_message=X #TODO
            self.mode=='listenN'
            self.messageHandler=self.receiveBatteryStatus
        elif byteIn == 'E':
            self.mode='listen/n'
            self.messageHandler=self.receiveError
        elif byteIn == '#':
            self.mode='listen/n'
            self.messageHandler=self.receiveDebugMessage
        elif byteIn == 'L':
            self.mode='listen4N'
            #callback must put '#' into out_buffer once message is received
            self.messageHandler=self.receiveLogData
    
    
    def send_time_to_datalogger(self):
        """ send the current time to the datalogger"""
        utime=int(time.time())
        hexutime=hex(utime)[2:].upper()
        s='t'+UBInt32("f").build(utime)
        self.logger.debug('Sending time as %s' % s.encode('string_escape'))
        #this is what it took to send the time in testing, oh if only self.connection.write(s) would work
        self.connection.write(s[0])
        self.connection.write('\x00'+s[1])
        self.connection.write('\x00'+s[2])
        self.connection.write('\x00'+s[3])
        self.connection.write('\x00'+s[4])
        
    def receiveLogData(self, data):
        """ Convert logger data into a nice neat form and sit on it"""
        Acceleration_Record_Length=8+6*32
        Temp_Record_Length=8+4*self.n_temp_sensors
        Combined_Record_Length=Acceleration_Record_Length+4*self.n_temp_sensors
        tempConstruct=StrictRepeater(self.n_temp_sensors,LFloat32("temps"))
        accelConstruct=StrictRepeater(32*3,SLInt16("accel"))
        if len(data)==Combined_Record_Length:
            self._have_unfetched_accels=True
            self._have_unfetched_temps=True
            self.current_temps=tempConstruct.parse(data[0:4*self.n_temp_sensors+1])
            self.current_accels=accelConstruct.parse(data[4*self.n_temp_sensors+1:-8])
            self.most_recent_record_timestamp=(
                ULInt32("foo").parse(data[-8:-4]),
                ULInt32("foo").parse(data[-4:])
                )
            self.accels_timestamp=self.most_recent_record_timestamp
            self.temps_timestamp=self.most_recent_record_timestamp  
        elif len(data)==Acceleration_Record_Length:
            self._have_unfetched_accels=True
            self.current_accels=accelConstruct.parse(data[0:-8])
            self.most_recent_record_timestamp=(
                ULInt32("foo").parse(data[-8:-4]),
                ULInt32("foo").parse(data[-4:])
                )
            self.accels_timestamp=self.most_recent_record_timestamp
        elif len(data)==Temp_Record_Length:
            self._have_unfetched_temps=True
            self.current_temps=tempConstruct.parse(data[0:-8])
            self.most_recent_record_timestamp=(
                ULInt32("foo").parse(data[-8:-4]),
                ULInt32("foo").parse(data[-4:])
                )
            self.temps_timestamp=self.most_recent_record_timestamp
        #NB: to convert accels to Gs and numpy array do:
        # 0.00390625*numpy.array(accels).reshape([32,3])
        #time.strftime("%a, %d %b %Y %H:%M:%S +0000",time.localtime(data.unixtime))
        
    def receiveDebugMessage(self, message):
        """ Process a debugging message from the datalogger"""
        cleanmsg=message.encode('string_escape')
        self.logger.debug("%s: %s" % (self.addr_str(),cleanmsg) )
        
    def receiveError(self, message):
        """ Process an error message from the datalogger"""
        cleanmsg=message.encode('string_escape')
        self.logger.error("%s: %s" % (self.addr_str(),cleanmsg) )
	
    def receiveBatteryStatus(self, message):
        """ Process an error message from the datalogger"""
        cleanmsg=message.encode('string_escape')
        self.logger.info("%s battery at %s" % (self.addr_str(),cleanmsg) )
    
    def have_unfetched_temps(self):
        return self._have_unfetched_temps
    
    def have_unfetched_accels(self):
        return self._have_unfetched_accels

    def fetch_temps(self):
        self._have_unfetched_temps=False
        return (self.temps_timestamp, self.current_temps)

    def fetch_accels(self):
        self._have_unfetched_accels=False
        return (self.accels_timestamp, self.current_accels)
