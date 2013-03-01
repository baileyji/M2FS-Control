import Queue

def SendRequest(IORequest):
    def __init__(self, sendMessageBlockingArgs, *args, **kwards):
        super(SendRequest, self).__init__( *args, **kwards)
        self.sendArgs=sendMessageBlockingArgs

def ReceiveRequest(IORequest):
    def __init__(self, receiveMessageBlockingArgs, *args, **kwards):
        super(SendRequest, self).__init__( *args, **kwards)
        self.receiveArgs=receiveMessageBlockingArgs

def SendReceiveRequest(IORequest):
    def __init__(self, sendMessageBlockingArgs,
                       receiveMessageBlockingArgs,
                       *args, **kwargs):
        super(SendRequest, self).__init__( *args, **kwards)
        self.sendArgs=sendMessageBlockingArgs
        self.receiveArgs=receiveMessageBlockingArgs

def IORequest(object):
    def __init__(self, target, responseQueue=Queue.Queue()):
        self.responseQueue=responseQueue
        self.target=target
        self.attemptCount=0
        self.serviced=Threading.Event()

    def fail(self, reason='Unpsecified'):
        if self.responseQueue!=None:
            self.responseQueue.put(reason)
        self.success=False
        self.serviced.set()
    
    def respond(self, reply):
        if self.responseQueue!=None:
            self.responseQueue.put(response)
        self.succeed()

    def succeed(self):
        self.success=True
        self.serviced.set()
