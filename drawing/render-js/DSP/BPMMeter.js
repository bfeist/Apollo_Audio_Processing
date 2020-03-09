class BPMMeter extends SignalNode {
    constructor(src, graph, sample_rate, options) {
        super();
        this.mSource = src;
        this.mSampleRate = sample_rate;

        this.x = options.x || 0;
        this.y = options.y || 0;
        this.mClipMin = options.clip_min || undefined;
        this.mClipMax = options.clip_max || undefined;
        this.mZeroOffset = options.zero_offset || 0.0;
        // The maximum detectable BPM.
        this.mHysteresisBPM = options.hysteresis_bpm || 200.0;
        this.mLossBPM = options.loss_bpm || 30.0;
        this.mHysteresis = this.mSampleRate * 60.0 / this.mHysteresisBPM;
        this.mLosteresis = this.mSampleRate * 60.0 / this.mLossBPM;
        this.mAlpha = options.alpha || 0.90;
        this.mAveragingDepth = options.averaging_depth || 3;
        this.mTriggerLevel = options.trigger_level || -0.05;
        this.mFontStyle = options.font || "12pt Courier";
        this.mFillStyle = options.fill_style || "black";
        this.mTextAlign = options.text_align || "start";

        this.mBeats = [];
        this.mSamplesSinceLastBeat = 0;
        this.mHaveAverage = false;
        this.mBPM = 0.0;
        this.mLevel = 0.0;

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

        //
        // Update overall average level.
        //
        this.mLevel = this.mLevel * this.mAlpha;
        this.mLevel += (1.0 - this.mAlpha) * value;

        this.mSamplesSinceLastBeat += 1;

        if (this.mSamplesSinceLastBeat < this.mHysteresis) {
            //
            // We're holding off on detection because we have recently
            // triggered. Continue to wait.
            //
            return;
        }

        //
        // Examine the new sample. Have we detected a beat?
        //
        var adjusted_value = value - this.mLevel;
        if (adjusted_value >= this.mTriggerLevel) {
            //
            // No, we haven't yet detected a new beat.
            //
            if (this.mSamplesSinceLastBeat > this.mLosteresis) {
                //
                // It appears we've lost some beats. Start decaying.
                //
                this._add_beat_bpm(0.0);
            }
            return;
        }

        //
        // We've detected a new beat!
        // Calculate the period from the last beat.
        //
        var period_s = this.mSamplesSinceLastBeat / this.mSampleRate;
        var bpm = 60.0 / period_s;
        
        this._add_beat_bpm(bpm);
    };

    _add_beat_bpm(bpm) {
        if (this.mBeats.length >= this.mAveragingDepth) {
            this.mBeats.shift();
        }
        this.mBeats.push(bpm);

        if (this.mBeats.length >= this.mAveragingDepth) {
            this.mHaveAverage = true;
            this.mBPM = this.mBeats.reduce((a,b) => a + b, 0) / this.mBeats.length;
        }
        this.mSamplesSinceLastBeat = 0;
    };

    display(brush) {
        // Set up a sprite-like context.
        if (this.mHaveAverage) {
            brush.save();
            brush.translate(this.x, this.y);
            brush.font = this.mFontStyle;
            brush.fillStyle = this.mFillStyle;
            brush.textAlign = this.mTextAlign;
            brush.fillText(this.mBPM.toFixed(0), 0, 0);
            brush.restore();
        }
    };
};
