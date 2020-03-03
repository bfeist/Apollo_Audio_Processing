'''
Produce an SVG drawing for the Apollo 13 timeline, illustrating the MOCR
tapes, their relationships on the historical recorder racks, and their
time spans.
'''
from tape import TapeFromData
from collections import namedtuple
import svgwrite
import csv
import sys

data = csv.reader(open(sys.argv[1], 'r'), delimiter='\t', quotechar='"',
  lineterminator='\n')

# Check some assertions.
first_row = next(data)
assert(first_row[0].startswith('Tape'))
assert(first_row[1].startswith('HR'))
next_row = next(data)
assert(next_row[13].startswith('Start'))
assert(next_row[14].startswith('Stop'))

tapes = []
for i in range(22):
    row = next(data)
    tape_name, rack, start_get, stop_get = row[0], row[1], row[13], row[14]
    tapes.append(TapeFromData(tape_name, rack, start_get, stop_get))

#
# Point positions of various features.
#
Context = namedtuple('Context',
    'timeline_zero rack_top points_per_hour tape_height rack_slot')
context = Context(
    timeline_zero = 180.0,
    rack_top = 60.0,
    points_per_hour = 4.0,
    tape_height = 15.0,
    rack_slot = 20.0
)

def get_to_hours(get):
    r = get.hour + get.minute / 60.0 + get.second / 3600.0
    r *= get.sign
    return r

def tape_position(ctx, tape):
    if not tape.ul:
        # Lower rack
        rack = tape.rack + 2
    else:
        rack = tape.rack

    x = ctx.timeline_zero + ctx.points_per_hour * get_to_hours(tape.start)
    y = ctx.rack_top + ctx.rack_slot * rack

    return (x, y)

def tape_dimensions(ctx, tape):
    get_hour_start = get_to_hours(tape.start)
    get_hour_stop = get_to_hours(tape.stop)
    duration_hrs = get_hour_stop - get_hour_start
    width = duration_hrs * ctx.points_per_hour
    height = ctx.tape_height
    
    return (width, height)

drawing = svgwrite.drawing.Drawing(
    filename='A13-tapes.svg', size=(u'792pt',u'612pt')
)

for tape in tapes:
    x, y = tape_position(context, tape)
    width, height = tape_dimensions(context, tape)
    
    drawing.add(drawing.rect((x, y), (width, height)))

drawing.save()

