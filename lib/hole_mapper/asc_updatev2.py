import glob
import os
import platefile

files=glob.glob(os.getcwd()+os.path.sep+'*.asc')
files.extend(glob.glob(os.getcwd()+os.path.sep+'*'+os.path.sep+'*.asc'))
for f in files:
    try:
        fsock = open(f+'~')
        fsock.close()
    except IOError:
        x=platefile.ascfile(f)
        x.writeWithChannels()
