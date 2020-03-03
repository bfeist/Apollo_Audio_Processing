from collections import namedtuple

GET = namedtuple('GET', 'sign hour minute second')
Tape = namedtuple('Tape', 'id rack ul start stop')

def GETFromStr(st):
    '''Return a GET from string representation h:m:s, possibly negative.'''
    parts = st.lstrip().rstrip().split(':')
    h, m, s = parts   
    if h[0] == '-':
        h = h[1:]
        sign = -1
    else:
        sign = 1
    h = int(h, 10)
    m = int(m, 10)
    s = int(s, 10)
    return GET(sign, h, m, s)

def TapeFromData(name, rack_str, start_get_str, stop_get_str):
    name = name.lstrip().rstrip()

    rack_str = rack_str.lstrip().rstrip().lower()
    assert(rack_str.startswith('hr'))
    assert(len(rack_str) == 4)

    rack = int(rack_str[2])
    assert(rack >= 1 and rack <= 2)

    ul = rack_str[3]
    if ul == 'u':
        ul = True
    elif ul == 'l':
        ul = False
    else:
        raise Exception('Bad upper/lower identifier')

    start_get = GETFromStr(start_get_str)
    stop_get = GETFromStr(stop_get_str)

    return Tape(name, rack, ul, start_get, stop_get)
