import ConfigParser, os.path
from collections import defaultdict
import operator


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
    '0.2':['Plate','PlateHoles','Setup1'],
    '0.3':['Plate','PlateHoles','Setup1']}
REQUIRED_PLATE_KEYS = {
    '0.1':['formatversion', 'name'],
    '0.2':['formatversion', 'name'],
    '0.3':['formatversion', 'name']}
REQUIRED_SETUP_KEYS = {
    '0.1':['name'],
    '0.2':['name', 'utc',
           'sidereal_time',
           'el',
           'de',
           'epoch',
           'az',
           'telescope',
           'airmass',
           'ra']}
REQUIRED_SETUP_KEYS['0.3']=REQUIRED_SETUP_KEYS['0.2']

REQUIRED_SETUP_SUBSECTIONS= {
    '0.1':['Targets'],
    '0.2':['Targets','Guide'],
    '0.3':['Targets','Guide']}

STD_LEN={'x':8,'y':8,'z':8,'r':7,'type':5,'id':23, 'ra':12,'de':12,
         'ep':7,'slit':4,'priority':8}


ORDERED_FIBER_NAMES=['{}{}-{:02}'.format(color,cnum,fnum)
                     for color in 'RB'
                     for cnum in range(1,9)
                     for fnum in range(1,17)]

def _make_fmt_string(keys, lengths):
    l_strs=[('>' if l >0 else '<')+str(abs(l)) for l in lengths]
    fmt_segs=["{r["+keys[i]+"]:"+l_strs[i]+"}" for i in range(len(keys))]
    return ' '.join(fmt_segs)

def _make_extra_fmt_string(cols, recs):

    extra=[k.lower() for rec in recs for k in rec.keys()]
    extra=list(set(extra).difference(cols))
    if not extra:
        return ('',[])
    try:
        max_len=[max([ max(len(rec[k]), len(k)) for rec in recs if k in rec])
                 for k in extra]
        #[[ rec[k] for rec in recs if k in rec] for k in extra]
    except ValueError:
        import ipdb;ipdb.set_trace()
    l=sorted(zip(extra, max_len), key=operator.itemgetter(1))
    extra=[e for e, n in l]
    max_len=[n for e, n in l]
    fmt=_make_fmt_string(extra, max_len)
    return (fmt, extra)
2
def defdict(dic,default='-'):
    x=defaultdict(lambda:default)
    x.update(dic)
    return x

def _format_attrib_nicely(items):
    key_col_wid=max([len(k[1]) for k in items])+6
    
    items.sort(key=lambda x:x[0])
    
    ret=[]
    for k, v in items:
        spaces=' '*(key_col_wid-len(k)-1)
        ret.append("{k}={space}{v}\n".format(k=k, v=v, space=spaces))
    return ret

class PlateConfigParser(ConfigParser.RawConfigParser):
    def __init__(self, file, sections=None):
        """File is platefile name.
        Sections is optional and will be used to create a new plate file
        from the data and write it to file on the first call of write
        """

        #Platefiles may not have spaces in their filenames
        if ' ' in os.path.basename(file):
            raise InvalidPlate('Filenames may not have spaces\n')
        
        #Init the parser
        ConfigParser.RawConfigParser.__init__(self)
        #self.optionxform=str
        self.plate_filename=file
        
        if sections:
            self._load_from_data(sections)
        else:
        
            #Load the file
            with open(self.plate_filename,'r') as configFile:
                try:
                    self.readfp(configFile)
                except ConfigParser.ParsingError as e:
                    raise InvalidPlate(str(e)+'\n')
            if self.has_option('Plate','std_offset'):
                self.set('Plate','offset',self.get('Plate','std_offset'))
                self.remove_option('Plate','std_offset')

        #If errors abort
        #errs=self._vet()
        errs=[]
        if errs:
            raise InvalidPlate('\n'.join(errs))
    
    def _load_from_data(self,sections):
        """
        Sections is a dict with keys in REQUIRED_SECTIONS and with the 
        required setup subsections
        
        """
        #Define all the sections in the config file
        self.add_section('Plate')
        self.add_section('PlateHoles')
        for key in sections:
            if 'setup' in key.lower():
                section_key=key.replace(' ','')
                self.add_section(section_key)
                self.add_section(section_key+':Targets')
                self.add_section(section_key+':Guide')
                self.add_section(section_key+':Unused')
    
        #Plate section
        self._update_section('Plate',sections['plate'])
        self.set('Plate','formatversion','0.3')
        
        #Plate holes section
        self._init_plateholes(sections['plateholes'])
        
        #Setup Sections
        for s in (k for k in sections if 'setup' in k.lower()):
            cannonical_setup_name=s.replace(' ','')
            self._init_setup_section(cannonical_setup_name, sections[s])
    
    def _init_plateholes(self, dicts):
        """ take list of dicts with key value pairs 
        of 'x','y','z','r', & 'type' and add them as
        properly formatted strings to the plateHoles section
        """
        cols=['x','y','z','r','type']
        fmt=_make_fmt_string(cols, [STD_LEN[c] for c in cols])

        rec=[('H',fmt.format(r={c:c for c in cols}))]
        rec+=[("H{}".format(i+1), fmt.format(r=defdict(dic)))
              for i, dic in enumerate(dicts)]
        for r in rec:
            self.set('PlateHoles', *r)

    def _init_setup_section(self, setup_name, setup_dict):
        """ 
        setup_dict should be a dict of lists of dicts
        with keys Info, Targets, Guide, & optionally Unused
        
        missing data will be replaced with -
        """
        #Add setup info
        
        attrib=setup_dict['info'].copy()
        #preprocess az,el & ra,de
        try:
            attrib['(az,el)']="({}, {})".format(attrib.pop('AZ'),
                                                attrib.pop('EL'))
        except KeyError:
            pass
        try:
            attrib['(ra,de)']="({}, {})".format(attrib.pop('RA'),
                                                attrib.pop('DE'))
        except KeyError:
            pass
        
        self._update_section(setup_name, attrib) #TODO determine key case
        
        ###Add target section###
        
        #Base record
        cols=['id', 'ra','de','ep','slit','priority','type', 'x','y','z','r']
        fmt=_make_fmt_string(cols, [STD_LEN[c] for c in cols])
        
        #Extra columns
        extra_fmt,extra_cols=_make_extra_fmt_string(cols+['fiber'],
                                                    setup_dict['Targets'])
        
        fmt+=' '+extra_fmt
        
        #Create the records
        rec=[('H', fmt.format(r={c:c for c in cols+extra_cols}))] #header
        
        rec+=[(dic.pop('fiber'), fmt.format(r=defdict(dic)))
              for dic in setup_dict['Targets'] ]
        for r in rec:
            self.set(setup_name+':Targets', *r)

        ###Add guide section###
        
        #Base record
        cols=['ra','de','ep','type', 'x','y','z','r']
        fmt=_make_fmt_string(cols, [STD_LEN[c] for c in cols])
        
        #Extra columns
        extra_fmt,extra_cols=_make_extra_fmt_string(cols, setup_dict['Guide'])
        fmt+=' '+extra_fmt

        #Create the records
        rec=[('H',fmt.format(r={c:c for c in cols+extra_cols}))] #header

        rec+=[("G{}".format(i+1), fmt.format(r=defdict(dic)))
              for i,dic in enumerate(setup_dict['Guide'])]

        for r in rec:
            self.set(setup_name+':Guide', *r)
        
            
        ###Add Unused section###
        
        if 'Unused' in setup_dict:
        
            #Base record
            cols=['id', 'ra','de','ep','slit','priority','type', 'x','y','z','r']
            fmt=_make_fmt_string(cols, [STD_LEN[c] for c in cols])
            
            #Extra columns
            extra_fmt,extra_cols=_make_extra_fmt_string(cols, setup_dict['Unused'])
            fmt+=' '+extra_fmt

            #Create the records
            rec=[('H',fmt.format(r={c:c for c in cols+extra_cols}))] #header
            
            rec+=[("U{}".format(i+1), fmt.format(r=defdict(dic)))
                   for i,dic in enumerate(setup_dict['Unused'])]

            for r in rec:
                self.set(setup_name+':Unused', *r)

    def _update_section(self,section, d):
        for k,v in d.iteritems():
            self.set(section,str(k),str(v))
    
    def setup_sections(self):
        """Return setup section names only"""
        sec=[j for j in self.sections() if j[:5]=='Setup' and ':' not in j]
        return sorted(sec,key=lambda s: int(s[5:]))

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
        return self._extract_list_to_dictlist(setup_section+':Targets',
                                              keep_key_as='fiber')

    def _extract_list_to_dictlist(self,section, keep_key_as=None):
        """ get list of dicts with keys based on header row"""
        hrec=self.get(section,'H')
        recs=filter(lambda x: x[0]!='h', self.items(section))
        if not recs:
            return []
        if '\t' in hrec:
            tabquote=True
            keys=map(str.lower, _extract_tab_quote_list(hrec))
        else:
            tabquote=False
            keys=map(str.lower, hrec.split())
    
        if tabquote:
            extr_func=_extract_tab_quote_list
        else:
            extr_func=str.split

        if recs[0][0][0]=='t':
            keep_key_as=None  #TODO remove hack for v.1 fiber section with not needed

        ret=[]
        for k, rec in recs:
            vals=extr_func(rec)
            rdict={keys[i].lower():vals[i] for i in range(len(keys))}# if vals[i] !='-'}
            if keep_key_as:
                rdict[keep_key_as]=k.upper()
            ret.append(rdict)
        return ret

    def get_guides(self, setup_section):
        """Return list of target dictionaries for setup section"""
        if not self.has_section(setup_section+':Guide'):
            return []
        return self._extract_list_to_dictlist(setup_section+':Guide')
    
    def get_plate_holes(self):
        if not self.has_section('PlateHoles'):
            return []
        return self._extract_list_to_dictlist('PlateHoles')

    def setup_attrib(self,setup):
        """Get the setup attribute dict"""
        #Post process (ra,de) and (az,el) keys
        attrib=dict(self.items(setup))
        try:
            azel=attrib.pop('(az,el)').split(',')
            attrib['az']=azel[0].strip('() ')
            attrib['el']=azel[1].strip('() ')
        except KeyError:
            pass
        try:
            rade=attrib.pop('(ra,de)').split(',')
            attrib['ra']=rade[0].strip('() ')
            attrib['de']=rade[1].strip('() ')
        except KeyError:
            pass
        return attrib
    
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



    def write(self,file=None):
        if file:
            self.plate_filename=file
        #get list of crap for the plate
        with open(self.plate_filename,'w') as fp:
        
            #Write the [Plate] section
            fp.write("[Plate]\n")
            #fp.write("formatversion= 0.2\n")
            
            for r in _format_attrib_nicely(self.items('Plate')):
                fp.write(r)

            #Write out mechanical holes
            fp.write("[PlateHoles]\n")
            
            ph_fmt="{:<3}: {}\n"
            
            #Write header
            v=self.get('PlateHoles','H')
            fp.write(ph_fmt.format("H",v))
            
            for k, v in (r for r in self.items("PlateHoles") if r[0]!='h'):
                 fp.write(ph_fmt.format(k,v))
            
            #Write out setup sections
            for s in self.setup_sections():

                #Write out setup description section
                fp.write("[{}]\n".format(s))
                
                #Write out the setup attributes
                for r in _format_attrib_nicely(self.items(s)):
                     fp.write(r)
                
                #Write out setup targets section
                fp.write("[{}:Targets]\n".format(s))
                
                t_fmt="{:<6}: {}\n"
                
                #Write header
                v=self.get(s+':Targets','H')
                fp.write(t_fmt.format('H',v))
                
                #Write fiber
                recs=dict(self.items(s+':Targets'))
                for fiber in ORDERED_FIBER_NAMES:
                    fp.write(t_fmt.format(fiber,recs[fiber.lower()]))
                
                #Write out the Guide section
                fp.write("[{}:Guide]\n".format(s))
                
                g_fmt="{:<3}: {}\n"
                
                #Write header
                v=self.get(s+':Guide','H')
                fp.write(g_fmt.format('H',v))
                
                #Write guides
                for k, v in (r for r in self.items(s+':Guide') if r[0]!='h'):
                    fp.write(g_fmt.format(k,v))
                    

                if self.has_section("{}:Unused".format(s)):
                    #Write out the unused section
                    fp.write("[{}:Unused]\n".format(s))

                    u_fmt="{:<3}: {}\n"

                    #Write header
                    v=self.get(s+':Unused','H')
                    fp.write(u_fmt.format('H',v))

                    #Write unused
                    for k, v in (r for r in self.items(s+':Unused') if r[0]!='h'):
                        fp.write(u_fmt.format(k,v))


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
            self.standard_offset=plateConfig.get('Plate','offset')
        except IndexError:
            self.standard={}
            self.standard_offset=float('nan')
        
        self.setups={}
        for setup in plateConfig.setup_sections():
            attrib=plateConfig.setup_attrib(setup)
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
