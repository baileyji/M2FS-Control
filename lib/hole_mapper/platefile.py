class platefile:
    def __init__(self, file):
        self.file=file
        self.parseFile()

    def __eq__(self,other):
        return self.file==other.file

    def parseFile(self):
        pass

    def getSetup(self, setup):
        return self.setups[setup]

    def getnSetups(self):
        return len(self.setups)

    def getSetupNames(self):
        return self.setups.keys()
    
    def getLineNofSetup(self,n,setup):
        if len(self.setups[setup]['setup_lines']) > n:
            return self.setups[setup]['setup_lines'][n]
        else:
            return ''


class ascfile(platefile):
    """Loads and parses files with lines of format
      -1.1706  -4.7180  -0.2321   0.1735  O   B-01-01    B
      word[0:3] plate coords
      word[3] hole diameter
      word[4] object type
      word[5] oldFiber
      word[6:] additional info
    """
    def __init__(self, file):
        platefile.__init__(self, file)

    def parseFile(self):
        self.setups={}
        with open(self.file,"r") as fin:
            for line in fin:
                words=line.split()
                if words[0]=='Setup':
                    currsetup=words[0]+' '+words[1]
                    self.setups[currsetup]={'setup_nfo_str':[line],
                                            'setup_lines':[]}
                elif words[5][-2:]!='17':
                    self.setups[currsetup]['setup_lines'].append(line)
                else:
                    self.seventeen=line
        for s in self.setups:
            self.parseSetup(self.setups[s])

    def parseSetup(self,setup):
        setup['nAqusition']=0
        setup['nGuide']=0
        setup['nScience']=0
        for line in setup['setup_lines']:
            words=line.split()
            if (words[4] == 'O' or words[4]=='S'):
                #Line is for a science fiber
                setup['nScience']+=1
            elif words[4]=='G':
                #Line is for a guide fiber
                setup['nGuide']+=1
            elif words[4]=='A':
                #Line is for an acquisition star
                setup['nAqusition']+=1
            else:
                #Line is either F, T, or R, all are unused holes
                pass

    def getLineNumOfHole(self, hole, setup):
        return self.setups[setup]['setup_lines'].index(hole.idstr)
        
    def getLineOfHole(self, hole, setup):
        linenum=self.getLineNumOfHole(hole, setup)
        return self.getLineNofSetup(linenum, setup)

    def writeWithChannels(self, colorforlessthan129='B'):
        import os
        os.rename( self.file, self.file+"~")
        with open( self.file, "w" ) as fout:
            for s in sorted(self.setups.keys()):
                fout.write(self.setups[s]['setup_nfo_str'][0])
                if s == 'Setup 1':
                    fout.write(self.seventeen)
                if self.setups[s]['nScience'] < 129:
                    for i,l in enumerate(self.setups[s]['setup_lines']):
                        if i < self.setups[s]['nScience']:
                            fout.write(l[0:-1]+'    '+colorforlessthan129+'\n')
                        else:
                            fout.write(l)
                else:
                    for i,l in enumerate(self.setups[s]['setup_lines']):
                        if i < self.setups[s]['nScience']:
                            if i%2:
                                fout.write(l[0:-1]+'    B\n')
                            else:
                                fout.write(l[0:-1]+'    R\n')
                        else:
                            fout.write(l)
                            


class resfile(platefile):
    """Loads and parses files with lines of format
      B-01-01  01 08 10.42  -72 54 25.6  2000.0  O      F00-   806  I=19.64
      word[0] oldFiber
      word[1:8] sky coords
      word[8] object type
      word[9:] additional info
      """
    def __init__(self, file):
        platefile.__init__(self, file)

    def parseFile(self):
        self.setups={}
        with open(self.file,"r") as fin:
            i=0
            currsetup=1
            for line in fin:
                if i==0:
                    self.setups['Setup %d'%currsetup]={'setup_nfo_str':[line],
                                                      'setup_lines':[]}
                    i+=1
                elif i<3:
                    self.setups['Setup %d'%currsetup]['setup_nfo_str'].append(line)
                    i+=1
                else:
                    #is a hole line or end
                    words=line.split()
                    if words[0] == 'END':
                        i=0
                        currsetup+=1
                    else:
                        if words[0][-2:]!='17':
                            self.setups['Setup %d'%currsetup]['setup_lines'].append(line)

    def prune(self, lineid):
        pass


class plateHoleInfo:
    '''Frontend to the .res & .asc files of a setup
       used to retrieve information about a given hole'''
    def __init__(self,dir,platename):
        self.rfile=resfile(dir+platename.replace('Sum','plate')+'.res')
        self.afile=ascfile(dir+platename+'.asc')

    def getHoleInfo(self, setupName, hole):
        '''Returns a line containing info about the hole requested,
        lines are of the form:
        "<sky Coords RA/DEC>  <plate Coords>  <hole type>  <additional info from .res file>"
        if there are no sky coordinates for the hole (such as for guide reference holes)
        then the sky coordinate string will be '00 00 00.00   00 00 00.0  0000.0'
        '''
        try:
            linenum=self.afile.getLineNumOfHole(hole, setupName)
        except KeyError:
            return ''
        except ValueError:
            return ''
        aline=self.afile.getLineNofSetup(linenum, setupName)
        awords=aline.split()
        holetype=awords[4]
        platecoords=aline[4:38]
        
        rline=self.rfile.getLineNofSetup(linenum, setupName)
        if rline!='':
            rwords=rline.split()
            if holetype!=rwords[8]:
                raise LookupError('Hole types different in .rse & .asc')
            if rwords[0] !=awords[5]:
                raise LookupError('old fiber assignments differ in .rse & .asc')
            skycoords=rline[11:43]
            additnfo=rline[52:-1]
        else:
            skycoords='00 00 00.00   00 00 00.0  0000.0'
            additnfo=''

        return '  '.join([skycoords,platecoords,holetype,additnfo])
        
    def getSetupInfo(self, setup):
        '''Returns a list of lines about the setup requested,
        lines are from the .asc file are first, followed by lines 
        from the .res file'''
        setupNfo=self.afile.setups[setup]['setup_nfo_str']
        setupNfo.extend(self.rfile.setups[setup]['setup_nfo_str'])
        return setupNfo
