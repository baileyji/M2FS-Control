import m2fscontrol.selectedconnection as selectedconnection
import time

EXPECTED_FIBERSHOE_INO_VERSION = 'Fibershoe v1.3'
SHOE_BOOT_TIME = 2
SHOE_SHUTDOWN_TIME = .25


class ShoeCommandNotAcknowledgedError(IOError):
    """ Shoe fails to acknowledge a command, e.g. didn't respond with ':' """
    pass


class ShoeSerial(selectedconnection.SelectedSerial):
    """
    Tetris Shoe Controller Connection Class

    This class extents the SelectedSerial implementation of SelectedConnection
    with custom implementations of _postConnect and
    _implementationSpecificDisconnect.

    The _postConnect hook is used to verify the shoe is running a compatible
    firmware version. EXPECTED_FIBERSHOE_INO_VERSION should match the define for
    VERSION_STRING in fibershoe.ino

    _implementationSpecificDisconnect is overridden to guarantee the shoe is
    told to power down whenever the serial connection closes.
    """
    SHOE_BOOT_TIME = SHOE_BOOT_TIME
    SHOE_SHUTDOWN_TIME = SHOE_SHUTDOWN_TIME
    EXPECTED_FIBERSHOE_INO_VERSION = EXPECTED_FIBERSHOE_INO_VERSION

    def _preConnect(self):
        """
        Attempt at workaround for
        https://bugs.launchpad.net/digitemp/+bug/920959
        """
        try:
            from subprocess import call
            s = 'stty crtscts < {device};stty -crtscts < {device}'.format(
                device=self.port)
            ret = call(s, shell=True)
        except Exception, e:
            raise selectedconnection.ConnectError(
                'rtscts hack failed. {}:{}:{}'.format(s, ret, str(e)))

    def _postConnect(self):
        """
        Implement the post-connect hook

        With the shoe we need verify the firmware version. If if doesn't match
        the expected version fail with a ConnectError.
        """
        # Shoe takes a few seconds to boot
        time.sleep(self.SHOE_BOOT_TIME)
        self.connection.flushInput()
        # verify the firmware version
        self.sendMessageBlocking('PV')
        response = self.receiveMessageBlocking()
        self.receiveMessageBlocking(nBytes=1)  # discard the :
        if response != self.EXPECTED_FIBERSHOE_INO_VERSION:
            error_message = ("Incompatible Firmware, Shoe reported '%s', expected '%s'." %
                             (response, self.EXPECTED_FIBERSHOE_INO_VERSION))
            raise selectedconnection.ConnectError(error_message)

    def _implementationSpecificDisconnect(self):
        """ Disconnect the serial connection, telling the shoe to disconnect """
        try:
            self.connection.write('DS\n')
            time.sleep(self.SHOE_SHUTDOWN_TIME)  # just in case the shoe resets on close,
            # gives time to write to EEPROM
            self.connection.flushOutput()
            self.connection.flushInput()
            self.connection.close()
        except Exception, e:
            pass
