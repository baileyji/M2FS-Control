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
        return ("Command '%s' from %s. State: %s. Reply '%s'."%
                (self.string,str(self.source),self.state,self.reply))
                
                
    def setReply(self, reply):
        command.state='complete'
        command.reply=reply