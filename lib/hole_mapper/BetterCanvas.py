import math
import Tkinter
import PIL.ImageColor as imgColor

class BetterCanvas(Tkinter.Canvas):
    def __init__(self, parent, width, height, units_hwidth, units_hheight, bg='White'):
        
        Tkinter.Canvas.__init__(self, parent, width=width, height=height, bg=bg)
        self.parent=parent
         
        self.centerx=float(width)/2.0
        self.centery=float(height)/2.0

        self.scalex=self.centerx/units_hwidth
        self.scaley=self.centery/units_hheight
        
        #Register onResize so it gets called if the canvas window is resized

    def clear(self):
        self.delete(Tkinter.ALL)

    def onResize(self):
        pass
    
    def sanitizeColorKW(self, kwdict):	
        for k in ['color','fill','background','outline','bg']:
            if k in kwdict and kwdict[k]!=None:
                tkcol="#%02x%02x%02x" % imgColor.getrgb(kwdict[k])
                kwdict[k]=tkcol
        
    def drawCircle(self, (x,y), r, **kw):
        x1=self.canvasCoordx(x-r)
        x2=self.canvasCoordx(x+r)
        y1=self.canvasCoordy(y+r)
        y2=self.canvasCoordy(y-r)
        self.sanitizeColorKW(kw)
        self.create_oval(x1,y1,x2,y2, kw)

    def drawSquare(self,(x,y), len, **kw):
        self.sanitizeColorKW(kw)
        self.create_rectangle(
              self.canvasCoordx(x-len/2.),
              self.canvasCoordy(y-len/2.),  
              self.canvasCoordx(x+len/2.),  
              self.canvasCoordy(y+len/2.), kw)

    def drawRectangle(self,(x0,y0,x1,y1), **kw):
        self.sanitizeColorKW(kw)
        self.create_rectangle(
              self.canvasCoordx(x0),
              self.canvasCoordy(y0),  
              self.canvasCoordx(x1),  
              self.canvasCoordy(y1), kw)  

    def drawDashedLine(self, *args, **kw):
        
        
        self.drawLine(*args, **kw)

    def drawLine(self, *args, **kw):
        assert len(args) == 2 or len(args) == 3

        self.sanitizeColorKW(kw)
        pos0 = args[0]
        if len(args) == 2:
            pos1 = args[1]
        else:
            l = args[1]
            th = args[2]
            x2=pos0[0]+l*math.cos(math.radians(th))
            y2=pos0[1]+l*math.sin(math.radians(th))
            pos1=(x2,y2)

        if kw.pop('dashing',None):
            kw['dash']=(3,3)

        self.create_line(self.canvasCoordx(pos0[0]),
                         self.canvasCoordy(pos0[1]),
                         self.canvasCoordx(pos1[0]),
                         self.canvasCoordy(pos1[1]),kw)


    def drawText(self,(x,y),text,color=None, center=0):
        kw={'color':color}
        self.sanitizeColorKW(kw)
        self.create_text(self.canvasCoordx(x),
                         self.canvasCoordy(y),
                         text=text,fill=kw['color'])
         
    
    def canvasCoordx(self,x):
        return round(-self.scalex*x+self.centerx)
    
    def canvasCoordy(self,y):
        return round(-self.scaley*y+self.centery)
