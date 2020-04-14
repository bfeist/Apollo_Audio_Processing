class ArrayWaveSource extends SignalNode {
    constructor(data) {
        super();
        this.mData = data;
        this.mOffset = -1;
    };

    value() {
        return this.mData[this.mOffset];
    };
    
    tick() {
        this.mOffset = (this.mOffset + 1) % this.mData.length;
    };
}
