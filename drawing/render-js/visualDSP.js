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
    return ctx;
}

const GET_at_frame_0 = "32h-37m-00.850s or 32:37:00:51 @ 60fps";

const scenario = "classic";

var x;
var channel_style;
var depth;

if (scenario == "classic") {
    //
    // Set up the display for a classic phosphor CRT emulation.
    //
    x = 10;

    // 
    // Keep only the last 20 samples on screen.
    //
    depth = 20;

    channel_style = {
        // Plot nothing less than 0.9
        clip_min : 0.9,
        // Plot nothing more than 1.1
        clip_max : 1.1,
        // Subtract 1.0 from all samples.
        zero_offset : 1.0,
        // When drawing, advance across the screen, wrapping at 340 pixels.
        cycle_size : 320,
        // When drawing previous samples, have them decay in intensity.
        fade : true,
        // Draw in green.
        color_rgb : [ 0, 255, 0 ],
        // Don't draw the zero line.
        draw_zero_line : false
    };
} else {
    //
    // Set up for a more modern display.
    //
    x = 10;

    //
    // Keep a lot of samples on screen.
    //
    depth = 340;

    channel_style = {
        // Plot nothing less than 0.9
        clip_min : 0.9,
        // Plot nothing more than 1.1
        clip_max : 1.1,
        // Subtract 1.0 from all samples.
        zero_offset : 1.0,
        // Don't fade previous samples.
        fade : false,
        // Draw in green.
        color_rgb : [ 0, 255, 0 ],
        // Don't draw the zero line.
        draw_zero_line : false
    };
}

//
// Options for BPM meters.
//
bpm_meter_options = {
    font_style : "bold 12pt courier",
    fill_style : "#00ff00",
    zero_offset : 1.0,
    trigger_level : -0.025,
    averaging_depth : 5,
};

let sampleRate = 50;

let graph = new SignalGraph();

let CMDR_EKG_source = new ArrayWaveSource(data['CMDR EKG']);
let LMP_EKG_source = new ArrayWaveSource(data['LMP EKG']);
let CMP_EKG_source = new ArrayWaveSource(data['CMP EKG']);
let CMDR_ZPN_source = new ArrayWaveSource(data['CMDR ZPN']);
let LMP_ZPN_source = new ArrayWaveSource(data['LMP ZPN']);
let CMP_ZPN_source = new ArrayWaveSource(data['CMP ZPN']);

let CMDR_EKG_display = new WaveBuffer(depth, 500, CMDR_EKG_source, graph, channel_style);
let LMP_EKG_display = new WaveBuffer(depth, 500, LMP_EKG_source, graph, channel_style);
let CMP_EKG_display = new WaveBuffer(depth, 500, CMP_EKG_source, graph, channel_style);
let CMDR_ZPN_display = new WaveBuffer(depth, 500, CMDR_ZPN_source, graph, channel_style);
let LMP_ZPN_display = new WaveBuffer(depth, 500, LMP_ZPN_source, graph, channel_style);
let CMP_ZPN_display = new WaveBuffer(depth, 500, CMP_ZPN_source, graph, channel_style);
let marker = new FrameLabel(CMDR_EKG_display, graph,
    { 0 : GET_at_frame_0 },
    { x : 10, y : 20, fill_style : "white" },
);
let CMDR_EKG_meter = new BPMMeter(CMDR_EKG_source, graph, sampleRate, bpm_meter_options);
let LMP_EKG_meter = new BPMMeter(LMP_EKG_source, graph, sampleRate, bpm_meter_options);
let CMP_EKG_meter = new BPMMeter(CMP_EKG_source, graph, sampleRate, bpm_meter_options);
let CMDR_BPM_static = new StaticText("CMDR", {
    fill_style : "green",
    font : "10pt courier"
});
let LMP_BPM_static = new StaticText("LMP", {
    fill_style : "green",
    font : "10pt courier"
});
let CMP_BPM_static = new StaticText("CMP", {
    fill_style : "green",
    font : "10pt courier"
});

CMDR_EKG_display.x = x;
CMDR_EKG_display.y = 50;

CMDR_EKG_meter.x = 340;
CMDR_EKG_meter.y = 50;

CMDR_BPM_static.x = 340;
CMDR_BPM_static.y = 35;

LMP_EKG_display.x = x;
LMP_EKG_display.y = 100;

LMP_EKG_meter.x = 340;
LMP_EKG_meter.y = 100;

LMP_BPM_static.x = 340;
LMP_BPM_static.y = 85;

CMP_EKG_display.x = x;
CMP_EKG_display.y = 150;

CMP_EKG_meter.x = 340;
CMP_EKG_meter.y = 150;

CMP_BPM_static.x = 340;
CMP_BPM_static.y = 135;

CMDR_ZPN_display.x = x;
CMDR_ZPN_display.y = 200;

LMP_ZPN_display.x = x;
LMP_ZPN_display.y = 250;

CMP_ZPN_display.x = x;
CMP_ZPN_display.y = 300;


graph.finalize();

const canvas = document.querySelector('canvas');
const brush = setupCanvas(canvas, window.innerWidth, window.innerHeight);


function animate(){
    requestAnimationFrame(animate);
    graph.advance();

    brush.save();
    brush.fillStyle = "black";
    brush.fillRect(0,0,innerWidth,innerHeight);
    brush.restore();

    CMDR_EKG_display.display(brush);
    LMP_EKG_display.display(brush);
    CMP_EKG_display.display(brush);
    CMDR_ZPN_display.display(brush);
    LMP_ZPN_display.display(brush);
    CMP_ZPN_display.display(brush);
    marker.display(brush);
    CMDR_EKG_meter.display(brush);
    LMP_EKG_meter.display(brush);
    CMP_EKG_meter.display(brush);
    CMDR_BPM_static.display(brush);
    LMP_BPM_static.display(brush);
    CMP_BPM_static.display(brush);
}

function run_animation(filesystem) {
    for (i = 0; i < total_frames; i++) {
        animate();
        blob = get_animation_frame();
        write_image(i, blob);
    }
}
