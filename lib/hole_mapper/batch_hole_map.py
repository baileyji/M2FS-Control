import Plate
import ImageCanvas

dir='/Users/One/Documents/Mario_Research/plate_routing/plates/'
files=['1_2_3_Sum.asc','411.1_411.2_Sum.asc','419.1_353.1_419.2_353.2_Sum.asc','1651.1_1846.1_1651.2_1846.2_Sum.asc','2155.1_2213.1_2155.2_2213.2_Sum.asc','n431n471n729n601n356_Sum.asc','n512n637n686n241n257n295_Sum.asc','A_B_Sum.asc']

p=Plate.Plate()
for f in files:
    file=dir+f
    p.loadHoles(file)
    for s in p.setups.keys():
        p.regionify(active_setup=s)
        ic=ImageCanvas.ImageCanvas(768, 768, 1.0, 1.0)
        p.drawImage(ic,channel='armB',active_setup=s)
        ic.save(file+'_'+s+'_blue.bmp')
        ic=ImageCanvas.ImageCanvas(768, 768, 1.0, 1.0)
        p.drawImage(ic,channel='armR',active_setup=s)
        ic.save(file+'_'+s+'_red.bmp')
        ic=ImageCanvas.ImageCanvas(768, 768, 1.0, 1.0)
        p.drawImage(ic,active_setup=s)
        ic.save(file+'_'+s+'.bmp')
        p.writeMapFile(dir, s)