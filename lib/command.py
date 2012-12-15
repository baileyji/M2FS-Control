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
        string=("Command '%s' from %s. State: %s. Reply '%s'." %
                (self.string, str(self.source), self.state, self.reply))
        string=string.replace('\n','\\n').replace('\r','\\r')
        return string
    
    def setReply(self, *args):
        if len(args)==1:
            reply=args[0]
        else:
            reply=args[1]
        self.reply=reply
        self.state='complete'
