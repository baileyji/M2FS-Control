#!/bin/bash
./galilAgent.py --side R &
./galilAgent.py --side B &
./shoeAgent.py --side R &
./shoeAgent.py --side B &
./slitController.py &
#./plugController.py &
./pluggingAgent.py &
./shackhartmanAgent.py &
./director.py &