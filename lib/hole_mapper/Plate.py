'''
Created on Dec 12, 2009

@author: one
'''
from Hole import *
import ImageCanvas
import os.path
import platefile
class Plate(object):
    '''Class for fiber plug plate'''
    FIBER_BUNDLES={
        'armB':( ('B-02-09','B-02-01','B-04-09','B-04-01',
                  'B-06-09','B-06-01','B-08-09','B-08-01'),
                 ('B-01-01','B-01-09','B-03-01','B-03-09',
                  'B-05-01','B-05-09','B-07-01','B-07-09') ),
        'armR':( ('R-02-09','R-02-01','R-04-09','R-04-01',
                  'R-06-09','R-06-01','R-08-09','R-08-01'),
                 ('R-01-01','R-01-09','R-03-01','R-03-09',
                  'R-05-01','R-05-09','R-07-01','R-07-09') )}
    LABEL_ANGLE_MULT={
        '02-09':-2.5, '02-01':-3,
        '04-09':-3.5, '04-01':-4,
        '06-09':-4.5, '06-01':-5,
        '08-09':-5.5, '08-01':-6,
        '01-01': 2.5, '01-09': 3,
        '03-01': 3.5, '03-09': 4,
        '05-01': 4.5, '05-09': 5,
        '07-01': 5.5, '07-09': 6}
    RED_VS_BLUE_MULT_OFFSET=.25
    SCALE=14.25
    RADIUS=1.0 # 14.25/Plate.SCALE
    LABEL_INC=20.0 # deg between cassette labels (180/(numcassperchannel+2))
    LABEL_RADIUS=0.85*RADIUS
    SH_RADIUS=0.1875
    HOLE_R_MULT=1.25


    def __init__(self):
        #self.h=0.4039727532995173
        #x1,y1 = 0.4863742535097986, 0.19906175954231559
        #x2,y2 = 0.36245210964697655, 0.6497646036144594
        self.holeSet=set()
        self.setups={}
        self.plate_name=''
        self.doCoordShift=True
        self.coordShift_D=64.0
        self.coordShift_R=50.68
        self.coordShift_rm=13.21875
        self.coordShift_a=0.03

    def getHole(self, holeID):
        for h in self.holeSet:
            if h.hash == long(holeID):
                return h
        return None

    def getSetupsUsingHole(self, hole):
        ret=[]
        for k in self.setups:
            v=self.setups[k]
            if hole in v['unused_holes']:
                ret.append(k)
            else:
                for chan in v['channels']:
                    if hole in v['channels'][chan]:
                        ret.append(k)
                        break
        return ret


    def getHoleInfo(self, holeID):
        """ Returns a dictionary of information for hole
            corresponding to holeID. Valid keys are:'RA',
            'DEC','GALAXYID','MAGNITUDE','COLOR','SETUPS',
            'HOLEID', and 'TYPE'.
            An invalid holeID is an exception."""
        
        hole=self.getHole(holeID)
        if not hole:
            raise Exception('Invalid holeID')
        
        ret={'RA':hole['RA'],'DEC':hole['DEC'],
             'GALAXYID':hole['GALAXYID'],'MAGNITUDE':hole['MAGNITUDE'],
             'COLOR':hole['COLOR'],'TYPE':hole['TYPE'],
             'SETUPS':self.getSetupsUsingHole(hole),'HOLEID':holeID,
             'IDSTR':hole.idstr}

        return ret


    def getChannelForHole(self, holeID, setupName):
        """ Returns the channel of a hole for a given setup.
            Returns '' for Holes without a channel. An invalid
            setup is an exception. An invalid holeID is an exception."""
            #A holeID not in the specified setup is an exception. 
        
        hole=self.getHole(holeID)
        if not hole:
            raise Exception('Invalid holeID')
        if setupName not in self.setups:
            raise Exception('Invalid setupName')
        
        ret=None
        for k in self.setups[setupName]['channels']:
            v=self.setups[setupName]['channels'][k]
            if hole in v:
                ret=k
                break
        
        if ret is None:
            if hole in self.setups[setupName]['unused_holes']:
                ret=''
                
        if ret is None:
            ret=''
            #raise Exception('Hole not in specified setup')
        
        return ret
    

    def getFiberForHole(self, holeID, setupName):
        """ Returns the Fiber which is mapped to a 
            specified holeID. "None" is returned if
            there is no mapping. A nonexistent setup
            is an exception, as is an invalid holeID """

        fiber='None'
        hole=self.getHole(holeID)
        if not hole:
            raise Exception('Invalid holeID')
        if setupName not in self.setups:
            raise Exception('Invalid setupName')
        
        groups=self.setups[setupName]['groups'] #is a list of dictionaries
        for g in groups:
            for i, h in enumerate(g['holes']):
                if h==hole:
                    fiber=g['fiber_group']
                    fiber=fiber[0:-2]+"%02i"%(int(fiber[-2:])+i)
                    break
            if fiber != 'None':
                break
        return fiber


    def getSetupInfo(self,setupName):
        nr=0
        nb=0
        nt=len(self.holeSet)-len(self.getHolesNotInAnySetup())
        for s in self.setups:
            nt-=len(self.setups[s]['unused_holes'])

        if setupName in self.setups:
            if 'armR' in self.setups[setupName]['channels']:
                nr=len(self.setups[setupName]['channels']['armR'])
            if 'armB' in self.setups[setupName]['channels']:
                nb=len(self.setups[setupName]['channels']['armB'])
        return 'Red: %03d  Blue: %03d  Total: %04d'%(nr,nb,nt)

    def getHolesNotInAnySetup(self):
        otherholes=[]
        #gather all the holes not in any setup
        for h in self.holeSet:
            flag=1
            for s in self.setups:
                if h in self.setups[s]['unused_holes']:
                    flag=0
                if flag:
                    for k in self.setups[s]['channels']:
                        if h in self.setups[s]['channels'][k]:
                            flag=0
                            break
                if flag == 0:
                    break
            if flag:
                otherholes.append(h)
        return otherholes
    
    def addHole(self, xin, yin, r, setup='', channel='', info=''):
        """Used to manually add a hole to the plate.
           If setup doesn't exist it will be created"""
        
        hole=Hole(xin/Plate.SCALE, yin/Plate.SCALE, r/Plate.SCALE, idstr=info)
        
        holeinfostr=self.plateHoleInfo.getHoleInfo(setup, hole)
        if holeinfostr:
            #print holeinfostr
            holeinfostr=holeinfostr.split()
            #"<sky Coords>  <plate Coords>  <hole type>  <additional info from .res file>"
            ra=tuple(map(float,holeinfostr[0:3]))
            dec=tuple(map(float,holeinfostr[3:6]))
            type=holeinfostr[11]
            hole['RA']=ra
            hole['DEC']=dec
            hole['TYPE']=type
        
        if hole in self.holeSet:
            for h in self.holeSet:
                if h.hash==hole.hash:
                    hole=h
                    break
        
        self.holeSet.add(hole)

        if setup:
            setupName=setup
            if setupName not in self.setups:
                self.setups[setupName]=self.initializeSetup(setupName)
        
            if channel:
                if channel in self.setups[setupName]['channels']:
                    self.setups[setupName]['channels'][channel].append(hole)
                else:
                    self.setups[setupName]['channels'][channel]=[hole]
            else:
                self.setups[setupName]['unused_holes'].append(hole)
            

    def initializeSetup(self, setupName):
        """Initializes a setup dictionary with name 
           setupName"""
        #if setupName is not of the form "Setup #" raise an exception
        
        setup={'plate':self.plate_name, 
               'setup':setupName,
               'unused_holes':[],
               'channels':{},
               'groups':[]}
        return setup
    
    @staticmethod
    def initializeGroup( fiberBundle, holes, region, side, channel):
        return {'fiber_group':fiberBundle, 
                'holes':holes,
                'region':region,
                'side':side, 
                'path':[],
                'channel':channel}

    def loadHoles(self,file):
        ''' Routine to load holes from a file 

        File should have all the holes on the plate
        separated into groups specifying the setup number.
        valid lines are of format x y z diam type arbit_fiber channel'''

        self.clear()


        
        self.plate_name=os.path.basename(file)[0:-4]
        plate_name=self.plate_name
        self.plateHoleInfo=platefile.plateHoleInfo(os.path.dirname(file)+
                                                   os.path.sep, plate_name)
        curr_setup=''
        
        #Add the SH to the global set
        self.addHole(0.0, 0.0, Plate.SH_RADIUS, info='Shack-Hartman')
        
        
        with open(file,'r') as f:

            for line in f:
                words=line.split()
                #If line specifies a setup see if we have already 
                # loaded holes if so we need store the last setup
                if words[0]=='Setup':
                    if curr_setup:
                        keep=False
                        for c in self.setups[curr_setup]['channels']:
                            if self.setups[curr_setup]['channels'][c]!=[]:
                                keep=True
                                break
                        if not keep:
                            self.setups.pop(curr_setup)
                            
                    curr_setup='Setup '+words[1]
                    self.setups[curr_setup]=self.initializeSetup(curr_setup)
                    
                else:
                    x,y,d=map(float,[words[0],words[1],words[3]])
                    if line[-3:-1]=='17':
                        self.addHole(x, y, d/2.0, info=line)
                        
                    elif words[-3] in ('O','S'):
                        channel='arm'+words[-1]
                        self.addHole(x, y, d/2.0, setup=curr_setup, 
                                     channel=channel, info=line)
                        
                    else:
                        self.addHole(x, y, d/2.0, setup=curr_setup, info=line)



  
    def clear(self):
        self.setups={}
        self.holeSet=set()

    def findPath(self, holeList, plateSide ):
        if plateSide == 'left':
            #we are going left to right
            holeList.sort(lambda a,b: -cmp(a.x,b.x))
        else:
            #we are going right to left to
            holeList.sort(lambda a,b: cmp(a.x,b.x))

        #The path starts at the first hole
        path=[]
        if len(holeList) == 1:
            path.append([holeList[0].position()])
        for i in range(len(holeList)-1):
        #   path.append(self.determineRoute(holeList[i],holeList[i+1]))
            path.append([holeList[i].position(),holeList[i+1].position()])
        
        return path


    def regionify(self, active_setup='Setup 1'):
        initRegion=(-Plate.RADIUS,-Plate.RADIUS,Plate.RADIUS,Plate.RADIUS)

        if active_setup in self.setups:
            self.setups[active_setup]['groups']=[]
            for c in self.setups[active_setup]['channels']:
    
                holes=[]
                for h in self.setups[active_setup]['channels'][c]:
                    if h.inRegion(initRegion):
                        holes.append(h)
    
                #Break the holes on the channel into desired groups of 8 or less
                regions=Plate.divideRegion((holes,initRegion))
    
                #Associate these regions with groups of fibers
                self.setups[active_setup]['groups'].extend(
                    Plate.regions2groups(c,regions))
    
                #Create a path for the holes
                for g in self.setups[active_setup]['groups']:
                    g['path']=self.findPath(g['holes'],g['side'])
            

    def writeMapFile(self, out_dir, active_setup):
        if active_setup in self.setups:
            ofile=''.join([out_dir,self.plate_name,'_',active_setup,'.map'])
            with open( ofile, "w" ) as fout:
                fout.write(''.join(['Code Version: Feb 10\n',self.plate_name,'\n']))
                setup_nfo=self.plateHoleInfo.getSetupInfo(active_setup)
                for l in setup_nfo:
                    fout.write(l)
                for g in self.setups[active_setup]['groups']:
                    base_fiber_name=g['fiber_group'][0:5]
                    base_fiber_num=int(g['fiber_group'][5:])
                    for i,h in enumerate(g['holes']):
                        fiber=base_fiber_name+'%02d'%(i+base_fiber_num)
                        nfostr=self.plateHoleInfo.getHoleInfo(active_setup, h)
                        fout.write(''.join([fiber,'  ',nfostr,'\n']))



    def toggleCoordShift(self):
        self.doCoordShift = not self.doCoordShift
        return self.doCoordShift


    @staticmethod
    def divideRegion(region):
        tmpr=Plate.splitRegionHorizontally( region )
        
        if len(tmpr)==1:
            regions=Plate.splitRegionVertically( tmpr[0] )
        else:
            regions=Plate.divideRegion( tmpr[0])
            subregions2=Plate.divideRegion( tmpr[1])
            regions[len(regions):]=subregions2
            
        return regions

                     
    @staticmethod
    def splitRegionVertically( (holes, (x0,y0,x1,y1)), nminr=8):
        if len(holes) <= nminr:
            regions=[(holes,(x0,y0,x1,y1))]
        else:
            holes=sorted(holes, Hole.holeCompareX)
            nr2=nminr*(len(holes)/nminr/2)+len(holes)%nminr
            splitx=(holes[-nr2-1].x+holes[-nr2].x)/2.0
            regions=[(holes[0:-nr2],(x0,y0,splitx,y1)),
                     (holes[-nr2:],(splitx,y0,x1,y1))]
        return regions


    @staticmethod
    def splitRegionHorizontally((holes, (x0,y0,x1,y1)), nminr=16):
        if len(holes) <= nminr:
            regions=[(holes,(x0,y0,x1,y1))]
        else:
            #sort holes by y position increasing
            holes=sorted(holes, Hole.holeCompareY)
            #num holes in second group: nr2
            nr2=nminr*(len(holes)/nminr/2)+len(holes)%nminr
            #holes in first group: 0:-nr2
            splity=(holes[-nr2-1].y+holes[-nr2].y)/2.0
            regions=[(holes[0:-nr2],(x0,y0,x1,splity)),
                     (holes[-nr2:],(x0,splity,x1,y1))]
        return regions


    @staticmethod
    def regions2groups(channel, regions):
        #Associate these regions with groups of fibers
        #break regions into left and right sides and sort them vertically
        groups=[]
    
        #First figure out which regions are to be associated with left fibers
        # and which with right side fibers
        # Compute CoM of holes in each region, of those on the left, the 8 
        # leftmost go to the left. Of those on the right, the 8 right most go right.
        # any leftover on either side go on the other side.
    
        regionxctr=[math.fsum([h.x for h in r[0]])/float(len(r[0])) for r in regions]
        num_left=sum([a > 0.0 for a in regionxctr])
        num_right=len(regions)-num_left
    
        #Sort the regions from leftmost to rightmost
        regions.sort(key=lambda r:math.fsum([h.x for h in r[0]])/float(len(r[0])),reverse=True)
    
        #Place first min(8, num regions on left + max(0, num regions on right - 8))
        # regions on the left, the remainder on the right
        num_left = min(8, num_left) + max(0, num_right - 8)
    
        left=regions[0:num_left]
        right=regions[num_left:]
  

        left.sort(lambda a,b: -cmp(a[1][1]+a[1][3],b[1][1]+b[1][3]))
        right.sort(lambda a,b: -cmp(a[1][1]+a[1][3],b[1][1]+b[1][3]))

        #Do the left and right sides of the plate separately
            #Now the groups are sorted vertically
            # so if there are as many of them as there are cassettes
            # we can just assign them in order
            # If there are fewer than the number of cassettes we would like 
            # to associate them with a cassette at roughly the same level
            #while there are unassociated groups
            #    if number of free cassettes is equal to number of 
            #        unassigned groups
            #        pair them off
            #    else
            #        determine the nearest unassociated cassette which leaves
            #        enough cassetts for the remaining groups and 
            #        associate it with the first group
        
        nextbundle=0
        numbundles=len(Plate.FIBER_BUNDLES[channel][0])
        while len(left):
            assert len(left) <= numbundles-nextbundle
            if len(left) ==  numbundles-nextbundle:
                for g in left:
                    groups.append(Plate.initializeGroup( 
                                    Plate.FIBER_BUNDLES[channel][0][nextbundle], 
                                    g[0], g[1], 'left', channel))
                    nextbundle+=1
                break
            else:
                #get the y position of the hole with the least x value
                groupy=max(left[0][0],key=lambda a:a.x).y
                angleoffvert=math.degrees(math.pi/2 - 
                                math.asin(groupy/Plate.LABEL_RADIUS))
                tmp=max(angleoffvert/Plate.LABEL_INC-1,0)
                
                bundlenum = min(round(tmp), numbundles-len(left) )
                bundlenum = int(max(bundlenum, nextbundle))
                
                groups.append(Plate.initializeGroup( 
                                Plate.FIBER_BUNDLES[channel][0][bundlenum], 
                                left[0][0], left[0][1], 'left', channel))
                
                nextbundle=bundlenum+1

                left.pop(0)
        
        #Now do the same thing for the right side
        nextbundle=0
        numbundles=len(Plate.FIBER_BUNDLES[channel][1])
        while len(right):
            assert len(right) <= numbundles-nextbundle
            if len(right) == numbundles-nextbundle:
                for g in right[:]:
                    groups.append(Plate.initializeGroup( 
                                    Plate.FIBER_BUNDLES[channel][1][nextbundle], 
                                    g[0], g[1], 'right', channel))
                    nextbundle+=1
                break
            else:
                #get the y position of the hole with the largest x value
                groupy=min(right[0][0],key=lambda a:a.x).y
                angleoffvert=math.degrees(math.pi/2 - 
                                math.asin(groupy/Plate.LABEL_RADIUS))

                tmp=(angleoffvert-Plate.LABEL_INC)/Plate.LABEL_INC
                
                bundlenum = min(round(tmp), numbundles-len(right) )
                bundlenum = int(max(bundlenum, nextbundle))

                groups.append(Plate.initializeGroup( 
                                Plate.FIBER_BUNDLES[channel][1][bundlenum], 
                                right[0][0], right[0][1], 'right', channel))
                
                nextbundle=bundlenum+1
                right.pop(0)

        return groups


    def drawHole(self, hole, canvas, color=None, fcolor='White', radmult=1.0, drawimage=0):
       
        
        pos=self.plateCoordShift(hole.position())
            
        hashtag=".%i"%hole.hash
        if drawimage:
                canvas.drawCircle( pos, hole.radius*radmult, outline=color, fill=fcolor)
        else:
            if canvas.find_withtag(hashtag):
                tmp=list(pos)
                tmp.append(hole.hash)
                print tmp
                print "drawing dupe in Dark Green @ (%f,%f) ID:%i"%tuple(tmp)
                fcolor='DarkGreen'
            canvas.drawCircle( pos, hole.radius*radmult, 
                               outline=color, fill=fcolor, tags=('hole',hashtag),
                               activefill='Green',activeoutline='Green',
                               disabledfill='Orange',disabledoutline='Orange')


    def plateCoordShift(self, (xin, yin), force=False):
        """ Shifts x and y to their new positions in scaled space,
            if self.doCoordShift is True or force is set to True.
            out=in otherwise"""
        if (not self.doCoordShift and
            not force or (xin==0.0 and yin==0.0)):
            return (xin,yin)
        else:
            D=self.coordShift_D
            a=self.coordShift_a
            R=self.coordShift_R
            rm=self.coordShift_rm
            
            x=xin*Plate.SCALE
            y=yin*Plate.SCALE
            r=math.hypot(x, y)
            #psi = angle clockwise from vertical
            #psi=90.0 - math.atan2(y,x)
            cpsi=y/r
            spsi=x/r
            d=math.sqrt(R**2 - r**2) - math.sqrt(R**2 - rm**2)
            dr=d*r/(D+d)
            
            rp=(r-dr)*(1.0+a*cpsi)
            xp=rp*spsi
            yp=rp*cpsi
            return (xp/Plate.SCALE, yp/Plate.SCALE)


    def draw(self, canvas, active_setup=None, channel='all'):

        #Make a circle of appropriate size in the window
        canvas.drawCircle( (0,0) , Plate.RADIUS)
        
        if active_setup and active_setup in self.setups:
            #the active setup
            setup=self.setups[active_setup]

            inactiveHoles=self.holeSet.difference(setup['unused_holes'])
            for key in setup['channels']:
                inactiveHoles.difference_update(setup['channels'][key])
    
            #Draw the holes that aren't in the current setup
            for h in inactiveHoles:
                self.drawHole(h, canvas)

            #If holes in setup have been grouped then draw the groups
            # otherwise draw them according to their channel
            if setup['groups']:
                self.drawGroup(setup['groups'],canvas,channel=channel)
            else:
                if channel=='all':
                    for c in setup['channels']:
                        if c=='armB':
                            for h in setup['channels'][c]:
                                self.drawHole(h, canvas, color='Blue')
                        else:
                            for h in setup['channels'][c]:
                                self.drawHole(h, canvas, color='Red')
                                
                elif channel=='armR' or channel.upper()=='RED':
                    if 'armB' in setup['channels']:
                        for h in setup['channels']['armB']:
                            self.drawHole(h, canvas)
                    if 'armR' in setup['channels']:
                        for h in setup['channels']['armR']:
                            self.drawHole(h, canvas, color='Red')
                elif channel=='armB' or channel.upper()=='BLUE':
                    if 'armR' in setup['channels']:
                        for h in setup['channels']['armR']:
                            self.drawHole(h, canvas)
                    if 'armB' in setup['channels']:
                        for h in setup['channels']['armB']:
                            self.drawHole(h, canvas, color='Blue')

            #Draw the guide and acquisition holes in color
            for h in setup['unused_holes']:
                self.drawHole(h, canvas, color='Green')
    
        else:
            for h in self.holeSet:
                self.drawHole(h, canvas)

        
    def drawImage(self, canvas, active_setup=None, channel='all',radmult=1.25):
        if active_setup and active_setup in self.setups:
            #the active setup
            setup=self.setups[active_setup]

            #Draw the plate name and active setup
            canvas.drawText((0,.7), self.plate_name ,color='White',center=0)
            canvas.drawText((0,.65), active_setup, color='White',center=0)
    

    
            #If holes in setup have been grouped then draw the groups
            # otherwise draw them according to their channel
            if setup['groups']:
                self.drawGroup(setup['groups'],canvas,channel=channel,drawimage=1)
            else:
                if channel=='all':
                    for c in setup['channels']:
                        if c=='armB':
                            for h in setup['channels'][c]:
                                self.drawHole(h, canvas,color='Blue',fcolor='Blue',radmult=radmult,drawimage=1)
                        else:
                            for h in setup['channels'][c]:
                                self.drawHole(h, canvas,color='Red',fcolor='Red',radmult=radmult,drawimage=1)
                elif channel=='armR' or channel.upper()=='RED':
                    if 'armB' in setup['channels']:
                        for h in setup['channels']['armB']:
                            self.drawHole(h, canvas,drawimage=1)
                    if 'armR' in setup['channels']:
                        for h in setup['channels']['armR']:
                            self.drawHole(h, canvas,color='Red',fcolor='Red',radmult=radmult,drawimage=1)
                elif channel=='armB' or channel.upper()=='BLUE':
                    if 'armR' in setup['channels']:
                        for h in setup['channels']['armR']:
                            self.drawHole(h, canvas,drawimage=1)
                    if 'armB' in setup['channels']:
                        for h in setup['channels']['armB']:
                            self.drawHole(h, canvas,color='Blue',fcolor='Blue',radmult=radmult,drawimage=1)
                    
            #Draw the guide and acquisition holes in color
            for h in setup['unused_holes']:
                self.drawHole(h, canvas,color='Yellow',fcolor='Yellow',radmult=radmult,drawimage=1)
    
            for h in self.getHolesNotInAnySetup():
                self.drawHole(h, canvas,color='Magenta',fcolor='Magenta',radmult=radmult,drawimage=1)

            #Draw little white dots where all the other holes are
            inactiveHoles=self.holeSet.difference(setup['unused_holes'])
            for key in setup['channels']:
                if channel==key or channel=='all':
                    inactiveHoles.difference_update(setup['channels'][key])
            for h in inactiveHoles:
                pos=self.plateCoordShift(h.position())    
                #canvas.drawCircle(pos, h.radius/3 ,fill='White',outline='White')
                canvas.drawSquare(pos,h.radius/3,fill='White',outline='White')
                
            #for h in self.holeSet:
            #    pos=self.plateCoordShift(h.position())    
            #    canvas.drawCircle(pos, h.radius/3 ,fill='White',outline='White')


    def drawGroup(self, holeGroup, canvas,radmult=1.0,channel='all',drawimage=0):    
        if channel=='all':
            channeltoshow=['armB','armR']
        elif channel=='armR' or channel.upper()=='RED':
            channeltoshow=['armR']
        elif channel=='armB' or channel.upper()=='BLUE':
            channeltoshow=['armB']
        else:
            channeltoshow=[]

        for i,g in enumerate(holeGroup):
            if g['channel'] in channeltoshow:
                if g['channel'] =='armB':
                    color='Blue'
                else:
                    color='Red'
                
                #Draw a rectangle around the group
                #mycanvas.drawRectangle(g['region'],outline=col)


                pluscrosscolor='Lime'
                #Draw an x across the first hole
                radius=2*0.08675*radmult/Plate.SCALE
                x,y=g['path'][0][0][0],g['path'][0][0][1]
                x,y=self.plateCoordShift(g['path'][0][0])
                canvas.drawLine((x-radius,y+radius),(x+radius,y-radius), fill=pluscrosscolor)
                canvas.drawLine((x-radius,y-radius),(x+radius,y+radius), fill=pluscrosscolor)
        
                #Draw a + over the last hole
                radius*=1.41
                x,y=g['path'][-1][-1][0],g['path'][-1][-1][1]
                x,y=self.plateCoordShift(g['path'][-1][-1])
                canvas.drawLine((x-radius,y),(x+radius,y), fill=pluscrosscolor)
                canvas.drawLine((x,y-radius),(x,y+radius), fill=pluscrosscolor)
                #canvas.drawLine(map(round,(x-radius,y)),map(round,(x+radius,y)), fill=pluscrosscolor)
                #canvas.drawLine(map(round,(x,y-radius)),map(round,(x,y+radius)), fill=pluscrosscolor)
       

                
                #Draw the holes in the group
                for h in g['holes']:
                    self.drawHole(h, canvas, color=color, fcolor=color,radmult=radmult,drawimage=drawimage)
    
                # Draw the paths between each of the holes
                for segment in g['path']:
                    for i in range(len(segment)-1):
                        canvas.drawLine(self.plateCoordShift(segment[i]),
                                        self.plateCoordShift(segment[i+1]), fill=color)
                
                #Determine where to stick the text label for the group
                thmult=Plate.LABEL_ANGLE_MULT[ g['fiber_group'][2:] ]
                if g['fiber_group'][0]=='R':
                    thmult+=Plate.RED_VS_BLUE_MULT_OFFSET
                th=math.radians(90.0-thmult*Plate.LABEL_INC)
                
                tpos=[ -Plate.LABEL_RADIUS*math.cos(th),
                       Plate.LABEL_RADIUS*math.sin(th) ]
                
                #Determine the text label
                label=g['fiber_group']+'-'+str(int(g['fiber_group'][-2:])+len(g['holes'])-1)
        
                if isinstance(canvas,ImageCanvas.ImageCanvas):
                    t=canvas.getTextSize(g['fiber_group'])
                    tpos[0]-=t[0]
                    if g['side']=='left':
                        tpos[0]-=t[0]
    
                #Draw the text label
                if drawimage:
                    lblcolor="White"
                else:
                    lblcolor="Black"

                canvas.drawText( tpos, label, color=lblcolor)   

                    
                #Draw the path
                # Draw a line from the label to the first hole
                canvas.drawLine(tpos, self.plateCoordShift(g['path'][0][0]), fill=color, dashing=1)

        
    def setCoordShiftD(self, D):
        if self.isValidCoordParam_D(D):
            self.coordShift_D=float(D)
        else:
            raise ValueError()
    
    def setCoordShiftR(self, R):
        if self.isValidCoordParam_D(R):
            self.coordShift_R=float(R)
        else:
            raise ValueError()
    
    def setCoordShiftrm(self, rm):
        if self.isValidCoordParam_rm(rm):
            self.coordShift_rm=float(rm)
        else:
            raise ValueError()
    
    def setCoordShifta(self, a):
        if self.isValidCoordParam_D(a):
            self.coordShift_a=float(a)
        else:
            raise ValueError()
    
    def isValidCoordParam_D(self, x):
        if type(x) in [int,long,float]:
            return float(x) > 0.0
        elif type(x) is str:
            try: 
                float(x)
                return float(x) > 0.0
            except ValueError:
                return False
        else:
            return False
        
    def isValidCoordParam_R(self, x):
        if type(x) in [int,long,float]:
            return float(x)**2-self.coordShift_rm**2 >= 0.0 and float(x) > 0.0
        elif type(x) is str:
            try: 
                return float(x)**2-self.coordShift_rm**2 >= 0.0 and float(x) > 0.0
            except ValueError:
                return False
        else:
            return False
        
    def isValidCoordParam_rm(self, x):
        if type(x) in [int,long,float]:
            return self.coordShift_R**2-float(x)**2 >= 0.0 and float(x) > 0.0
        elif type(x) is str:
            try: 
                return self.coordShift_R**2-float(x)**2 >= 0.0 and float(x) > 0.0
            except ValueError:
                return False
        else:
            return False
        
    def isValidCoordParam_a(self, x):
        if type(x) in [int,long,float]:
            return True
        elif type(x) is str:
            try: 
                float(x)
                return True
            except ValueError:
                return False
        else:
            return False

    def isValidSetup(self,s):
        ret=True
        if self.setups:
            ret=s in self.setups
        return ret
