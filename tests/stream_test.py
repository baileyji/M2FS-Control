from m2fscontrol.m2fsConfig import M2FSConfig
import threading
from datetime import datetime, timedelta
import time
import numpy as np
from walrus import Walrus
from dataloggerAgent import *

keys = ('ifuentrance', 'ifutop', 'ifufiberexit', 'ifumotor', 'ifudrive', 'ifuhoffman',
                        'shoebox', 'cradleR', 'cradleB', 'echelleR', 'echelleB', 'prismR', 'prismB',
                        'loresR', 'loresB')
mainkeys = ('ifuentrance', 'ifutop', 'ifufiberexit', 'ifumotor', 'ifudrive', 'ifuhoffman',
            'shoebox', 'cradleR', 'cradleB')

REDIS_DB=0
redis = Walrus(host='localhost', port=M2FSConfig.getAgentPorts()['redis'], db=REDIS_DB)
dts = redis.time_series('temps', BASE_TEMP_LIST+M2FS_TEMP_LIST+IFUM_TEMP_LIST)
ts = redis.time_series('temps', keys)

def logthread(run_event, ts, keys, interval):
    while run_event.is_set():
        for k in keys:
            getattr(ts, k.lower()).add({'':np.random.uniform()}, id=datetime.utcnow())
        time.sleep(interval)


runtime = 60
interval = .2
run = threading.Event()
run.set()
rthread = threading.Thread(target=logthread, args=(run, ts, ('echelleR', 'prismR', 'loresR'), interval))
bthread = threading.Thread(target=logthread, args=(run, ts, ('echelleB', 'prismB', 'loresB'), interval))
tic = time.time()
bthread.start()
rthread.start()
while time.time()-tic < runtime:
    for k in mainkeys:
        getattr(ts, k.lower()).add({'': np.random.uniform()}, id=datetime.utcnow())
    time.sleep(interval)
run.clear()


def retrieve(k):
    return [(m.timestamp, float(m.data.get(''))) for m in getattr(ts, k.lower()) if m.data.get('')]




SelectedSocket('localhost', agent_ports['ShackHartmanAgent'])
