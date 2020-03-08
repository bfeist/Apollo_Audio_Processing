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
    x = 10;
    depth = 20;
    channel_style = {
        zero_offset : 1.0,
        clip_min : 0.9,
        clip_max : 1.1,
        cycle_size : 380,
        fade : true,
        color_rgb : [ 0, 255, 0 ],
        draw_zero_line : false
    };
} else {
    x = 10;
    depth = 380;
    channel_style = {
        zero_offset : 1.0,
        clip_min : 0.9,
        clip_max : 1.1,
        fade : false,
        color_rgb : [ 0, 255, 0 ],
        draw_zero_line : false
    };
}

let sampleRate = 60;

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

CMDR_EKG_display.x = x;
CMDR_EKG_display.y = 50;

LMP_EKG_display.x = x;
LMP_EKG_display.y = 100;

CMP_EKG_display.x = x;
CMP_EKG_display.y = 150;

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
}

function run_animation(filesystem) {
    for (i = 0; i < total_frames; i++) {
        animate();
        blob = get_animation_frame();
        write_image(i, blob);
    }
}
