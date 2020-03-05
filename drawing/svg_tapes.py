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
import datetime

sys.path.append('../processing_scripts')
import apollo


data = csv.reader(open(sys.argv[1], 'r'), delimiter='\t', quotechar='"',
  lineterminator='\n')
mission_basis = apollo.TimeBases['a13']

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
    'timeline_zero rack_top points_per_hour tape_height rack_slot_height '
    'text_y_adj GET_ruler_y ruler_big_tick_height tick_stroke_width')
context = Context(
    timeline_zero = 180.0,
    rack_top = 100.0,
    points_per_hour = 4.0,
    tape_height = 15.0,
    rack_slot_height = 20.0,
    text_y_adj= 0.0,
    GET_ruler_y = 95.0,
    ruler_big_tick_height = 20.0,
    tick_stroke_width = .25
)

def get_to_hours(get):
    r = get.hour + get.minute / 60.0 + get.second / 3600.0
    r *= get.sign
    return r

def tape_position(ctx, tape):
    rack_slot = (tape.rack - 1) * 2
    if not tape.ul:
        # Lower rack
        rack_slot += 1

    x = ctx.timeline_zero + ctx.points_per_hour * get_to_hours(tape.start)
    y = ctx.rack_top + ctx.rack_slot_height * rack_slot

    return (x, y)

def tape_dimensions(ctx, tape):
    get_hour_start = get_to_hours(tape.start)
    get_hour_stop = get_to_hours(tape.stop)
    duration_hrs = get_hour_stop - get_hour_start
    width = duration_hrs * ctx.points_per_hour
    height = ctx.tape_height
    
    return (width, height)

def round_GET_to_hour(et, round_up):
    '''
    Given an elapsed time find the nearest hour mark in a direction.
    '''
    hour = et.hour * et.sign
    if et.minute != 0 or et.second != 0:
        if round_up:
            hour += 1
        else:
            hour -= 1
    return hour

def round_DT_to_hour(dt, round_up):
    '''
    Given a datetime find the nearest hour mark in a direction.
    '''
    if dt.minute != 0 or dt.second != 0:
        total_seconds = dt.minute * 60 + dt.second
        if round_up:
            adjust = 3600 - total_seconds
        else:
            adjust = -total_seconds
        return dt + datetime.timedelta(0, adjust, 0)
    else:
        return dt

def draw_GET_ruler(drawing, ctx, tapes_start_time, tapes_stop_time):
    '''
    Given the start and stop time for the mission, draw a GET ruler above the
    tapes.
    '''
    #
    # Convert to mission time basis.
    #
    earliest_get = apollo.ETFromDatetimeGMT(mission_basis, tapes_start_time)
    latest_get = apollo.ETFromDatetimeGMT(mission_basis, tapes_stop_time)
    
    #
    # Round up and down to the nearest GET hour.
    #
    start_hour = round_GET_to_hour(earliest_get, False)
    stop_hour = round_GET_to_hour(latest_get, True)

    #
    # Draw a ruler with tick marks on each hour. 10-hour boundaries
    # get the tallest marks. 5-hour boundaries get half marks, and the
    # remainder get quarter marks.
    #
    for hour in range(start_hour, stop_hour):
        if hour % 10 == 0:
            tick_relative_height = 1.0
        elif hour % 5 == 0:
            tick_relative_height = 0.5
        else:
            tick_relative_height = 0.25
        tick_height = ctx.ruler_big_tick_height * tick_relative_height
        tick_x = ctx.timeline_zero + hour * ctx.points_per_hour
        
        tick = drawing.line(
            start=(tick_x, ctx.GET_ruler_y),
            end=(tick_x, ctx.GET_ruler_y - tick_height),
            stroke="black",
            stroke_width=str(ctx.tick_stroke_width)
        )
        drawing.add(tick)

def draw_GMT_ruler(drawing, ctx, tapes_start_time, tapes_stop_time):
    '''
    Given the start and stop time for the mission, draw a terrestrial
    time ruler above the tapes, using Greenwich Mean Time.
    '''
    #
    # Round up and down to the nearest GET hour.
    #
    start_time = round_DT_to_hour(tapes_start_time, False)
    stop_time = round_DT_to_hour(tapes_stop_time, False)

    all_balls = mission_basis.all_balls_dt
    
    #
    # Draw a ruler with tick marks on each hour. 10-hour boundaries
    # get the tallest marks. 5-hour boundaries get half marks, and the
    # remainder get quarter marks.
    #
    t = 
    for hour in range(start_hour, stop_hour):
        if hour % 10 == 0:
            tick_relative_height = 1.0
        elif hour % 5 == 0:
            tick_relative_height = 0.5
        else:
            tick_relative_height = 0.25
        tick_height = ctx.ruler_big_tick_height * tick_relative_height
        tick_x = ctx.timeline_zero + hour * ctx.points_per_hour
        
        tick = drawing.line(
            start=(tick_x, ctx.GET_ruler_y),
            end=(tick_x, ctx.GET_ruler_y - tick_height),
            stroke="black",
            stroke_width=str(ctx.tick_stroke_width)
        )
        drawing.add(tick)

drawing = svgwrite.drawing.Drawing(
    filename='A13-tapes.svg', size=(u'792pt',u'612pt')
)

for tape in tapes:
    x, y = tape_position(context, tape)
    width, height = tape_dimensions(context, tape)
    center_x = x + width / 2.0
    center_y = y + height / 2.0
    
    drawing.add(drawing.rect((x, y), (width, height), fill="none", stroke="black"))
    label = drawing.text(tape.id, (center_x, center_y+context.text_y_adj))
    label.update({ 'text-anchor' : 'middle'})
    label.update({ 'dominant-baseline' : 'central'})
    drawing.add(label)

#
# Find the earliest and latest times for the tape recordings.
#
earliest_tape_time = min(
    apollo.DatetimeGMTFromET(mission_basis, tape.start) for tape in tapes
)
latest_tape_time = max(
    apollo.DatetimeGMTFromET(mission_basis, tape.stop) for tape in tapes
)

draw_GET_ruler(drawing, context, earliest_tape_time, latest_tape_time)

drawing.save()

