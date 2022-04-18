from . import PyNUT

NUT_LOGIN="monitor"
NUT_PASSWORD="1"


def get_ups_state():
    try:
        nut = PyNUT.PyNUTClient(login=NUT_LOGIN, password=NUT_PASSWORD)
        upsstate = nut.GetUPSVars('myups')
        batteryState = [('Battery', upsstate['ups.status']),
                        ('Runtime(s)', upsstate['battery.runtime'])]
    except Exception:
        batteryState = [('Battery', 'Failed to query NUT for status')]
    return batteryState
