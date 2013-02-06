import ConfigParser

REQUIRED_SECTIONS = ['Plate', 'Setup1']
REQUIRED_PLATE_KEYS = ['name']
REQUIRED_SETUP_KEYS = []


class NullPlate(object):
    """ This is a null plate """
    def __init__(self):
        self.setups={}
        self.name='NULL'
        

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
    def __init__(self, name):
        self.name=name
    
    def __eq__(self,other):
        return self.name == other.name


class Setup(object):
    def __init__(self, generalinfodict, targetstringlist):
        self.name=generalinfodict['name']
        #self.plugPos=( (Fiber(), Hole()), (Fiber(), Hole()))
        #self.targets=(Hole(), CelestialObject(),(Hole(), CelestialObject()))
        #self.shobject=(Hole(), CelestialObject())
        #self.guideobjects=(Hole(), CelestialObject(),(Hole(), CelestialObject()))
        #self.acquisitionobjects=(Hole(), CelestialObject(),(Hole(), CelestialObject()))


class CelestialObject(object):
    def __init__(self):
        self.names=['']
        self.ra=0.0
        self.dec=0.0
        self.equinox='J2000'
        self.mag=0.0
        self.magV=0.0


class InvalidPlate(Exception):
    """
    Exception raised if a plate file is invalid in any way. str(exception) will
    give a \n delimited list of the various issues with the plate.
    """
    pass

class Plate(object):
    """
    This is the M2FS plugplate class.
    
    Plates are real. Plates are metal.
    
    the file sample.plate describes the plate file file sturcture
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
        #Read in the plate file
        try:
            f=open(file,'r')
            plateConfig.readfp(f)
        except ConfigParser.ParsingError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(str(e))
        finally:
            f.close()
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
        #Ensure required keys are in each setup section
        for setup in plateConfig.setup_sections():
            for key in REQUIRED_SETUP_KEYS:
                if not plateConfig.has_option(setup, key):
                    errors.append('Required key %s missing from %s' %
                                  (key, setup))
        #At this point we know all the basic data is there
        # The file isn't guarnateed valid yet, as there could still be invalid
        # data for a particular key
        #Validate the plate section data
        errors.extend(Plate._vetPlateSection(plateConfig))
        #Validate the setup sections data
        errors.extend(Plate._vetSetups(plateConfig))
        #Check for errors
        if errors:
            raise InvalidPlate('\n'.join(errors))
        #initialize the plate
        return Plate._initFromVettedPlateConfig(plate, plateConfig)
    
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
            plate.setups[setup]=Setup(
                dict(plateConfig.items(setup)),
                dict(plateConfig.items(setup+':Targets')).values())
    
    def __init__(self, file):
        """
        Instatiate a new plate from file
        
        file must be a string file path.
        """
        Plate._initFromFile(self, file)

    def getSetup(self, setup):
        """
        Return the Setup or raise ValueError
        Returns a Setup object
        """
        return self.setups[setup]
