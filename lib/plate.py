import os
class Plate(object):
    """ M2FS Plate Class 
    
    Each plate has:
        name
        setups
        active_setup
        n_setups
    """
    def __init__(self, file):
        """
        Create a plate from file or default plate if no file
        
        If file is not a plate or DNE will throw exception.
        """
        if not file:
            self.name='None'
            self.file=None
            self.setups={}
            self.n_setups=0
            self.active_setup=''
        else:
            self.name=os.path.basename(file)
            self.file=file
            self.setups=self._loadSetups()
            self.n_setups=len(self.setups)
            self.active_setup=''
        
        
        
