function rgb_scale(from_rgb_trio, to_rgb_trio, intensity) {
    var i = 1.0 - intensity;
    return [
        (from_rgb_trio[0] * i + to_rgb_trio[0] * intensity),
        (from_rgb_trio[1] * i + to_rgb_trio[1] * intensity),
        (from_rgb_trio[2] * i + to_rgb_trio[2] * intensity)
    ];
};

function rgb_color(trio) {
    return "rgb(" + trio.join(",") + ")";
};

class WaveBuffer extends SignalNode {
    constructor(depth, x_scale, y_scale, src, graph, options) {
        super();
        this.mData = [];
        this.mDepth = depth;
        this.mXScale = x_scale;
        this.mYScale = y_scale;
        this.mSource = src;

        this.mLineWidth = options.line_width || 1;
        this.mLineJoin = options.line_join || "round";
        this.mLineCap = options.line_cap || "round";
        this.mZeroOffset = options.zero_offset || 0.0;
        this.x = options.x || 0;
        this.y = options.y || 0;
        this.mClipMin = options.clip_min || undefined;
        this.mClipMax = options.clip_max || undefined;
        this.mDrawZeroLine = options.draw_zero_line || false;
        this.mCycleSize = options.cycle_size || undefined;
        this.mFade = options.fade || false;
        this.mFadeFromColorRGB = options.fade_from_color_rgb || [0, 0, 0];
        this.mColorRGB = options.color_rgb || [ 0, 255, 0];
        this.mZeroLineColor = options.zero_line_color || "#00ff00";

        if (this.mCycleSize < this.mDepth)
            throw new Error("Depth greater than cycle size.");

        //
        // Determine the X coordinate where the most recent ("live")
        // point should be plotted. In static displays this point will
        // stay put. In live displays it will cycle.
        //
        if (this.mCycleSize) {
            this.mLivePosition = -1;
        } else {
            this.mLivePosition = this.mDepth;
        }

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

        if (this.mCycleSize) {
            this.mLivePosition += 1;
            this.mLivePosition %= this.mCycleSize;
        }
    };
    
    display(brush) {
        // Set up a sprite-like context.
        brush.save();
        brush.translate(this.x, this.y);

        //
        // Establish the line drawing styles.
        //
        brush.lineWidth = this.mLineWidth;
        brush.lineJoin = this.mLineJoin;

        //
        // If the plot should have a zero line, draw it.
        //
        if (this.mDrawZeroLine) {
            brush.beginPath();
            brush.strokeStyle = this.mZeroLineColor;
            brush.moveTo(0, 0);
            brush.lineTo(this.mDepth*this.mXScale, 0);
            brush.stroke();
        }

        //
        // Make plan to draw a path from the current starting position,
        // up to the edge of the display, or the end of data, whichever
        // comes first.
        //
        const predicted_start_x = this.mLivePosition - this.mData.length + 1;
        var stop_at_index;
        if (predicted_start_x < 0) {
            //
            // This drawing will have to be split in two.
            //
            stop_at_index = this.mData.length - this.mLivePosition - 1;
        } else {
            //
            // There's no wrapping. Everything can always be drawn
            // in one swath.
            //
            stop_at_index = this.mData.length;
        }

        //
        // Compute the color(s) involved in the current path.
        //
        var start_intensity, stop_intensity;
        if (this.mFade) {
            //
            // Fading is in effect, set up a gradient which will
            // cover the area being drawn.
            //
            var length = this.mData.length;
            start_intensity = 1.0 - length/this.mDepth;
            stop_intensity = 1.0 - (length-stop_at_index)/this.mDepth;
        } else {
            start_intensity = 1.0;
            stop_intensity = 1.0;
        }

        //
        // Calculate the starting x coordinate.
        //
        var start_x = this.mLivePosition - this.mData.length + 1;
        if (start_x < 0)
            start_x += this.mCycleSize;

        //
        // Finally, draw this path.
        //
        this.draw(brush, start_x, 0, stop_at_index, start_intensity,
            stop_intensity);

        //
        // Finish the remainder of the graph, if we had to stop
        // at a wrapping point.
        //
        if (stop_at_index != this.mData.length) {
            //
            // Drawing has to be continued.
            //
            if (this.mFade) {
                var length = this.mData.length;
                start_intensity = 1.0 - (length-stop_at_index)/this.mDepth;
                stop_intensity = 1.0;
            } else {
                start_intensity = 1.0;
                stop_intensity = 1.0;
            }
            
            this.draw(brush, 0, stop_at_index, this.mData.length,
                start_intensity, stop_intensity);
        }

        brush.restore();
    };
    
    draw(brush, at_x, from_i, to_i, from_intensity, to_intensity) {
        var last_x, last_y;

        //
        // Determine if we need to draw with a gradient or if
        // this can be done as a single color.
        //
        if (from_intensity != to_intensity) {
            //
            // Requires gradient.
            //
            
            // Map out the starting and stoping X position.
            var grad = brush.createLinearGradient(
                (at_x) * this.mXScale,                 // Start X
                0,                                     // Start Y
                (at_x - from_i + to_i) * this.mXScale, // Stop X
                0                                      // Stop Y
            );

            // Establish the start and stop color.
            var start_color = rgb_scale(
                this.mFadeFromColorRGB,
                this.mColorRGB,
                from_intensity
            );
            var stop_color = rgb_scale(
                this.mFadeFromColorRGB,
                this.mColorRGB,
                to_intensity
            );
            
            // Plug in the colors.
            grad.addColorStop(0, rgb_color(start_color));
            grad.addColorStop(1, rgb_color(stop_color));

            // Set up the context to use the gradient.
            brush.strokeStyle = grad;
        } else {
            //
            // No gradient needed. Use single color.
            //
            brush.strokeStyle = rgb_color(this.mColorRGB);
        }

        brush.lineCap = this.mLineCap;

        brush.beginPath();
        for (let i = from_i; i < to_i; i++) {
            var x = (i + at_x - from_i) * this.mXScale;
            var y = this.mData[i]*-this.mYScale;

            if (i == 0) {
                brush.moveTo(x, y);
            } else {
                brush.lineTo(x, y);
            }
        }
        brush.stroke();
    }
};
