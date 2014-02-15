import Tkinter
import BetterCanvas
import ImageCanvas
import Plate
import tkMessageBox
import os

class HoleInfoDialog:
        
    def __init__(self, parent, canvas, plate, setup, holeIDs):
        self.canvas=canvas
        self.parent=parent
        self.setup=setup
        self.getHoleInfo=lambda a:plate.getHoleInfo(a)
        self.getFiberForHole=lambda a:plate.getFiberForHole(a, setup)
        self.getChannelForHole=lambda a:plate.getChannelForHole(a, setup)
        
        if len(holeIDs) > 1:
            self.initializeSelection(holeIDs)
        else:
            self.initializeSingle(holeIDs[0])
            
    def initializeSelection(self, holeIDs):
        
        self.dialog=Tkinter.Toplevel(self.parent)
        self.dialog.bind("<FocusOut>", self.defocusCallback)
        self.dialog.bind("<Destroy>", self.destroyCallback)
        
        self.holeID=holeIDs
        
        for i,id in enumerate(holeIDs):
            
            self.add_callback_for_id(id)
            
            self.canvas.itemconfigure('.'+id, state=Tkinter.DISABLED)

            info=self.getHoleInfo(id)
            
            lbl_str=' '.join(['ID:',id,'Type:',info['TYPE'],'Galaxy ID:',
                               info['GALAXYID'],'other info'])
            Tkinter.Label(self.dialog, text=lbl_str).grid(row=i,column=0)
            
            Tkinter.Button(self.dialog,text='Select',command=getattr(self,'cb'+id)).grid(row=i,column=1)
                

    def initializeSingle(self, holeID):

        self.canvas.itemconfigure('.'+holeID,state=Tkinter.DISABLED)
        self.dialog=Tkinter.Toplevel(self.parent)
        self.dialog.bind("<FocusOut>", self.defocusCallback)
        self.dialog.bind("<Destroy>", self.destroyCallback)
        
        self.holeID=holeID
        info=self.getHoleInfo(holeID)
        print info
        
        #types: TROSFGA
        Tkinter.Label(self.dialog, text='Type: '+info['TYPE']).pack(anchor='w')
        if info['TYPE'] in 'OSGA':

            Tkinter.Label(self.dialog, text='Galaxy ID: '+info['GALAXYID']).pack(anchor='w')
            Tkinter.Label(self.dialog, text='RA: %i %i %2.3f'%info['RA']).pack(anchor='w')
            Tkinter.Label(self.dialog, text='Dec: %i %i %2.3f'%info['DEC']).pack(anchor='w')
            if info['TYPE'] not in 'S':
                Tkinter.Label(self.dialog, text='Mag: %f'%info['MAGNITUDE']).pack(anchor='w')
                Tkinter.Label(self.dialog, text='Color: %f'%info['COLOR']).pack(anchor='w')
            
            Tkinter.Label(self.dialog, text='Setup Specific Information').pack()
            Tkinter.Label(self.dialog, text="Channel: "+self.getChannelForHole(holeID)).pack(anchor='w')
            Tkinter.Label(self.dialog, text="Assigned Fiber: "+self.getFiberForHole(holeID)).pack(anchor='w')

        Tkinter.Button(self.dialog,text='Done',command=self.ok).pack()


    def add_callback_for_id(self, holeID):
        def innercb():
            self.close()
            self.initializeSingle(holeID)
        innercb.__name__ = "cb"+holeID
        setattr(self,innercb.__name__,innercb)
        

    def defocusCallback(self, event):
        self.ok()
    
    def ok(self):
        self.save()
        self.close()
    
    def destroyCallback(self, event):
        self.resetHoles()

    def save(self):
        pass    
    
    def close(self):   
        self.resetHoles()
        self.dialog.destroy()
        
    def resetHoles(self):
        if isinstance(self.holeID, str):
            self.canvas.itemconfig('.'+self.holeID,state=Tkinter.NORMAL)
        else:
            for id in self.holeID:
                self.canvas.itemconfig('.'+id,state=Tkinter.NORMAL)
        
        
class App(Tkinter.Tk):
    def __init__(self, parent):
        Tkinter.Tk.__init__(self, parent)
        self.parent = parent
        self.initialize()

    def initialize(self):

        self.plate=Plate.Plate()
        self.file_str=Tkinter.StringVar(value='No File Loaded')
        
        #Basic window stuff
        swid=120
        bhei=55
        whei=735
        chei=whei-bhei
        wwid=chei+swid
        self.geometry("%ix%i"%(wwid,whei))
        self.title("Hole App")
        
        
        #The sidebar
        frame = Tkinter.Frame(self, width=swid, bd=0, bg=None)#None)
        frame.place(x=0,y=0)

        #Info display
        frame2 = Tkinter.Frame(self, height=bhei, bd=0, bg=None)#None)
        frame2.place(x=0,y=whei-45-1)

        #The canvas for drawing the plate        
        self.canvas=BetterCanvas.BetterCanvas(self, chei, chei, 1.01, 1.01, bg='White')
        self.canvas.place(x=swid,y=0)
        self.canvas.bind("<Button-1>",self.canvasclick)


        #Buttons
        Tkinter.Button(frame, text="Show All", command=self.show).pack()
        Tkinter.Button(frame, text="Show Red", 
                       command=lambda:self.show(channel='armR')).pack()
        Tkinter.Button(frame, text="Show Blue", 
                       command=lambda:self.show(channel='armB')).pack()
        Tkinter.Button(frame, text="Make Image", command=self.makeImage).pack()
        Tkinter.Button(frame, text="Make R Image", 
                       command=lambda:self.makeImage(channel='armR')).pack()
        Tkinter.Button(frame, text="Make B Image", 
                       command=lambda:self.makeImage(channel='armB')).pack()
        Tkinter.Button(frame, text="Load Holes", command=self.load).pack()
        Tkinter.Button(frame, text="Regionify", command=self.makeRegions).pack()
        Tkinter.Button(frame, text="Write Map", command=self.writeMap).pack()
        self.coordshft_str=Tkinter.StringVar(value='CShift On')
        Tkinter.Button(frame, textvariable=self.coordshft_str, command=self.toggleCoord).pack()

        #Input
        #Setup input
        self.setup_str=Tkinter.StringVar(value='1')
        
        lframe=Tkinter.Frame(frame)
        lframe.pack()
        
        Tkinter.Label(lframe, text='Setup #:').grid(row=0,column=0)
        entry=Tkinter.Entry(lframe, validate='focusout', width=2, 
                      invcmd=lambda:tkMessageBox.showerror('Bad Setup','Not a valid setup.'),
                      vcmd=lambda:self.plate.isValidSetup(self.getActiveSetup()), 
                      textvariable=self.setup_str)
        entry.grid(row=0,column=1)
        #entry.bind("<Return>",self.show)
   
        #Coordinate shift input
        self.Dparam_str=Tkinter.StringVar(value='64')
        self.rmparam_str=Tkinter.StringVar(value='13.21875')
        self.aparam_str=Tkinter.StringVar(value='0.03')
        self.Rparam_str=Tkinter.StringVar(value='50.68')
        
        paramw=4
        pframe=Tkinter.LabelFrame(frame,text='Coord. Params',relief='flat')
        pframe.pack()
        
        Dframe=Tkinter.LabelFrame(pframe,text='D',relief='flat')
        Dframe.grid(row=0,column=0)
        entry=Tkinter.Entry(Dframe, validate='focusout', width=paramw,
            invcmd=lambda:tkMessageBox.showerror('Bad D','Not a value for D.'),
            vcmd=lambda:self.plate.isValidCoordParam_D(self.Dparam_str.get()),
            textvariable=self.Dparam_str)
        entry.pack()
        #entry.bind("<FocusOut>",self.setCoordShiftD)
        entry.bind("<Return>",self.setCoordShiftD)

        rmframe=Tkinter.LabelFrame(pframe,text='rm',relief='flat')
        rmframe.grid(row=0,column=1)
        entry=Tkinter.Entry(rmframe, validate='focusout', width=paramw,
            invcmd=lambda:tkMessageBox.showerror('Bad rm','Not a value for rm.'),
            vcmd=lambda:self.plate.isValidCoordParam_rm(self.rmparam_str.get()),
            textvariable=self.rmparam_str)
        entry.pack()
        #entry.bind("<FocusOut>",self.setCoordShiftrm)
        entry.bind("<Return>",self.setCoordShiftrm)
        
        Rframe=Tkinter.LabelFrame(pframe,text='R',relief='flat')
        Rframe.grid(row=1,column=0)
        entry=Tkinter.Entry(Rframe, validate='focusout', width=paramw,
            invcmd=lambda:tkMessageBox.showerror('Bad R','Not a value for R.'),
            vcmd=lambda:self.plate.isValidCoordParam_R(self.Rparam_str.get()),
            textvariable=self.Rparam_str)
        entry.pack()
        #entry.bind("<FocusOut>",self.setCoordShiftR)
        entry.bind("<Return>",self.setCoordShiftR)

        aframe=Tkinter.LabelFrame(pframe,text='a',relief='flat')
        aframe.grid(row=1,column=1)
        entry=Tkinter.Entry(aframe, validate='focusout', width=paramw,
            invcmd=lambda:tkMessageBox.showerror('Bad a','Not a value for a.'),
            vcmd=lambda:self.plate.isValidCoordParam_a(self.aparam_str.get()),
            textvariable=self.aparam_str)
        entry.pack()
        #entry.bind("<FocusOut>",self.setCoordShifta)
        entry.bind("<Return>",self.setCoordShifta)

        #Info output
        self.info_str=Tkinter.StringVar(value='Red: 000  Blue: 000  Total: 0000')
        Tkinter.Label(frame2, textvariable=self.info_str).pack(anchor='w')
        Tkinter.Label(frame2, textvariable=self.file_str).pack(anchor='w')
        
        self.testinit()

    def toggleCoord(self):
        self.plate.toggleCoordShift()
        if self.plate.doCoordShift:
            self.coordshft_str.set('CShift On')
        else:
            self.coordshft_str.set('CShift Off')
        self.show()

    def testinit(self):
        # create a second window and make it cover the entire projector screen
        self.proj_win=Tkinter.Toplevel(self.parent)
        self.proj_win.overrideredirect(1)
        self.proj_win.geometry("768x768+1494+0")

        self.moving={'stat':False}
        self.proj_win.bind("<Button-1>",self.startMove)
        self.proj_win.bind("<ButtonRelease-1>",self.stopMove)
        self.proj_win.bind("<B1-Motion>", self.Move)
        print '.'+self.proj_win.winfo_screen()+'.'
        
        self.proj_can=BetterCanvas.BetterCanvas(self.proj_win, 768,768, 1.00, 1.00, bg='Black')
        self.proj_can.place(x=-3,y=-3)
        self.show()

    def Move(self,event):
        if self.moving['stat']:
            
            dx=event.x_root-self.moving['xs']
            dy=event.y_root-self.moving['ys']
            
            xnew=self.moving['xi']+dx
            ynew=self.moving['yi']+dy
            self.proj_win.geometry("768x768+%i+%i"%(xnew,ynew))
            

    def startMove(self,event):
        print '.'+self.proj_win.winfo_screen()+'.'
        self.moving={'stat':True,'xs':event.x_root,'ys':event.y_root,
                     'xi':self.proj_win.winfo_rootx(),
                     'yi':self.proj_win.winfo_rooty()}
        
    
    def stopMove(self,event):
        print '.'+self.proj_win.winfo_screen()+'.'
        self.moving['stat']=False    
    
    def canvasclick(self, event):
        #Get holes that are within a few pixels of the mouse position
        items=self.canvas.find_overlapping(event.x - 2, event.y-2, event.x+2, event.y+2)
        items=filter(lambda a: 'hole' in self.canvas.gettags(a), items)
            
        if items:
            holeIDs=tuple([tag[1:] for i in items for tag in self.canvas.gettags(i) if tag[-1].isdigit()])
            HoleInfoDialog(self.parent, self.canvas, self.plate, self.getActiveSetup(), holeIDs)


    def setCoordShiftD(self,*args):
        if self.plate.isValidCoordParam_D(self.Dparam_str.get()):
            self.plate.setCoordShiftD(self.Dparam_str.get())
        else:
            self.Dparam_str.set(str(self.plate.coordShift_D))
        if self.plate.doCoordShift:
            self.show()

    def setCoordShiftR(self,*args):
        if self.plate.isValidCoordParam_R(self.Rparam_str.get()):
            self.plate.setCoordShiftR(self.Rparam_str.get())
        else:
            self.Rparam_str.set(str(self.plate.coordShift_R))
        if self.plate.doCoordShift:
            self.show()
    
    def setCoordShiftrm(self,*args):
        if self.plate.isValidCoordParam_rm(self.rmparam_str.get()):
            self.plate.setCoordShiftrm(self.rmparam_str.get())
        else:
            self.rmparam_str.set(str(self.plate.coordShift_rm))
        if self.plate.doCoordShift:
            self.show()

    def setCoordShifta(self,*args):
        if self.plate.isValidCoordParam_a(self.aparam_str.get()):
            self.plate.setCoordShifta(self.aparam_str.get())
        else:
            self.aparam_str.set(str(self.plate.coordShift_a))
        if self.plate.doCoordShift:
            self.show()

    def getActiveSetup(self):
        return "Setup "+self.setup_str.get()


    def show(self, channel='all'):
        self.canvas.clear()
        self.proj_can.clear()
        self.info_str.set(self.plate.getSetupInfo(self.getActiveSetup()))
        self.plate.draw(self.canvas, channel=channel, active_setup=self.getActiveSetup())
        self.plate.drawImage(self.proj_can, channel=channel,radmult=1.1, active_setup=self.getActiveSetup())


    def makeRegions(self):
        self.plate.regionify(active_setup=self.getActiveSetup())
        self.show()


    @staticmethod
    def getPath(sequence):
        dir=os.path.os.path.join(*sequence)
        if os.name is 'nt':
            dir='C:\\'+dir+os.path.sep
        else:
            dir=os.path.expanduser('~/')+dir+os.path.sep
        return dir
        
    def load(self):
        from tkFileDialog import askopenfilename

        dir=App.getPath(('hole_mapper','plates'))
        file=askopenfilename(initialdir=dir, filetypes=[('asc files', '.asc')])
        file=os.path.normpath(file)
        print file
        if file:
            self.plate.loadHoles(file)
            self.file_str.set(os.path.basename(file))
            self.show()
        
    def writeMap(self):
        dir=App.getPath(('hole_mapper',self.plate.plate_name))
        if not os.path.exists(dir):
            os.makedirs(dir)
        self.plate.writeMapFile(dir, self.getActiveSetup())
        
    def makeImage(self,channel='all'):
        #The image canvas for drawing the plate to a file
        dir=App.getPath(('hole_mapper',self.plate.plate_name))
        if not os.path.exists(dir):
            os.makedirs(dir)
        imgcanvas=ImageCanvas.ImageCanvas(1280, 1280, 1.0, 1.0)
        self.plate.drawImage(imgcanvas, channel=channel, active_setup=self.getActiveSetup())
        imgcanvas.save(dir+self.file_str.get()+'_'+self.getActiveSetup()+'_'+channel+'.png')
                            
    
if __name__ == "__main__":
    app = App(None)
    app.title('Hole Mapper')
    app.mainloop()
