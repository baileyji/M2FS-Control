import Queue, threading

class IORequest(object):
    def __init__(self, target):
        self.response=None
        self.target=target
        self.attemptCount=0
        self.serviced=threading.Event()
        self.success=None

    def fail(self, reason='Unpsecified'):
        self.success=False
        self.response=str(reason)
        self.serviced.set()

    def succeed(self):
        self.success=True
        self.serviced.set()

class SendRequest(IORequest):
    def __init__(self, sendMessageBlockingArgs, *args, **kwards):
        super(SendRequest, self).__init__( *args, **kwards)
        self.sendArgs=sendMessageBlockingArgs

    def __str__(self):
        if self.success != None:
            state='Success' if self.success==True else 'Failed'
        else:
            state='Pending'
        serviced=( '' if self.serviced.isSet() else 'Not ') + 'Serviced'
        return "Send %s to %s. %s State: %s" % (self.sendArgs, self.target, serviced,state)

class ReceiveRequest(IORequest):
    def __init__(self, receiveMessageBlockingArgs, *args, **kwards):
        super(SendRequest, self).__init__( *args, **kwards)
        self.receiveArgs=receiveMessageBlockingArgs
    
    def respond(self, reply):
        self.response=str(response)
        self.succeed()
    
    def __str__(self):
        if self.success != None:
            state='Success' if self.success==True else 'Failed'
            state+=' '+self.response
        else:
            state='Pending'
        serviced=( '' if self.serviced.isSet() else 'Not ') + 'Serviced'
        return "Listen to %s (%s). %s State: %s" % (self.target, self.receiveArgs,  serviced,state)


class SendReceiveRequest(IORequest):
    def __init__(self, sendMessageBlockingArgs,
                 receiveMessageBlockingArgs,
                 *args, **kwargs):
        super(SendRequest, self).__init__( *args, **kwards)
        self.sendArgs=sendMessageBlockingArgs
        self.receiveArgs=receiveMessageBlockingArgs
    
    def respond(self, reply):
        self.response=str(response)
        self.succeed()
    
    def __str__(self):
        if self.success != None:
            state='Success' if self.success==True else 'Failed'
            state+=' '+self.response
        else:
            state='Pending'
        serviced=( '' if self.serviced.isSet() else 'Not ') + 'Serviced'
        return "Send %s to %s and listen (%s). %s State: %s" % (self.sendArgs, self.target, self.receiveArgs,  serviced, state)