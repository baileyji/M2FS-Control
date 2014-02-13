class Obj:
    def __init__(self):
        self.callback=None

class Command:
    def __init__(self, source, string,
                 args=None, callback=None, state='recieved',
                 replyRequired=True, reply=None):
        self.source=source
        self.string=string
        self.args=args
        self.callback=callback
        self.state=state
        self.replyRequired=replyRequired
        self.reply=reply

c=Command('1','boo')

obj=Obj()

def f(command):

    def callback(msg):
        command.reply=msg
        command.state='callback called'
    obj.callback=callback