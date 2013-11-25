import ConfigParser, os.path


def Plate(file):
    if file !=None:
        return PlugPlate(file)
    else:
        return NullPlate()


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


class Setup(object):
    """
    This is an M2FS plugplate setup.
    
    It has the attributes:
    name
    TODO
    """
    def __init__(self, setupAttributes, targetDictList, guideDictList):
        """
        setupAttributes must have name
        Target list:[header_record_str, (fiber_str_i, target_record_i), ...]
        """
        self.name=setupAttributes['name']
        self.attrib=setupAttributes.copy()
        self._target_list=targetDictList
        self._guide_list=guideDictList
        self.attrib['n']=self.n_fibers_used()
    
    def get_nominal_fiber_hole_dict(self):
        return {t['fiber']:t['id'] for t in self._target_list if t['id']}

    def n_fibers_used(self):
        return len([t for t in self._target_list if t['id']])


class NullSetup(object):
    def __init__(self):
        self.name='None'

    def get_nominal_fiber_hole_dict(self):
        return {}


class InvalidPlate(Exception):
    """
    Exception raised if a plate file is invalid in any way. str(exception) will
    give a \n delimited list of the various issues with the plate.
    """
    pass


def _extract_tab_quote_list(s):
    return [x[1:-1] for x in s.split('\t')]

def _extract_comma_list(s):
    return [x.strip(' \t\n\r') for x in s.split(',')]


REQUIRED_SECTIONS = {
    '0.1':['Plate', 'Setup1'],
    '0.2':['Plate','PlateHoles','Setup1']}
REQUIRED_PLATE_KEYS = {
    '0.1':['formatversion', 'name'],
    '0.2':['formatversion', 'name']}
REQUIRED_SETUP_KEYS = {
    '0.1':['name'],
    '0.2':['name',
           'utc',
           'sidereal_time',
           'el',
           'de',
           'epoch',
           'az',
           'telescope',
           'airmass',
           'ra']}
REQUIRED_SETUP_SUBSECTIONS= {
    '0.1':['Targets'],
    '0.2':['Targets','Guide']}


class PlateConfigParser(ConfigParser.RawConfigParser):
    def __init__(self,file, *args, **kwargs):
    
        #Platefiles may not have spaces in their filenames
        if ' ' in os.path.basename(file):
            raise InvalidPlate('Filenames may not have spaces\n')
        
        #Init the parser
        ConfigParser.RawConfigParser.__init__(self,*args,**kwargs)
        #self.optionxform=str
        self.plate_filename=file
        
        #Load the file
        with open(self.plate_filename,'r') as configFile:
            try:
                self.readfp(configFile)
            except ConfigParser.ParsingError as e:
                raise InvalidPlate(str(e)+'\n')
    
        #If errors abort
        errs=self._vet()
        if errs:
            raise InvalidPlate('\n'.join(errs))
    
    def setup_sections(self):
        """Return setup section names only"""
        return [j for j in self.sections() if j[:5]=='Setup' and ':' not in j]

    def target_sections(self):
        """Return setup target section names only"""
        return [j for j in self.sections() if j[:5]=='Setup' and ':Targets' in j]

    def guide_sections(self):
        """Return setup guide section names only"""
        return [j for j in self.sections() if j[:5]=='Setup' and ':Guide' in j]
    
    def setup_subsections(self):
        """Return setup subsection names"""
        return [j for j in self.sections() if j[:5]=='Setup' and ':' in j]
    
    def file_version(self):
        return self.get('Plate','formatversion')
    
    def get_targets(self, setup_section):
        """Return list of target dictionaries for setup section"""
        recs=self.items(setup_section+':Targets')
        
        keys=map(str.lower, _extract_tab_quote_list(recs.pop(0)[1]))
        
        ret=[]
        if self.file_version()=='0.1':
            for _, rec in recs:
                vals=_extract_tab_quote_list(rec)
                tdict={keys[i]:vals[i] for i in range(len(keys))}
                ret.append(tdict)
        else:
            for fiber, rec in recs:
                vals=_extract_tab_quote_list(rec)
                tdict={keys[i]:vals[i] for i in range(len(keys))}
                tdict['fiber']=fiber.upper()
                ret.append(tdict)
        return ret
    
    def get_guides(self, setup_section):
        """Return list of target dictionaries for setup section"""
        if self.file_version() == '0.1':
            return []
        
        recs=self.items(setup_section+':Guide')
        
        keys=map(str.lower, _extract_tab_quote_list(recs.pop(0)[1]))
        
        ret=[]
        for _, rec in recs:
            vals=_extract_tab_quote_list(rec)
            tdict={keys[i]:vals[i] for i in range(len(keys))}
            ret.append(tdict)
        return ret
    
    def get_plate_holes(self):
        if self.file_version() == '0.1':
            return []
        
        recs=self.items('PlateHoles')
        
        keys=map(str.lower, _extract_tab_quote_list(recs.pop(0)[1]))
        ret=[]
        for _, rec in recs:
            vals=_extract_tab_quote_list(rec)
            tdict={keys[i]:vals[i] for i in range(len(keys))}
            ret.append(tdict)
        return ret
        
    def setup_dict(self,setup):
        return dict(self.items(setup))
    
    def _vet(self):
        """return a list of format errors"""
        try:
            version=self.file_version()
        except ConfigParser.NoSectionError:
            return ["Must have [Plate] section."]
        except ConfigParser.NoOptionError:
            return ["[Plate] section must have keyword 'formatversion'."]
        
        errors=[]
        
        #Verify the file has all the required sections
        for section in REQUIRED_SECTIONS[version]:
            if not self.has_section(section):
                errors.append('Required section %s is missing' % section)
        
        #Verify plate section has correct keys
        for key in REQUIRED_PLATE_KEYS[version]:
            if not self.has_option('Plate',key):
                errors.append('Plate section missing key %s' % key)
    
        #Ensure all setup sections have the required subsections & keys
        for setup in self.setup_sections():
            #Subsections
            for subsec in REQUIRED_SETUP_SUBSECTIONS[version]:
                sec=':'.join([setup,subsec])
                if not self.has_section(sec):
                    errors.append(sec+' section is missing')
            #Keys
            for key in REQUIRED_SETUP_KEYS[version]:
                if not self.has_option(setup,key):
                    errors.append(setup+' section missing key '+key)

        #Ensure there is a setup section for every setup subsection
        for subsec in self.setup_subsections():
            setup,_,_=subsec.partition(':')
            if not self.has_section(setup):
                errors.append(setup+' section is missing')

        #Ensure setup names are unique
        setupNames=[]
        for setup in self.setup_sections():
            try:
                name=self.get(setup, 'name')
                if name in setupNames:
                    errors.append("Setup name '%' is not unique" % name)
                    setupNames.append(name)
            except ConfigParser.NoOptionError:
                pass
        
        #At this point we know all the basic data is there
        # The file isn't guarnateed valid yet, as there could still be invalid
        # data for a particular key
        
        #Validate the plate section data
        #TODO

        #Validate the setup sections data
        #TODO

        return errors


class NullPlate(object):
    """ This is a null plate """
    def __init__(self):
        self.n_setups=0
        self.name='NULL'
    
    def getSetup(self, setup):
        return NullSetup()


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
    def __init__(self, file):
        """
        Instatiate a new plate from file
        
        file must be a string file path.
        
        Plate file is vetted prior to loading. All errors found are returned as
        the description of the InvalidPlate exception which will be raised.
        Errors are /n seperated to ease dumping to a file with str(exception)
        """
        plateConfig=PlateConfigParser(file)
        self._plateConfig=plateConfig
        self.name=plateConfig.get('Plate', 'name')
        self.n_setups=len(plateConfig.setup_sections())
        self.plate_holes=plateConfig.get_plate_holes()
        self.file_version=plateConfig.file_version()
        if plateConfig.file_version() == '0.1':
            self.shackhartman=None
            self.mechanical=[]
        else:
            self.shackhartman=[x for x in self.plate_holes if x['type']=='C'][0]
            self.mechanical=[x for x in self.plate_holes if x['type'] in 'FT']
        try:
            self.standard=[x for x in self.plate_holes if x['type']=='O'][0]
            self.standard_offset=plateConfig.get('Plate','std_offset')
        except IndexError:
            self.standard={}
        
        self.setups={}
        for setup in plateConfig.setup_sections():
            attrib=plateConfig.setup_dict(setup)
            targets=plateConfig.get_targets(setup)
            guides=plateConfig.get_guides(setup)
            self.setups[attrib['name']]=Setup(attrib, targets, guides)
    
    def getSetup(self, setup):
        """
        Return the Setup or raise KeyError
        Returns a Setup object
        """
        return self.setups[setup]

    def listSetups(self):
        """ return a list of setup names """
        return self.setups.keys()
