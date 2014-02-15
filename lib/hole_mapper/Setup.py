'''
Created on Jan 19, 2010

@author: one
'''

class Setup(object):
    '''
    classdocs
    '''


    def __init__(self, plateName, setupName, channels=[]):
        '''
        Constructor
        '''
        self.name=setupName
        self.plateName=plateName
        self.guideHoles=set()
        self.groups=[]
        self.dict={}
        for c in channels:
            self.dict[c]=set()

    
    def __eq__(self, other):
        """ Returns true if both have the same channels
            and the channels are composed of the same holes."""
        
        
    def __contains__(self, hole):
        """ Returns true if hole is in the setup, 
            false otherwise."""
        for v in self.dict.itervalues():
            if hole in v:
                return True
        return False

    
    def getInfo(self):
        return (self.name, self.plateName)
        
        
    def addHole(self, hole, channel):
        """ Adds a hole to specified channel.
            A nonexistent channel is an exception.
            Attempting to add a hole to a channel when it is 
            already in the the setup in another channel is an exception."""
        if channel not in self.dict:
            raise Exception("Channel does not exist")
        
        x=self.dict.keys()
        x.remove(channel)
        for k in x:
            if hole in self.dict[k]:
                raise Exception('Hole exists in annother channel')
 
        self.dict[channel].add(hole)

    def getFiberForHole(self, hole):

        fiber='None'
        for group in self.groups:

            for i, h in enumerate(group['holes']):
                if h==hole:
                    fiber=group['fiber_group']
                    fiber=fiber[0:-2]+"%02i"%(int(fiber[-2:])+i)
                    break
            if fiber != 'None':
                break
        
        return fiber

        
    def addGuiderHole(self, hole):
        """ Adds a guider hole to the setup """
        self.guideHoles.add(hole)

    def getGuiderHoles(self):
        return self.guideHoles.copy()
        
    def addChannel(self, channel, holes=[]):
        """ Adds a channel to the setup, optionally
            initializing it with holes given as a sequence object
            to holes. 
            If channel exists no action is taken"""
        if channel not in self.dict:
            self.dict[channel]=set(holes)
            
    def createGroup(self, fiberBundle, holes, region, side, channel):

        if not set(holes).issubset(self.dict[channel]):
            raise Exception('Holes must all be in the setup and on the specified channel')
        self.groups.append({'fiber_group':fiberBundle, 'holes':holes,
                'region':region, 'side':side, 'path':[], 'channel':channel})
        
                
    def isHoleInChannel(self, hole, channel):
        """ Returns true if hole is in channel
            channel. False otherwise. 
            A nonexistent channel is an exception."""
        return hole in self.dict[channel]

    
    def delHole(self, hole):
        """ Removes a hole from the setup.
            If the hole is not part of the setup no action is taken"""
        for k in self.dict:
            self.dict[k].discard(hole)

    
    def getChannels(self):
        """ Returns a list of the channels which are
            in use for the setup."""
        return [x for x in self.dict.keys() if len(self.dict[x])]
    
    
    def getHolesInChannel(self, channel):
        """ Returns a set of holes in the specified channel,
            a nonexistent channel is an exception"""
        return self.dict[channel].copy()
    
    
    def getChannelOfHole(self, hole):
        """ Returns the channel of the hole.
            If hole is not in setup then an exception is raised."""
        for k,v in self.dict.iteritems():
            if hole in v:
                return k
        
        raise Exception('Hole not in setup')
            
    def isEmpty(self):
        """ Returns true if setup has no holes,
            false otherwise."""
        for k in self.dict.itervalues():
            if len(k):
                return False
        return True
    
    
    
    
        