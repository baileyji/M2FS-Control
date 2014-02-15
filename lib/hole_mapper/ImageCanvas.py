import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
#import PIL.ImageFilter
import math

class ImageCanvas():
    def __init__(self, width, height, units_hwidth, units_hheight):
    
        #http://www.pythonware.com/library/pil/handbook/imagedraw.htm for ref
        #create a new image filled black
        self.mult=4
        self.lwid=int(self.mult+3)

        self.default_color='White'
        self.finishedSize=(width,height)
        
        self.image= PIL.Image.new("RGB", (self.mult*width, self.mult*height))
        self.draw = PIL.ImageDraw.Draw(self.image)
        
        self.centerx=self.mult*float(width)/2.0
        self.centery=self.mult*float(height)/2.0

        self.scalex=self.centerx/units_hwidth
        self.scaley=self.centery/units_hheight
        
        
    def save(self, file):
        #im=self.image.filter(PIL.ImageFilter.SMOOTH)
        im=self.image.resize(self.finishedSize,PIL.Image.ANTIALIAS)
        im.save(file)


    def clear(self):
        pass


    def setupColors(self, outline, fill):
    
        c=[self.default_color, None]
        if outline:
            c[0]=outline
        if fill:
            c[1]=fill
        
        return c

    #assumes that canvas coord scaling is same in both x and y dimensions
    def drawCircle(self, (x,y), r, fill=None, outline=None, width=None):
        
        # Get the coordinates 
        p1=( self.canvasCoordx(x-r),
             self.canvasCoordy(y-r) )
        p2=( self.canvasCoordx(x+r),
             self.canvasCoordy(y+r) )
        if p1[0] > p2[0]:
            l=[p2,p1]
        else:
            l=[p1,p2]
                
        #Sort out coloring
        col=self.setupColors(outline, fill)

        self.draw.ellipse(l, outline=col[0], fill=col[1])


    #x,y are at center len is length of side
    def drawSquare(self, (x,y), len, outline=None, fill=None, width=None):
    
        # Get the coordinates
        x0=self.canvasCoordx(x-len/2.)
        y0=self.canvasCoordy(y-len/2.)
        x1=self.canvasCoordx(x+len/2.)  
        y1=self.canvasCoordy(y+len/2.)
        
        #Sort out coloring
        col=self.setupColors(outline, fill)
        
        self.draw.rectangle((x0,y0,x1,y1), outline=col[0], fill=col[1])
        

    # x0,y0 is one corner, x1,y1 is corner diagonally across
    def drawRectangle(self, (x0,y0,x1,y1), outline=None, fill=None):
    
        # Get the coordinates
        x0c=self.canvasCoordx(x0)
        y0c=self.canvasCoordy(y0)
        x1c=self.canvasCoordx(x1)  
        y1c=self.canvasCoordy(y1)
        
        #Sort out coloring
        col=self.setupColors(outline, fill)
        
        #From docs: Note that the second coordinate pair 
        # defines a point just outside the rectangle, also
        # when the rectangle is not filled.
        # Not sure if this will be an issue
        self.draw.rectangle((x0c,y0c,x1c,y1c), outline=col[0], fill=col[1])
        
    ##takes either (x0,y0), (x1,y1)  or (x,y), r,theta
    def drawLine(self, *args, **kw):
        assert len(args) == 2 or len(args) == 3

        # Get the coordinates
        pos0 = args[0]
        if len(args) == 2:
            pos1 = args[1]
        else:
            l = args[1]
            th = args[2]
            x2=pos0[0]+l*math.cos(math.radians(th))
            y2=pos0[1]+l*math.sin(math.radians(th))
            pos1=(x2,y2)
            
        x0c=self.canvasCoordx(pos0[0])
        y0c=self.canvasCoordy(pos0[1])
        x1c=self.canvasCoordx(pos1[0])
        y1c=self.canvasCoordy(pos1[1])
        
        #Sort out coloring
        col=self.setupColors(kw.get('fill',None), None)
        
        if kw.pop('dashing',None):
            if x0c > x1c:
                xi,yi=x1c,y1c
                xf,yf=x0c,y0c
            else:
                xi,yi=x0c,y0c
                xf,yf=x1c,y1c
            llen=math.hypot(xf-xi, yf-yi)
            
            notdone=True
            x0,y0=xi,yi
            dl=20
            dx,dy=dl*(xf-xi)/llen,dl*(yf-yi)/llen

            x1,y1=x0+dx,y0+dy
            if x1 < xf:
                while notdone:
                    
                    self.draw.line((x0,y0,x1,y1), fill=col[0],width=self.lwid)
                    x0,y0=x1+dx,y1+dy
                    x1,y1=x0+dx,y0+dy
                    if x1 > xf:
                        self.draw.line((x0,y0,xf,yf), fill=col[0],width=self.lwid)
                        notdone=False
            else:    
                self.draw.line((x0c,y0c,x1c,y1c), fill=col[0],width=self.lwid)
                
        else:
            self.draw.line((x0c,y0c,x1c,y1c), fill=col[0],width=self.lwid)


    # x,y is at upper left corner of text unless center is set to 1
    def drawText(self,(x,y), text, color=None,center=0):

        # Get the coordinates
        xc=self.canvasCoordx(x)
        yc=self.canvasCoordy(y)

        thefont=PIL.ImageFont.truetype("Arial.ttf", 12*self.mult)

        if center:
            tmp=thefont.getsize(text)
            xc-=tmp[0]/2.0
            yc-=tmp[0]/2.0

        #Sort out coloring
        col=self.setupColors(color, None)

        self.draw.text((xc,yc), text, fill=col[0], font=thefont)
        
    def getTextSize(self,text):
        wid,ht=self.draw.textsize(text)
        return ( self.inputCoordx(wid)-self.inputCoordx(0), 
                 self.inputCoordy(ht)-self.inputCoordy(0) )

    # go from coordinates with 0,0 at center to 0,0 at upper left
    def canvasCoordx(self, x):
        return round(-self.scalex*x+self.centerx)


    def canvasCoordy(self, y):
        return round(-self.scaley*y + self.centery)

    def inputCoordx(self, x):
        return (self.centerx-x)/self.scalex

    def inputCoordy(self, y):
        return (self.centery-y)/self.scaley

