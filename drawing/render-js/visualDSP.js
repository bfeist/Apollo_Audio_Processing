function setupCanvas(canvas, width, height) {
    // Get the device pixel ratio, falling back to 1.
    var dpr = window.devicePixelRatio || 1;
    // Get the size of the canvas in CSS pixels.
    //var rect = canvas.getBoundingClientRect();
    // Give the canvas pixel dimensions of their CSS
    // size * the device pixel ratio.
    width = canvas.width;
    height = canvas.height;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width.toString(10) + "px";
    canvas.style.height = height.toString(10) + "px";
    var ctx = canvas.getContext('2d');
    // Scale all drawing operations by the dpr, so you
    // don't have to worry about the difference.
    ctx.scale(dpr, dpr);
    //ctx.scale(.5, .5);
    return ctx;
}

const sampleRate = data['sample_rate'];
const width = 1440;
const height = 1080;

//
// TODO: Get this information from the data, when it is
// available.
//
const GET_at_frame_0 =
    "32h-37m-00.850s or 32:37:00:51 @" + sampleRate + " fps";

//
// Base styling for all telemetry graphs.
//
const channel_style = {
    // Plot nothing less than 0.9
    clip_min : 0.9,
    // Plot nothing more than 1.1
    clip_max : 1.1,
    // Subtract 1.0 from all samples.
    zero_offset : 1.0,
    // When drawing, advance across the screen, wrapping at 500 samples.
    cycle_size : 500,
    // When drawing previous samples, have them decay in intensity.
    fade : true,
    // Don't draw the zero line.
    draw_zero_line : false,
    // Line weight
    line_width : (width / 1440) * 5.0
};

//
// Base styling for all heart rate monitors.
//
const bpm_meter_options = {
    font : "bold " + ((width / 1440)*42) + "pt courier",
    zero_offset : 1.0,
    trigger_level : -0.025,
    averaging_depth : 15,
    text_align : "end"
};

//
// Options for static text labels.
//
const static_text_options = {
    font : ((width / 1440) * 25) + "pt courier",
    text_align : "end"
};
unit_text_options = {
    font : ((width /1440)*25) + "pt courier",
    text_align : "end"
};

//
// Compute sizes for items.
//
let ekg_width = width * .75;

const global_options = {
    // The data sampling rate, in hertz.
    sample_rate : sampleRate,

    // Left hand edge
    x : width * 0.05,

    // 
    // Keep only the last 400 samples on screen.
    //
    ekg_depth : 400,

    ekg_x_scale : ekg_width / channel_style.cycle_size,
    ekg_y_scale : (width / 1440) * 1200,
    zpn_y_scale : (width / 1440) * 800,
    ekg_lane_height : (width / 1440) * 130,
    ekg_lane_start :  (width / 1440) * 200,
    ekg_bpm_meter_x : width - (width/1440) * 165,
    ekg_label_x : width - (width / 1440) * 90,
    role_adj_y : -(width / 1440) * 37,
    name_adj_y : (width / 1440) * 37
};

const c = data['channels'];
let CMDR_EKG_source = new ArrayWaveSource(c['CMDR EKG']);
let LMP_EKG_source = new ArrayWaveSource(c['LMP EKG']);
let CMP_EKG_source = new ArrayWaveSource(c['CMP EKG']);
let CMDR_ZPN_source = new ArrayWaveSource(c['CMDR ZPN']);
let LMP_ZPN_source = new ArrayWaveSource(c['LMP ZPN']);
let CMP_ZPN_source = new ArrayWaveSource(c['CMP ZPN']);

let graph = new SignalGraph();
let animated_elements = [];

function setup_EKG(slot, role, name, source, graph, globals, ekg_opts,
    bpm_opts, label_opts) {
    var EKG_graph = new WaveBuffer(
        globals.ekg_depth,
        globals.ekg_x_scale,
        globals.ekg_y_scale,
        source,
        graph,
        ekg_opts
    );

    //
    // Construct the elements that comprise the channel.
    //
    var BPM_meter = new BPMMeter(source, graph, globals.sample_rate, bpm_opts);
    var role_static = new StaticText(role, label_opts);
    var name_static = new StaticText(name, label_opts);
    var BPM_static = new StaticText("BPM", label_opts);

    //
    // Position the elements in their places.
    //
    var lane_base_y = globals.ekg_lane_start + globals.ekg_lane_height * slot;

    EKG_graph.x = globals.x;
    EKG_graph.y = lane_base_y;
    BPM_meter.x = globals.ekg_bpm_meter_x;
    BPM_meter.y = lane_base_y;
    role_static.x = globals.ekg_label_x;
    role_static.y = lane_base_y + globals.role_adj_y;
    name_static.x = globals.ekg_label_x;
    name_static.y = lane_base_y + globals.name_adj_y;
    BPM_static.x = globals.ekg_label_x;
    BPM_static.y = lane_base_y;

    animated_elements.push(EKG_graph);
    animated_elements.push(BPM_meter);
    animated_elements.push(role_static);
    animated_elements.push(name_static);
    animated_elements.push(BPM_static);
}

function setup_ZPN(slot, role, name, source, graph, globals, zpn_opts,
    label_opts) {
    var ZPN_graph = new WaveBuffer(
        globals.ekg_depth,
        globals.ekg_x_scale,
        globals.ekg_y_scale * .8,
        source,
        graph,
        zpn_opts
    );

    //
    // Construct the elements that comprise the channel.
    //
    var role_static = new StaticText(role, label_opts);
    var name_static = new StaticText(name, label_opts);
    var ZPN_static = new StaticText("ZPN", label_opts);

    //
    // Position the elements in their places.
    //
    var lane_base_y = globals.ekg_lane_start + globals.ekg_lane_height * slot;

    ZPN_graph.x = globals.x;
    ZPN_graph.y = lane_base_y;
    role_static.x = globals.ekg_label_x;
    role_static.y = lane_base_y + globals.role_adj_y;
    name_static.x = globals.ekg_label_x;
    name_static.y = lane_base_y + globals.name_adj_y;
    ZPN_static.x = globals.ekg_label_x;
    ZPN_static.y = lane_base_y;

    animated_elements.push(ZPN_graph);
    animated_elements.push(role_static);
    animated_elements.push(name_static);
    animated_elements.push(ZPN_static);
}

CMDR_ekg_options = Object.assign({}, channel_style);
CMDR_bpm_options = Object.assign({}, bpm_meter_options);
CMDR_unit_options = Object.assign({}, unit_text_options);
CMDR_ekg_options.color_rgb = [ 255, 255, 0];
CMDR_bpm_options.fill_style = "#ffff00";
CMDR_unit_options.fill_style = "#a0a000";
setup_EKG(0, "CDR", "Lovell", CMDR_EKG_source, graph, global_options,
    CMDR_ekg_options, CMDR_bpm_options, CMDR_unit_options);

LMP_ekg_options = Object.assign({}, channel_style);
LMP_bpm_options = Object.assign({}, bpm_meter_options);
LMP_unit_options = Object.assign({}, unit_text_options);
LMP_ekg_options.color_rgb = [ 0, 255, 255];
LMP_bpm_options.fill_style = "#00ffff";
LMP_unit_options.fill_style = "#00a0a0";
setup_EKG(1, "LMP", "Haise", LMP_EKG_source, graph, global_options,
    LMP_ekg_options, LMP_bpm_options, LMP_unit_options);

CMP_ekg_options = Object.assign({}, channel_style);
CMP_bpm_options = Object.assign({}, bpm_meter_options);
CMP_unit_options = Object.assign({}, unit_text_options);
CMP_ekg_options.color_rgb = [ 255, 0, 255];
CMP_bpm_options.fill_style = "#ff00ff";
CMP_unit_options.fill_style = "#a000a0";
setup_EKG(2, "CMP", "Swigert", CMP_EKG_source, graph, global_options,
    CMP_ekg_options, CMP_bpm_options, CMP_unit_options);

setup_ZPN(3, "CDR", "Lovell", CMDR_ZPN_source, graph, global_options,
    CMDR_ekg_options, CMDR_unit_options);

setup_ZPN(4, "LMP", "Haise", LMP_ZPN_source, graph, global_options,
    LMP_ekg_options, LMP_unit_options);

setup_ZPN(5, "CMP", "Swigert", CMP_ZPN_source, graph, global_options,
    CMP_ekg_options, CMP_unit_options);

let marker = new FrameLabel(CMDR_EKG_source, graph,
    { 0 : GET_at_frame_0 },
    { x : 10, y : 20, fill_style : "white" },
);

graph.finalize();

const canvas = document.querySelector('canvas');
const brush = setupCanvas(canvas, window.innerWidth, window.innerHeight);

function animate_one_frame(brush) {
    graph.advance();

    brush.save();
    brush.fillStyle = "black";
    brush.fillRect(0,0,width,height);
    brush.restore();

    animated_elements.forEach(item => item.display(brush));
    marker.display(brush);
}

function render_animation_to_file() {
    //
    // Create a capturer that exports to WebM format.
    //
    var capturer = new CCapture({
        format: 'webm',
        framerate: sampleRate,
        verbose: true
     });

     //
     // Determine how many frames of data we have.
     //
     var total_frames = c['CMDR EKG'].length;

    capturer.start();
    for (i = 0; i < total_frames; i++) {
        animate_one_frame(brush);
        capturer.capture(canvas);
    }
    capturer.stop();
    capturer.save();
}

function render_animation_to_window() {
    requestAnimationFrame(render_animation_to_window);
    animate_one_frame(brush);
}