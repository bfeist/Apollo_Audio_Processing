class NodeNote {
    constructor(node) {
        this.node = node;
        this.sources = [];
        this.destinations = [];
        this.depth = 0;
    };
};

class SignalGraph {
    constructor() {
        this.notes = new Map();
        this.finalized = false;
    };
    
    connect(src, dst) {
        if (src === dst) {
            throw new Error('Cyclical graph.');
        }
        
        let src_note = this.notes.get(src);
        let dst_note = this.notes.get(dst);

        if (this.preceeds(dst_note, src_note)) {
            throw new Error('Cyclical graph.');
        }
        
        if (src_note === undefined) {
            src_note = new NodeNote(src);
            this.notes.set(src, src_note);
        }
        if (dst_note == undefined) {
            dst_note = new NodeNote(dst);
            this.notes.set(dst, dst_note);
        }
        
        if (dst_note.sources.find(n => n.node === src) !== undefined) {
            // These two are already connected.
            return;
        }
        
        //
        // The destination node's depth needs to be adjusted
        // so that it is higher than its new source, and all the
        // destination's destinations need to be adjusted as well.
        //
        this.note_demote(dst_note, src_note.depth + 1);
        
        //
        // If anyone needs the list to be sorted, another finalization
        // pass must be made first.
        //
        this.finalized = false;
    };
    
    //
    // Is X a source of Y? Used for detecting graph cycles.
    //
    preceeds(x_note, y_note) {
        if (x_note === undefined || y_note === undefined) {
            // One or both nodes aren't even in the graph yet,
            // so no.
            return false;
        }
        
        //
        // Recursively check if X is a source of any of Y's source's
        // sources.
        //
        for (let i = 0; i < y_note.sources.length; i++) {
            let y_source = y_note.sources[i];
            let y_source_note = this.notes[y_source];
            
            if (x_note.node === y_source) {
                // X is in one of Y's sources.
                return true;
            }
            if (this.preceeds(x_note, y_source_note)) {
                // X is in one of Y's source's sources
                return true;
            }
        }
        
        return false;
    };
    
    note_demote(node_note, new_min_depth) {
        if (node_note.depth < new_min_depth) {
            node_note.depth = new_min_depth;
        }
        for (let i = 0; i < node_note.destinations.length; i++) {
            let dst_note = this.nodes.get(node_note.destinations[i]);
            this.note_demote(dst_note, new_min_depth + 1);
        }
    };
    
    finalize() {
        if (this.finalized) {
            return;
        }
        
        //
        // Construct a list of all node notes we posess.
        //
        let note_list = [];
        
        for (var note of this.notes.values()) {
            note_list.push(note);
        }
        
        //
        // Sort the list by depth, ascending.
        //
        note_list.sort(function (a, b) {
            return a.depth - b.depth
        });
        
        this.notes_forward = note_list;
        this.finalized = true;
    }
    
    advance() {
        if (!this.finalized)
            this.finalize();
        
        for (let i = 0; i < this.notes_forward.length; i++) {
            let note = this.notes_forward[i];
            note.node.tick();
        }
    };
};