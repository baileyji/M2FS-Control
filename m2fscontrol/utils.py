def longTest(s):
    """ Return true if s can be cast as a long, false otherwise """
    try:
        long(s)
        return True
    except ValueError:
        return False


def floatTest(s):
    """ Return true if s can be cast as a long, false otherwise """
    try:
        float(s)
        return True
    except ValueError:
        return False
