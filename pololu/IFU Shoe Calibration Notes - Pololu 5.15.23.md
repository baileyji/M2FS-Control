## Pololu 15V startup ##

The mechanical limits on this scale happen at 4.65 and 22.51.
Pipes have about 13.55mm travel  ~13.55um/count (when calibrated, pololu units are 1/4.096 this)
Height has about 16.60mm travel  ~16.6um/count

HR top of stack
LSB mid stack
STD bottom of stack

- SL 1. STD on 80um slit
- SL 2. STD on 300um slit. 150um core, does not occult
- SL 3. LSB on 180 slit
- SL 4. LSB on 80um slit
- SL 5. LSB on 300 um slit. 260um core, does not occult
- SL 6. HR on 180 um slit. 75um cores, does not occult fibers

_**!!!!!! BOTH SHOES MUCH BE CONNECTED FOR PROPER ADC READINGS !!!!!!!**_

Working with B shoe, cover off, in position from end of Sept.22 run.

Need to determine PID and pololu settings then determine setpoints. Then see if we can attain down position with 15V torque.

1. Frame out and into jig.
1. CoolTerm Connnect. TS. verify ok
1. PI. Move height down, pipe to a high position very carefully using feedback setup wizards.
1. move height to mid and remove leafs. needed to get height cal pos. Make sure to use hand to help lift. visually verify slide is into forward hardstop from below. Sample and save.
1. Tune PID here if needed. Seems Sept. 12V PID params are good enough for 15V on B.
1. Replace leaf springs.
1. (Program updated control tower w/ current best known set points HS/PS)
1. @ BH=8 ~0.3mm clearance or about 18 steps of clearance @HB=17 0.18 or about 10.8
1. Find contact points for pipes for future reference (very valuable if pipes are at "good", meaningful heights). MV down, MV to pipe, mv up to contact, note
1. BH contact at (all 4): 940 850 475 440 400 70
1. Move to midlow and mid pipe with MV and reinstall, shimming to align.
1. Test.
1. 1. Mount in upside down jig
1.1. S180 high @ 940 Stalls at 962 -> can lower pipe or shift slit up.
1.2. S300 high @ 900 -> can lower pipe or shift slit up.
1.5. L300 short @ 400-550 -> can raise pipe or shift slit down.
1.6. H180 high @ 200 -> can lower pipe or shift slits up.
Flip shoe in jig. Right side up now.
1.1. S180 high @ 940 Stalls at 963 -> can lower pipe or shift slit up.
1.2. S300 beautiful @ 875, 900 low @850, 925 -> on pipes?
1.5. L300 short @ 400-550 -> can raise pipe or shift slit down.
1.6. H180 good @ 200

1. Tune Pipes, flipping shoe in jig. Happy with 1 & 6 in B after nudging slit up (YAY!)
1. Switch to R shoe and repeat
1. Initial contact: 880 830 450 425 400 45 (30 is solidly clear)
1.6 solidly clear to 43

IMPORTANT Alignment  notes
Get the slits reacting to all of the screws in the jig first.
If one side is high/low try tuning with a front screw, if it improves but screws up the other side undo and use the back screw to improve the side that is off first.
Back off the rear as much as is needed first. Watch out for nose-down condition (e.g. DON'T DO THAT) then use the front to set a limit. Mid and low (3-6) slits behave much differently from high slits (1, 2). If too low, back off the rear pipes first until it stops responding, then back off the front, then tighten down on the rear until its responsive to everything.

NB dropped B Pipe PID deadzone to 10 from XXX
NB dropped B Height PID deadzone to 14 from XXX

USE JIG to load fibers ~realitically and aid viewing.


When happy, install choes in MSpec and cycle through all 2x.




The zero position of the organ pipes (first, and shortest, organ pipe) occurs when post
hole axis is 5.65 mm from the front face of the actuator.
The pipes are 2.5 mm apart, so the positions relative to the front face are:

Nominal positions are then (position-3mm)*(

Post     Position   Nominal
-lim        4.65    15
1           5.65    24
2           8.15    46
3          10.65    68
4          13.15    91
5          15.65    114
6          18.15    136
+lim       22.51    175

The mechanical limits on this scale happen at 4.65 and 22.51.
Pipes have about 13.55mm travel  ~2um adc count
Height has about 16.60mm travel  ~16.6um count



## Swapping baseplates ##

1. remove shoe base from frame or jig
1. remove front faceplate w/slit
1. attach green clamp (~2.1mm space in front 2.6mm space in rear w/ greed spacers around posts)
1. retract height to lower limit
1. Loosen clamps (not set screws) to remove cables
1. pipes off (can get screws to stay w/ pipes)
1. height to middle (500) make note of maximal low pos (~130)
1. remove rear green clamp
1. catch springs
1. side teflon out
1. transfer cables, bearings, and back clamp
1. work backwards until reassembled but leave cables unclamped so base is essentially reassembled.
1. with plate in compressed position bring height to lowest possible position.
1. tension cables one at a time by using a pair of needle-nose pliers with ~1 loop around nose, leaning pliers away from front of shoe and use back of shoe frame as a lever point.
1. the central clamp will need about twice the tension as the side clamps.
1. Once installed see recalibrating, especially if a motor was exchanged or the connecting screw for the pipes was adjusted

# Recalibrating
1. Start with both axes roughly in the middle (~500) and the baseplate clamped low. They can be hand driven (with significant force for the height, best place to apply the force is on the clamps) but the MV command is also viable.

1. Use MV[B|R]P# to move pipe from center to extremal positions in small ~50 count (1mm) increments after around 300/700
 - Procedure is MVRP500 -> MVRP700 -> (see it not far enough) -> MVRP500 -> MVRP750 (check again).
 - Going back to the centerish is necessary as small moves won't capture bad behavior at the limits
 - If you can't reach limit or the axis tries to go hard into a limit in part of the required travel range the LAC hardware limits must be updated.
 - If the mechanism isn't moving smoothly (see videos for examples) you need to retune the LAC parameters. See that section and call Jeb.
check slit 6 pipe (low pos) pipe position for accuracy (move to 500, move to sl6 pipe area, repeat)
check happy pos with TS
NB looks like we've shifted set point by -24 B pipes
Move to pipe 1
move height to mid
move height up in increments to verify can reach max height, must be slack keep eye on leaf springs
move height to low pos


repeat w/ other shoe
pipe r shift be -9

check for tilt down in front when at pipe high pos
if found, loosen tower bolts in high pos and let them slip back. apply just enough pressure that that make contact and just before the front tilts down, retighten bolts, though keep in mind that if it is slight it may be because the fibers are not installed
final positioning of the towers REQUIRES the fibers (or at the very least the fiber prop) installed
cycle height

#There is a bug in the SS ->EEPROM or EEPROM data codepath!!!

##Setting leaf spring positions
When the travel range and PID are in good shape the leaf spring tower height may need to be adjusted to ensure that the shoeboxes are level at the heigh (SL1) position. This REQUIRES the Wiha 0.9mm allen driver, using any other driver has a high risk of stripping the button cap screws.

- With the dummy fiber box or the real fibers installed move to SL1 to see which side(s) need lift.
- Move to mid height (MV[R|B]H500)
- Remove the two screws holding the leaf spring and slightly loosen the front tower screw.
- Reattach the leaf spring and move to the high position, probably around 850 which will need about 10 more to get good force e.g. MV[R|B]H860
- Slightly loosen the rear tower screw and apply upward pressure on the shoebox plate while simultaneously angling the screwdriver forward to push the tower forward, supporting the up position. Odds are the total adjustment of the tower will be <1 mm.
- While maintaining pressure tighten the rear tower screw.
- MV to 500 then back to high and see if good contact has been made. Keep an eye out for having gone too far (i.e excessive force on the leaf).
- Iterate as needed.
- When happy move back to 500, take the leaf off, tighten the front screw, reattach leaf and test shoe.


##IFU-M Shoe Startup/Calibration from scratch##

Bring up the control tower w/o the shoes connected.
Execute TS and make note of the output just in case

Execure ZB to reset the shoe. Use ZB1 if you want to start with the theoretically nominal slit positions.

connect the shoes.

Execute MVRP500 (ONLY IF PATH IS CLEAR)and MVRH500 to move to the approximate midpoint of travel.
Work down towards  

##Notes 8/12/21 Shoe Assembly & Testing @ SBS w/ Mario##

Calibrating the LAC PID

Lower height all the way. Connect LAC and cool term.
Use lac to drive to -lim in steps.
TS to get ADC/RC position. ADC position should be at the retract limit (or a touch more).
Repeat with extend, ADC max value or a bit less should be extend limit. Click disable defaults between each change for certainty.

Each ADC count is 19.5 um. I used 10 extra for the limits. 185 and 839 for pipes on one shoe.

Despite what Actuonix's docs say the PWM min/max behaves as the speed range during PD operation.

Min of 75B/250R and max of 1023 seem pretty good for the pipes. Too low on the max and they will get stuck. (NB 1/22 These values have since seen significant tweaking)

Pipe centers are about 1.92+.65 mm, 12.9%,1 of travel apart with first post about 5% further than the retract limit. So pipes are roughly at `185/1023 + 5%` at 23.08%, 35.9%, 48.8, 61.6, 74.5%, 87.3%

To set height positions once the pipes are known move to the highest pipe position in increments (i.e. MVBH200, MVBH300, 600...) The highest position is somewhere in the 800-950 range. Be careful about going too far and forcing and upward cant into the rear of the fiber box plate. When that looks good. Lower (e.g. MVBH100) and move the pipes to the lowest position and then raise. Probably in the 200 region. Keep in mind that throughout this process you may need to make bigger moves if the PD tuning of the axis isn't great: if working with different loads than when the PD was tuned (e.g. 2 leafs when tuned with one).

The key Is that the calculated position from TS IS the attained position e.g. if the ADC is stabilized at 343 then the actual position is 335 `round(335/1023)`

To tune the height axis first get a sense of where it needs to be. Then plan on tuning the full up highest position and the lowest position. Start with the highest and start with a low proportional gain (1-2) so that you don't overshoot and ram the thing up. Also start with a low derivative gain (say 10-20). Then good luck (I've not done this yet!)



##Hardware Notes ##
Stroke is 20mm.
When centered, the plate's tabs clear neighboring pipes by 0.75 mm. Positioning pipes to better than 0.5 mm should be fine.
System has 51.2 adu/mm and 50 counts/mm. We've adopted 33 counts as the default tolerance 0.66mm.
20 um/ count


##November 2021 Tuning Notes##

R Side:
- pipe -lim needs to increase to somewhere around 18.6%
- pipe pos ok movements often overshoot, very snappy
- hits +lim only with moves ~ full travel
- frequent hight stopped too low errors (capture and email actuonix?)
- Shorter (2k s) stall, smaller movement theshold seem beneficial for height at base smaller tolerance too
- Tweaked pipe lac to lessen impact at limits and make less snappy and with less overshoot


B Side:
- pipe much nicer, though can really creap in on the position with excessive care
- Changed b down from 119 to 128
- Tweaked height LAC settings and control code slightly (added a nudge move going up)
- Seems to be much more reliable, no stops on the way up.
- Tweaked pipe lac settings, less creeping.

Overall: Happy with system ready for cycling.


## September 2022 Pololu Controler setpoints ##
===R Shoe Status===
(pipe, height)
Toler: 33, 20
Slit Pos:
 Up:    932 875 530 500 470 200
 Down:  300 300 300 300 300 50
 Pipe:  50 230 375 560 745 930
===B Shoe Status===
Toler: 33, 15
Slit Pos:
 Up:    989 940 540 520 480 200
 Down:  300 300 300 300 300 25
 Pipe:  72 230 440 605 785 965



# 2/17/2023 #
===================
R connected
B connected
R&B Normal
===R Shoe Status===
 (pipe, height)
 ADC: 686, 148
 Servo: 230, 875
 Pos: 233, 872
 Err: 3, -3
 Moving: 0, 0
  ms since move: 30254, 30209
  SL Delta: 3, -3
 Toler: 33, 20
Desired Slit: 1
Detected Slit: 2
Errors: 0
Jrk: 1, 1
MiP: 0 Safe: 0 Relay: 1 curPipeNdx: 1
Slit Pos:
 Up:    920 875 530 500 470 200
 Down:  80 80 80 80 80 50
 Pipe:  50 230 375 560 745 930
Free Mem:582
===================
===B Shoe Status===
 (pipe, height)
 ADC: 682, 140
 Servo: 230, 940
 Pos: 232, 935
 Err: 2, -5
 Moving: 0, 0
  ms since move: 439443, 437750
  SL Delta: 2, -5
 Toler: 33, 15
Desired Slit: 1
Detected Slit: 2
Errors: 0
Jrk: 1, 1
MiP: 0 Safe: 0 Relay: 1 curPipeNdx: 1
Slit Pos:
 Up:    985 940 540 520 480 200
 Down:  80 80 80 80 80 35
 Pipe:  72 230 440 605 785 965
Free Mem:582
===================
:

# 5/15/2023 Arrival #

R was sitting on 2/S300 but misaligned Move to 6/H180 looks quite nice
2 on return looks good though high on the outboard (right, non cable) side
1 low 50% of slit width L centered R
3 low 50% R 30% L
4 low 50% L & R
5 low 10% R good L
6 high 10% R 20% L (vignetted!)
2 low 20% L high 10% R


B was sitting on 2 low but just acceptible
SLB6 failed (setpoint 35 ± 15) but manual testing shows 70 is safe
HSBD650 and TOBH30 (and extra ~.25mm) @ 110 WE HIT THE PIPES @ 80 A BIT MAYBE TOO 70 IS CLEAR
still having issues getting down!
gunk (2 pieces of debris (old tape, broken glue?) floating inside stuck on the inside of the slit. appeared on the 80um slit. Took slit off and they fell away

SL2 looks well centered
SL1 centered inboard low outboard 45%

SL3 looks well centered to within 10%
SL2 centered
SL1 LOW 15% LEFT 50% RIGHT (OUTBOARD) 
SL4  LOW 100% LEFT & RIGHT
SL5 LOOKS GOOD, MIGHT BE A TOUCH HIGH BUT BASICALLY NOT POSSIBLE TO IMPROVE GIVEN MOUNT VARIABILITY
SL6 HIGH LEFT AND RIGHT BY 50%
SL3 HIGH 30-50%%
SL2 FINE

-----
Wiggle everything per proceedure.
slb6: both sides 45% high
slb1: within 15% / mount variability
slb2: perfection
slb3: maybe ~10-15% low
slb4: maybe ~10-15% low
slb5: perfect (well simply not possible to do better)
slb6: both sides 45% high

slr6: r 45% high l 78% high (DUR made worse)
slr1: 50% high both sides (DUR made worse)
slr2: 25% high r 13% high l
slr3: 50% high l 33%ish R
slr4: too high ~50%
slr5: too high ~40%
 
Wiggle R
slr6: similar
slr1: similar

Out, wiggle, reinstall
slr6: can't attain
slr6 manually: similar
slr1: perfection
slr2: 25% high r, perfection l (pack to where it was at very first look)
slr3: 50% high l, 25% high r
slr4: 50% high
slr5: 30% high
slr6: (attained) 50% high
slr2: unchanged

R Out, wiggle, reinstall (next day)
slr6: l high ~20 um (vignetted) r high ~10 um (vignetted)
dur: high vignetted by l/r 80/40 um  
dur: no change
slr1: high l/r ~20/40 um
dur: no change
slr2: perfect l r high 75 um
dur: no change
slr3: high l/r 90/45 um
dur: no change
slr4: high l/r 50/20 um
dur: no change
slr5: high l/r 50/35 um
dur: no change
slr6: high l/r 45/20 um
slr2: unchanged



===================
===================
R connected
B connected
R&B Normal
===R Shoe Status===
 (pipe, height)
 ADC: 214, 705
 Servo: 930, 200
 Pos: 931, 203
 Err: 1, 3
 Moving: 0, 0
  ms since move: 2055647, 2055024
  SL Delta: 1, 3
 Toler: 33, 20
Desired Slit: 6
Detected Slit: 6
Errors: 0
Jrk: 1, 1
MiP: 0 Safe: 0 Relay: 1 curPipeNdx: 5
Slit Pos:
 Up:    915 875 530 500 437 200
 Down:  80 80 80 80 85 50
 Pipe:  50 230 375 560 745 930
Free Mem:580
===================
===B Shoe Status===
 (pipe, height)
 ADC: 684, 137
 Servo: 0, 0
 Pos: 232, 939
 Err: 232, 939
 Moving: 0, 0
  ms since move: 2074970, 2074971
  SL Delta: -553, 459
 Toler: 33, 15
Desired Slit: 5
Detected Slit: INTERMEDIATE
Errors: 0
Jrk: 1, 1
MiP: 0 Safe: 0 Relay: 1 curPipeNdx: 1
Slit Pos:
 Up:    987 940 590 520 480 200
 Down:  80 80 80 80 80 35
 Pipe:  72 230 440 605 785 965
Free Mem:580
===================
:
