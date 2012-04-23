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
                (str(self.source),self.string,self.state,self.reply))