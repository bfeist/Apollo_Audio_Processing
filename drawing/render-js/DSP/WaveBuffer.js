class WaveBuffer extends SignalNode {
    constructor(depth, height, src, graph, options) {
        super();
        this.mData = [];
        this.mDepth = depth;
        this.mHeight = height;
        this.mSource = src;

        this.mZeroOffset = options.zero_offset || 0.0;
        this.x = options.x || 0;
        this.y = options.y || 0;
        this.mClipMin = options.clip_min || undefined;
        this.mClipMax = options.clip_max || undefined;
        this.mDrawZeroLine = options.draw_zero_line || false;
        this.mCycleSize = options.cycle_size || undefined;
        this.mFade = options.fade || false;
        this.mColorRGB = options.color_rgb || [ 0, 255, 0 ];
        this.mZeroLineColorRGB = options.zero_line_color_rgb || [ 0, 255, 0 ];

        this.mCyclePosition = 0;

        graph.connect(src, this);
    };
    
    tick() {
        //
        // Clip and translate incoming data.
        //
        var value = this.mSource.value();

        if (this.mClipMin && value < this.mClipMin) {
            value = this.mClipMin;
        } else if (this.mClipMax && value > this.mClipMax) {
            value = this.mClipMax;
        }
        if (this.mZeroOffset) {
            value -= this.mZeroOffset;
        }

        if (this.mData.length >= this.mDepth) {
            this.mData.shift();
        }
        this.mData.push(value);
    };
    
    display(brush) {
        // Set up a sprite-like context.
        brush.save();
        brush.translate(this.x, this.y);

        brush.lineWidth = 1;
        brush.lineJoin = "round";

        if (this.mDrawZeroLine) {
            brush.beginPath();
            brush.color = "rgb("+this.mZeroLineColor.join()+")";
            brush.moveTo(0, 0);
            brush.lineTo(this.mDepth, 0);
            brush.stroke();
        }

        var start_at = this.mDepth - this.mData.length;
        var last_x, last_y;

        for (let i = 0; i < this.mData.length; i++) {
            var x = i + start_at;
            var y = this.mData[i]*-this.mHeight;
            
            if (this.mCycleSize) {
                x += this.mCyclePosition;
                x = x % this.mCycleSize;
            }

            if (i != 0) {
                var fade;
                if (this.mFade)
                    fade = i / this.mDepth;
                else
                    fade = 1.0;
                var red = this.mColorRGB[0] * fade;
                var green = this.mColorRGB[1] * fade;
                var blue = this.mColorRGB[2] * fade;
                var color = "rgb("+red+","+green+","+blue+")";
                brush.strokeStyle = color;
                brush.beginPath();
                if (last_x > x)
                    last_x = 0;
                brush.moveTo(last_x, last_y);
                brush.lineTo(x, y);
                brush.stroke();
            }
            last_x = x;
            last_y = y;
        }

        brush.restore();
        if (this.mCycleSize) {
            this.mCyclePosition = (this.mCyclePosition + 1) % this.mCycleSize;
        }
    };
};
