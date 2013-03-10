import time

def escapeString(string):
    return string.replace('\n','\\n').replace('\r','\\r')

class Command:
    def __init__(self, source, command_string,
                 callback=None, state='recieved',
                 replyRequired=True, reply=None):
        self.timestamp=time.time()
        self.source=source
        self.string=command_string
        self.callback=callback
        self.state=state
        self.replyRequired=replyRequired
        self.reply=reply
        self._lock=threading.Lock()
    
    def __str__(self):
        with self._lock:
            timestr=time.strftime('%X',time.localtime(self.timestamp))
            cmdstr=("%s@%s: '%s', %s." %
                (str(self.source), timestr, self.string, self.state))
            if self.state == 'complete':
                cmdstr+=" Reply: '%s'" % self.reply
        return escapeString(cmdstr)
    
    def setReply(self, *args):
        if len(args)==1:
            reply=args[0]
        else:
            reply=args[1]
        with self._lock:
            self.reply=reply
            self.state='complete'
