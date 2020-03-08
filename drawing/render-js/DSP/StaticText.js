class StaticText {
    constructor(label, options) {
        this.mLabel = label;
        this.x = options.x || 0;
        this.y = options.y || 0;
        this.mFontStyle = options.font || "12pt Courier Bold";
        this.mFillStyle = options.fill_style || "black";
    };

    display(brush) {
        brush.save();
        brush.translate(this.x, this.y);
        brush.font = this.mFontStyle;
        brush.fillStyle = this.mFillStyle;
        brush.fillText(this.mLabel, 0, 0);
        brush.restore();
    };
};
