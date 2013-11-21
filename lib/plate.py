import ConfigParser, os.path

REQUIRED_SECTIONS = ['Plate', 'Setup1']
REQUIRED_PLATE_KEYS = ['name']
REQUIRED_SETUP_KEYS = ['name']


class CelestialObject(object):
    def __init__(self):
        self.names=['']
        self.ra=0.0
        self.dec=0.0
        self.equinox='J2000'
        self.mag=0.0
        self.magV=0.0

class Hole(object):
    """
    This class represents a hole drilled on a fiber plugplate
    
    Holes have x,y,z coordinates
    """
    def __init__(self, x, y, r, optional_tag=None):
        self.x=float(x)
        self.y=float(y)
        self.radius=float(r)
        self.tag=optional_tag
        self.ID=self.__hash__()
    
    def __hash__(self):
        return ( "%2.3f.%2.3f.%2.3f" % (self.x,self.y,self.radius) ).__hash__()
    
    def __eq__(self,other):
        return (self.x == other.x and
                self.y == other.y and
                self.radius == other.radius)

class Fiber(object):
    """
    An M2FS fiber. An object wrapper for the fiber name.
    
    Fibers are named, Fibers are equal if they have the same name.
    """
    def __init__(self, name):
        self.name=name
    
    def __eq__(self,other):
        return self.name == other.name

    def __str__(self):
        return self.name

def extract_tab_quote_list(s):
    return [x[1:-1] for x in s.split('\t')]

class Setup(object):
    """
    This is an M2FS plugplate setup.
    
    It has the attributes:
    name
    TODO
    """
    def __init__(self, name, setupAttributes, targetsDict):
        self.name=name
        self.attrib=setupAttributes
        self.tlist=[]
        keys=map(str.lower, extract_tab_quote_list(targetsDict.pop('H')))
        for k,v in targetsDict.iteritems():
            vals=extract_tab_quote_list(v)
            self.tlist.append({keys[i]:vals[i] for i in range(len(keys))})

        #self.plugPos=( (Fiber(), Hole()), (Fiber(), Hole()))
        #self.targets=(Hole(), CelestialObject(),(Hole(), CelestialObject()))
        #self.shobject=(Hole(), CelestialObject())
        #self.guideobjects=(Hole(), CelestialObject(),(Hole(), CelestialObject()))
        #self.acquisitionobjects=(Hole(), CelestialObject(),(Hole(), CelestialObject()))

class InvalidPlate(Exception):
    """
    Exception raised if a plate file is invalid in any way. str(exception) will
    give a \n delimited list of the various issues with the plate.
    """
    pass


def Plate(file):
    if file !=None:
        return PlugPlate(file)
    else:
        return NullPlate()

class NullPlate(object):
    """ This is a null plate """
    def __init__(self):
        self.n_setups=0
        self.name='NULL'
    
    def getSetup(self, setup):
        raise KeyError

class PlugPlate(object):
    """
    This is the M2FS plugplate class.
    
    Plates are real. Plates are metal. Each plate hase a number of holes
    drilled into it in which the M2FS fibers are plugged. Typically a plate 
    is drilled with many more holes than there are fibers and so only a 
    subset of the holes are populated for any given scientific observation.
    These groups of hole which are plugged together are referred to as Setups.
    Each setup has its own field center, shack hartman star, guide stars, etc. 
    
    There are four types of holes on a plate.
    1) Science fiber holes, which accept the M2FS fibers, are used for 
    the guider acquisition stars (with the small guide fibers), sky, and science
    targets. There may be more than 1000 of these holes on a plate.
    2) Guide fiber holes , which accept a spatially coherent imaging fiber 
    bundle. There are 1 or 2 per setup.
    3) Guide fiber locator holes. These are small diameter locating pin holes 
    used to orient the guide fibers.
    4) The central hole for the shack-hartman star. One per plate, does not get
    a fiber.

    A plate object has the following attributes:
    name - A string, the plate name.
    n_setups - The number of setups on the plate

    The file sample.plate describes the plate file file sturcture
    """
    @staticmethod
    def _vetPlateSection(plateConfig):
        """
        Verify all keys in the Plate section have the required type and content
        
        Return a list of strings describing any errors found or [].
        """
        return []
    
    @staticmethod
    def _vetSetups(plateConfig):
        """
        Verify all setup sections' data for type and and content
        
        Return a list of strings describing any errors found or [].
        """
        return []
    
    @staticmethod
    def _initFromFile(plate, file):
        """
        Instantiate a plate from its plate file
        
        Plate file is vetted prior to loading. All errors found are returned as 
        the description of the InvalidPlate exception which will be raised. 
        Errors are /n seperated to ease dumping to a file with str(exception)
        """
        plateConfig=ConfigParser.RawConfigParser()
        plateConfig.optionxform=str
        errors=[]
        #Platefiles may not have spaces in their filenames
        if ' ' in os.path.basename(file):
            raise InvalidPlate('Filenames may not have spaces\n')
        #Read in the plate file
        with open(file,'r') as configFile:
            try:
                plateConfig.readfp(configFile)
            except ConfigParser.ParsingError as e:
                errors.append(str(e))
        if errors:
            raise InvalidPlate('\n'.join(errors))
        #Monkey patch the plate config to support grabbing a list of all
        # setup sections with setup_sections() and target sections with
        # target_sections()
        import types
        ssFunc=(lambda x: [j for j in x.sections()
                           if j[:5]=='Setup' and ':' not in j])
        plateConfig.setup_sections=types.MethodType(ssFunc, plateConfig)
        tsFunc=(lambda x: [j for j in x.sections()
                           if j[:5]=='Setup' and ':' in j])
        plateConfig.target_sections=types.MethodType(tsFunc, plateConfig)
        #Verify the file has all the required sections
        for section in REQUIRED_SECTIONS:
            if not plateConfig.has_section(section):
                errors.append('Required section %s is missing' % section)
        #Verify the 'Plate' section has all the required keys
        for key in REQUIRED_PLATE_KEYS:
            if not plateConfig.has_option('Plate', key):
                errors.append('Required key %s missing from Plate section' % key)
        #Ensure all setup and setup:targets sections are paired
        for setup in plateConfig.setup_sections():
            target=setup+':Targets'
            if not plateConfig.has_section(target):
                errors.append('%s section is missing' % target)
        for target in plateConfig.target_sections():
            setup,junk,junk=target.partition(':')
            if not plateConfig.has_section(setup):
                errors.append('%s section is missing' % setup)
        #Ensure required keys are in each setup section and names are unique
        setupNames=[]
        for setup in plateConfig.setup_sections():
            #Verify all keys are there
            for key in REQUIRED_SETUP_KEYS:
                if not plateConfig.has_option(setup, key):
                    errors.append('Required key %s missing from %s' %
                                  (key, setup))
            #make sure name is unique
            if plateConfig.has_option(setup, 'name'):
                setupName=plateConfig.get(setup, 'name')
                if setupName in setupNames:
                    errors.append("Setup name '%' is not unique" % setupName)
                setupNames.append(setupName)
        #At this point we know all the basic data is there
        # The file isn't guarnateed valid yet, as there could still be invalid
        # data for a particular key
        #Validate the plate section data
        errors.extend(PlugPlate._vetPlateSection(plateConfig))
        #Validate the setup sections data
        errors.extend(PlugPlate._vetSetups(plateConfig))
        #Check for errors
        if errors:
            raise InvalidPlate('\n'.join(errors))
        #initialize the plate
        return PlugPlate._initFromVettedPlateConfig(plate, plateConfig)
    
    @staticmethod
    def _initFromVettedPlateConfig(plate, plateConfig):
        """
        Initialize the plate object with the plate data from the plate file
        TODO
        """
        plate.name=plateConfig.get('Plate', 'name')
        plate.setups={}
        plate.n_setups=len(plateConfig.setup_sections())
        for setup in plateConfig.setup_sections():
            setupAttributes=dict(plateConfig.items(setup))
            #import pdb;pdb.set_trace()
            targetsDict=dict(plateConfig.items(setup+':Targets'))
            plate.setups[setupAttributes['name']]=Setup(setupAttributes['name'],
                                      setupAttributes, targetsDict)
    
    def __init__(self, file):
        """
        Instatiate a new plate from file
        
        file must be a string file path.
        """
        PlugPlate._initFromFile(self, file)
    
    def getSetup(self, setup):
        """
        Return the Setup or raise KeyError
        Returns a Setup object
        """
        return self.setups[setup]

    def listSetups(self):
        """ return a list of setup names """
        return self.setups.keys()
