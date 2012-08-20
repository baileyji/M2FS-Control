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
        with open(file) as f:
            pass
        self.name=os.path.basename(file)
        self.file=file
        self.setups={}
        self.n_setups=len(self.setups)
        self.active_setup=None
        
        
        
