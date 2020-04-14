//
// Abstract base class for signal consuming and producing
// nodes.
//
class SignalNode {
    constructor() {  
    };
    
    tick() {
        //
        // All source nodes to this node have updated. Pull
        // a new input from any sources, if needed.
        //
        return;
    };
}