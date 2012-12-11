class Plate(object):

    @staticmethod
    def _initFromFile(plate, file):
        plate.name=None
        plate.file=file
        new_setup=None
        with open(file, "r") as f:
            try:
                for i, line in enumerate(f):
                    col=line.split()
                    if line[0]=='#':
                        continue
                    elif plate.name==None:
                        plate.name=col[0]
                        plate.n_setups=int(col[1])
                    elif col[0]=='setup':
                        if new_setup:
                            plate.setups[new_setup.name]=new_setup
                        new_setup=Setup()
                        new_setup.name=col[1]
                    else:
                        target=Target()
                        target.name=col[0]
                        target.hole=Hole(col[2:5])
                        target.kind=col[1]
                        target.desiredFiber=Fiber(col[10])
                        target.usedFiber=None
                        if target.kind=='SH'
                            new_setup.shobject.append(target)
                        elif target.kind=='G'
                            new_setuo.guideobjects.append(target)
                        else:
                            new_setup.targets.append(target)
            except IndexError:
                raise Exception('Bad file, line %i: "%s"' % (i, line) )
    
    def __init__(self, file):
        if not file:
            self.name='None'
            self.file=None
            self.setups=immutabledict()
            self.active_setup_name=''
            self.holes=immutableset()
        else:
            Plate._initFromFile(self, file)

class Hole(object):
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
    def __init__(self):
        self.name=''
        self.plugPos=( (Fiber(), Hole()), (Fiber(), Hole()), ...)
        self.targets=(Hole(), CelestialObject(),(Hole(), CelestialObject()),...)
        self.shobject=(Hole(), CelestialObject())
        self.guideobjects=(Hole(), CelestialObject(),(Hole(), CelestialObject()),...)
        self.acquisitionobjects=(Hole(), CelestialObject(),(Hole(), CelestialObject()),...)


class CelestialObject(object):
    def __init__(self):
        self.names=['']
        self.ra=0.0
        self.dec=0.0
        self.epoch='J2000'
        self.mag=0.0
        self.magV=0.0
        
        
