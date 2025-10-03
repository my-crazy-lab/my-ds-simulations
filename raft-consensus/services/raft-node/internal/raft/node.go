package raft

import (
	"context"
	"fmt"
	"log"
	"math/rand"
	"sync"
	"time"

	"../config"
	"../storage"
)

// State represents the current state of a Raft node
type State int

const (
	Follower State = iota
	Candidate
	Leader
)

func (s State) String() string {
	switch s {
	case Follower:
		return "Follower"
	case Candidate:
		return "Candidate"
	case Leader:
		return "Leader"
	default:
		return "Unknown"
	}
}

// LogEntry represents a single entry in the Raft log
type LogEntry struct {
	Term    int64  `json:"term"`
	Index   int64  `json:"index"`
	Command string `json:"command"`
	Data    []byte `json:"data"`
}

// NodeState represents the current state of the node
type NodeState struct {
	State       State
	Term        int64
	LeaderID    string
	CommitIndex int64
	LogLength   int64
}

// Node represents a Raft node
type Node struct {
	mu sync.RWMutex

	// Configuration
	config *config.Config

	// Persistent state
	currentTerm int64
	votedFor    string
	log         []LogEntry

	// Volatile state
	state       State
	leaderID    string
	commitIndex int64
	lastApplied int64

	// Leader state
	nextIndex  map[string]int64
	matchIndex map[string]int64

	// Storage
	storage storage.Storage

	// State machine (simple key-value store)
	stateMachine map[string]string

	// Channels and timers
	electionTimer  *time.Timer
	heartbeatTimer *time.Timer
	stopCh         chan struct{}

	// Peers
	peers map[string]*Peer
}

// Peer represents a peer node in the cluster
type Peer struct {
	ID      string
	Address string
	// Add gRPC client connection here
}

// NewNode creates a new Raft node
func NewNode(cfg *config.Config, storage storage.Storage) (*Node, error) {
	node := &Node{
		config:       cfg,
		storage:      storage,
		state:        Follower,
		stateMachine: make(map[string]string),
		nextIndex:    make(map[string]int64),
		matchIndex:   make(map[string]int64),
		peers:        make(map[string]*Peer),
		stopCh:       make(chan struct{}),
	}

	// Initialize peers
	for nodeID, address := range cfg.GetPeers() {
		node.peers[nodeID] = &Peer{
			ID:      nodeID,
			Address: address,
		}
	}

	// Load persistent state
	if err := node.loadState(); err != nil {
		return nil, fmt.Errorf("failed to load persistent state: %w", err)
	}

	return node, nil
}

// Start starts the Raft node
func (n *Node) Start() error {
	log.Printf("Starting Raft node %s", n.config.NodeID)

	// Start election timer
	n.resetElectionTimer()

	// Start main loop
	go n.run()

	return nil
}

// Stop stops the Raft node
func (n *Node) Stop() {
	log.Printf("Stopping Raft node %s", n.config.NodeID)
	close(n.stopCh)

	if n.electionTimer != nil {
		n.electionTimer.Stop()
	}
	if n.heartbeatTimer != nil {
		n.heartbeatTimer.Stop()
	}
}

// run is the main event loop for the Raft node
func (n *Node) run() {
	for {
		select {
		case <-n.stopCh:
			return
		case <-n.electionTimer.C:
			n.handleElectionTimeout()
		case <-n.heartbeatTimer.C:
			n.handleHeartbeatTimeout()
		}
	}
}

// handleElectionTimeout handles election timeout
func (n *Node) handleElectionTimeout() {
	n.mu.Lock()
	defer n.mu.Unlock()

	if n.state == Leader {
		return
	}

	log.Printf("Node %s: Election timeout, starting election", n.config.NodeID)

	// Become candidate
	n.state = Candidate
	n.currentTerm++
	n.votedFor = n.config.NodeID
	n.leaderID = ""

	// Save state
	n.saveState()

	// Reset election timer
	n.resetElectionTimer()

	// Start election
	go n.startElection()
}

// handleHeartbeatTimeout handles heartbeat timeout (leader only)
func (n *Node) handleHeartbeatTimeout() {
	n.mu.RLock()
	if n.state != Leader {
		n.mu.RUnlock()
		return
	}
	n.mu.RUnlock()

	// Send heartbeats to all peers
	go n.sendHeartbeats()

	// Reset heartbeat timer
	n.resetHeartbeatTimer()
}

// startElection starts a new election
func (n *Node) startElection() {
	n.mu.RLock()
	term := n.currentTerm
	lastLogIndex := int64(len(n.log) - 1)
	lastLogTerm := int64(0)
	if lastLogIndex >= 0 {
		lastLogTerm = n.log[lastLogIndex].Term
	}
	n.mu.RUnlock()

	votes := 1 // Vote for self
	totalNodes := len(n.peers) + 1

	var wg sync.WaitGroup
	var mu sync.Mutex

	// Request votes from all peers
	for peerID := range n.peers {
		wg.Add(1)
		go func(peerID string) {
			defer wg.Done()

			// TODO: Implement RequestVote RPC call
			granted := n.requestVote(peerID, term, lastLogIndex, lastLogTerm)

			mu.Lock()
			if granted {
				votes++
			}
			mu.Unlock()
		}(peerID)
	}

	wg.Wait()

	n.mu.Lock()
	defer n.mu.Unlock()

	// Check if we won the election
	if n.state == Candidate && n.currentTerm == term && votes > totalNodes/2 {
		log.Printf("Node %s: Won election with %d votes", n.config.NodeID, votes)
		n.becomeLeader()
	}
}

// becomeLeader transitions the node to leader state
func (n *Node) becomeLeader() {
	n.state = Leader
	n.leaderID = n.config.NodeID

	// Initialize leader state
	lastLogIndex := int64(len(n.log))
	for peerID := range n.peers {
		n.nextIndex[peerID] = lastLogIndex
		n.matchIndex[peerID] = 0
	}

	log.Printf("Node %s: Became leader for term %d", n.config.NodeID, n.currentTerm)

	// Start sending heartbeats
	n.resetHeartbeatTimer()
	go n.sendHeartbeats()
}

// sendHeartbeats sends heartbeat messages to all peers
func (n *Node) sendHeartbeats() {
	n.mu.RLock()
	if n.state != Leader {
		n.mu.RUnlock()
		return
	}
	term := n.currentTerm
	n.mu.RUnlock()

	var wg sync.WaitGroup

	for peerID := range n.peers {
		wg.Add(1)
		go func(peerID string) {
			defer wg.Done()
			// TODO: Implement AppendEntries RPC call
			n.sendAppendEntries(peerID, term)
		}(peerID)
	}

	wg.Wait()
}

// requestVote sends a RequestVote RPC to a peer
func (n *Node) requestVote(peerID string, term, lastLogIndex, lastLogTerm int64) bool {
	// TODO: Implement actual gRPC call
	// For now, simulate a response
	return rand.Float32() > 0.5
}

// sendAppendEntries sends an AppendEntries RPC to a peer
func (n *Node) sendAppendEntries(peerID string, term int64) bool {
	// TODO: Implement actual gRPC call
	// For now, simulate a response
	return true
}

// resetElectionTimer resets the election timer with a random timeout
func (n *Node) resetElectionTimer() {
	if n.electionTimer != nil {
		n.electionTimer.Stop()
	}

	// Random timeout between 150-300ms (election timeout to 2x election timeout)
	timeout := n.config.ElectionTimeout + time.Duration(rand.Int63n(int64(n.config.ElectionTimeout)))
	n.electionTimer = time.NewTimer(timeout)
}

// resetHeartbeatTimer resets the heartbeat timer
func (n *Node) resetHeartbeatTimer() {
	if n.heartbeatTimer != nil {
		n.heartbeatTimer.Stop()
	}
	n.heartbeatTimer = time.NewTimer(n.config.HeartbeatInterval)
}

// loadState loads persistent state from storage
func (n *Node) loadState() error {
	// TODO: Implement loading from storage
	n.currentTerm = 0
	n.votedFor = ""
	n.log = make([]LogEntry, 0)
	return nil
}

// saveState saves persistent state to storage
func (n *Node) saveState() error {
	// TODO: Implement saving to storage
	return nil
}

// GetState returns the current state of the node
func (n *Node) GetState() NodeState {
	n.mu.RLock()
	defer n.mu.RUnlock()

	return NodeState{
		State:       n.state,
		Term:        n.currentTerm,
		LeaderID:    n.leaderID,
		CommitIndex: n.commitIndex,
		LogLength:   int64(len(n.log)),
	}
}

// GetNodes returns information about all nodes in the cluster
func (n *Node) GetNodes() map[string]interface{} {
	n.mu.RLock()
	defer n.mu.RUnlock()

	nodes := make(map[string]interface{})
	
	// Add current node
	nodes[n.config.NodeID] = map[string]interface{}{
		"id":      n.config.NodeID,
		"address": n.config.NodeAddress,
		"state":   n.state.String(),
		"term":    n.currentTerm,
		"self":    true,
	}

	// Add peer nodes
	for peerID, peer := range n.peers {
		nodes[peerID] = map[string]interface{}{
			"id":      peer.ID,
			"address": peer.Address,
			"state":   "Unknown", // We don't know peer states
			"term":    0,
			"self":    false,
		}
	}

	return nodes
}

// Client API methods

// Get retrieves a value from the state machine
func (n *Node) Get(key string) (string, error) {
	n.mu.RLock()
	defer n.mu.RUnlock()

	value, exists := n.stateMachine[key]
	if !exists {
		return "", fmt.Errorf("key not found: %s", key)
	}

	return value, nil
}

// Put stores a key-value pair (requires consensus)
func (n *Node) Put(key, value string) error {
	n.mu.RLock()
	if n.state != Leader {
		n.mu.RUnlock()
		return fmt.Errorf("not the leader")
	}
	n.mu.RUnlock()

	// TODO: Implement log replication
	// For now, just update the state machine directly
	n.mu.Lock()
	n.stateMachine[key] = value
	n.mu.Unlock()

	return nil
}

// Delete removes a key from the state machine (requires consensus)
func (n *Node) Delete(key string) error {
	n.mu.RLock()
	if n.state != Leader {
		n.mu.RUnlock()
		return fmt.Errorf("not the leader")
	}
	n.mu.RUnlock()

	// TODO: Implement log replication
	// For now, just update the state machine directly
	n.mu.Lock()
	delete(n.stateMachine, key)
	n.mu.Unlock()

	return nil
}

// Admin API methods

// AddNode adds a new node to the cluster
func (n *Node) AddNode(nodeID, address string) error {
	// TODO: Implement membership change
	return fmt.Errorf("membership changes not implemented yet")
}

// RemoveNode removes a node from the cluster
func (n *Node) RemoveNode(nodeID string) error {
	// TODO: Implement membership change
	return fmt.Errorf("membership changes not implemented yet")
}

// TakeSnapshot creates a snapshot of the current state
func (n *Node) TakeSnapshot() error {
	// TODO: Implement snapshotting
	return fmt.Errorf("snapshotting not implemented yet")
}

// CompactLog compacts the log by removing entries before the last snapshot
func (n *Node) CompactLog() error {
	// TODO: Implement log compaction
	return fmt.Errorf("log compaction not implemented yet")
}
