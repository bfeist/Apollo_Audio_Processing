class FrameLabel extends SignalNode {
    constructor(src, graph, frames, options) {
        super();

        this.mFrames = frames;
        this.mFrameNumber = -1;
        this.x = options.x || 0;
        this.y = options.y || 0;
        this.mFontStyle = options.font || "12pt Courier";
        this.mFillStyle = options.fill_style || "black";
        
        graph.connect(src, this);
    };
    
    tick() {
        this.mFrameNumber += 1;
    };
    
    display(brush) {
        // Set up a sprite-like context.
        brush.save();
        brush.translate(this.x, this.y);
        
        var text = this.mFrames[this.mFrameNumber];
        if (text) {
            brush.font = this.mFontStyle;
            brush.fillStyle = this.mFillStyle;
            brush.fillText(text, 0, 0);
        }
        brush.restore();
    };
};
