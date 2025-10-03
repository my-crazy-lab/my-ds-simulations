package storage

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/tecbot/gorocksdb"
)

// Storage interface defines the storage operations for Raft
type Storage interface {
	// Persistent state operations
	GetCurrentTerm() (int64, error)
	SetCurrentTerm(term int64) error
	GetVotedFor() (string, error)
	SetVotedFor(nodeID string) error

	// Log operations
	GetLogEntry(index int64) (*LogEntry, error)
	AppendLogEntry(entry *LogEntry) error
	AppendLogEntries(entries []*LogEntry) error
	GetLogEntries(startIndex, endIndex int64) ([]*LogEntry, error)
	GetLastLogIndex() (int64, error)
	GetLastLogTerm() (int64, error)
	TruncateLog(index int64) error

	// Snapshot operations
	SaveSnapshot(snapshot *Snapshot) error
	LoadSnapshot() (*Snapshot, error)
	GetSnapshotMetadata() (*SnapshotMetadata, error)

	// State machine operations
	ApplyEntry(entry *LogEntry) error
	GetStateMachine() (map[string]string, error)
	SetStateMachine(state map[string]string) error

	// Utility operations
	Sync() error
	Close() error
}

// LogEntry represents a log entry
type LogEntry struct {
	Term    int64  `json:"term"`
	Index   int64  `json:"index"`
	Command string `json:"command"`
	Data    []byte `json:"data"`
}

// Snapshot represents a point-in-time snapshot
type Snapshot struct {
	Metadata    SnapshotMetadata  `json:"metadata"`
	StateMachine map[string]string `json:"state_machine"`
}

// SnapshotMetadata contains metadata about a snapshot
type SnapshotMetadata struct {
	Index int64 `json:"index"`
	Term  int64 `json:"term"`
}

// RocksDBStorage implements Storage using RocksDB
type RocksDBStorage struct {
	db      *gorocksdb.DB
	dataDir string
	walDir  string

	// Column families
	cfState    *gorocksdb.ColumnFamilyHandle
	cfLog      *gorocksdb.ColumnFamilyHandle
	cfSnapshot *gorocksdb.ColumnFamilyHandle
	cfSM       *gorocksdb.ColumnFamilyHandle // State Machine

	// Options
	opts   *gorocksdb.Options
	ropts  *gorocksdb.ReadOptions
	wopts  *gorocksdb.WriteOptions
}

// NewRocksDBStorage creates a new RocksDB storage instance
func NewRocksDBStorage(dataDir, walDir string) (*RocksDBStorage, error) {
	// Create directories if they don't exist
	if err := os.MkdirAll(dataDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create data directory: %w", err)
	}
	if err := os.MkdirAll(walDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create WAL directory: %w", err)
	}

	// Configure RocksDB options
	opts := gorocksdb.NewDefaultOptions()
	opts.SetCreateIfMissing(true)
	opts.SetCreateIfMissingColumnFamilies(true)
	opts.SetWalDir(walDir)

	// Define column families
	cfNames := []string{"default", "state", "log", "snapshot", "statemachine"}
	cfOpts := make([]*gorocksdb.Options, len(cfNames))
	for i := range cfOpts {
		cfOpts[i] = gorocksdb.NewDefaultOptions()
	}

	// Open database with column families
	db, cfHandles, err := gorocksdb.OpenDbColumnFamilies(opts, dataDir, cfNames, cfOpts)
	if err != nil {
		return nil, fmt.Errorf("failed to open RocksDB: %w", err)
	}

	storage := &RocksDBStorage{
		db:         db,
		dataDir:    dataDir,
		walDir:     walDir,
		cfState:    cfHandles[1],
		cfLog:      cfHandles[2],
		cfSnapshot: cfHandles[3],
		cfSM:       cfHandles[4],
		opts:       opts,
		ropts:      gorocksdb.NewDefaultReadOptions(),
		wopts:      gorocksdb.NewDefaultWriteOptions(),
	}

	// Enable WAL sync for durability
	storage.wopts.SetSync(true)

	return storage, nil
}

// Persistent state operations

func (s *RocksDBStorage) GetCurrentTerm() (int64, error) {
	value, err := s.db.GetCF(s.ropts, s.cfState, []byte("current_term"))
	if err != nil {
		return 0, err
	}
	defer value.Free()

	if !value.Exists() {
		return 0, nil
	}

	var term int64
	if err := json.Unmarshal(value.Data(), &term); err != nil {
		return 0, fmt.Errorf("failed to unmarshal current term: %w", err)
	}

	return term, nil
}

func (s *RocksDBStorage) SetCurrentTerm(term int64) error {
	data, err := json.Marshal(term)
	if err != nil {
		return fmt.Errorf("failed to marshal current term: %w", err)
	}

	return s.db.PutCF(s.wopts, s.cfState, []byte("current_term"), data)
}

func (s *RocksDBStorage) GetVotedFor() (string, error) {
	value, err := s.db.GetCF(s.ropts, s.cfState, []byte("voted_for"))
	if err != nil {
		return "", err
	}
	defer value.Free()

	if !value.Exists() {
		return "", nil
	}

	var votedFor string
	if err := json.Unmarshal(value.Data(), &votedFor); err != nil {
		return "", fmt.Errorf("failed to unmarshal voted for: %w", err)
	}

	return votedFor, nil
}

func (s *RocksDBStorage) SetVotedFor(nodeID string) error {
	data, err := json.Marshal(nodeID)
	if err != nil {
		return fmt.Errorf("failed to marshal voted for: %w", err)
	}

	return s.db.PutCF(s.wopts, s.cfState, []byte("voted_for"), data)
}

// Log operations

func (s *RocksDBStorage) GetLogEntry(index int64) (*LogEntry, error) {
	key := fmt.Sprintf("log_%d", index)
	value, err := s.db.GetCF(s.ropts, s.cfLog, []byte(key))
	if err != nil {
		return nil, err
	}
	defer value.Free()

	if !value.Exists() {
		return nil, fmt.Errorf("log entry not found at index %d", index)
	}

	var entry LogEntry
	if err := json.Unmarshal(value.Data(), &entry); err != nil {
		return nil, fmt.Errorf("failed to unmarshal log entry: %w", err)
	}

	return &entry, nil
}

func (s *RocksDBStorage) AppendLogEntry(entry *LogEntry) error {
	key := fmt.Sprintf("log_%d", entry.Index)
	data, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("failed to marshal log entry: %w", err)
	}

	return s.db.PutCF(s.wopts, s.cfLog, []byte(key), data)
}

func (s *RocksDBStorage) AppendLogEntries(entries []*LogEntry) error {
	batch := gorocksdb.NewWriteBatch()
	defer batch.Destroy()

	for _, entry := range entries {
		key := fmt.Sprintf("log_%d", entry.Index)
		data, err := json.Marshal(entry)
		if err != nil {
			return fmt.Errorf("failed to marshal log entry: %w", err)
		}
		batch.PutCF(s.cfLog, []byte(key), data)
	}

	return s.db.Write(s.wopts, batch)
}

func (s *RocksDBStorage) GetLogEntries(startIndex, endIndex int64) ([]*LogEntry, error) {
	entries := make([]*LogEntry, 0, endIndex-startIndex+1)

	for i := startIndex; i <= endIndex; i++ {
		entry, err := s.GetLogEntry(i)
		if err != nil {
			return nil, err
		}
		entries = append(entries, entry)
	}

	return entries, nil
}

func (s *RocksDBStorage) GetLastLogIndex() (int64, error) {
	// Use iterator to find the last log entry
	it := s.db.NewIteratorCF(s.ropts, s.cfLog)
	defer it.Close()

	it.SeekToLast()
	if !it.Valid() {
		return -1, nil // No log entries
	}

	key := string(it.Key().Data())
	var index int64
	if _, err := fmt.Sscanf(key, "log_%d", &index); err != nil {
		return -1, fmt.Errorf("failed to parse log index from key %s: %w", key, err)
	}

	return index, nil
}

func (s *RocksDBStorage) GetLastLogTerm() (int64, error) {
	lastIndex, err := s.GetLastLogIndex()
	if err != nil {
		return 0, err
	}

	if lastIndex == -1 {
		return 0, nil // No log entries
	}

	entry, err := s.GetLogEntry(lastIndex)
	if err != nil {
		return 0, err
	}

	return entry.Term, nil
}

func (s *RocksDBStorage) TruncateLog(index int64) error {
	// Delete all log entries from index onwards
	batch := gorocksdb.NewWriteBatch()
	defer batch.Destroy()

	it := s.db.NewIteratorCF(s.ropts, s.cfLog)
	defer it.Close()

	prefix := fmt.Sprintf("log_%d", index)
	it.Seek([]byte(prefix))

	for it.Valid() {
		key := it.Key()
		var entryIndex int64
		if _, err := fmt.Sscanf(string(key.Data()), "log_%d", &entryIndex); err != nil {
			break
		}

		if entryIndex >= index {
			batch.DeleteCF(s.cfLog, key.Data())
		}

		it.Next()
	}

	return s.db.Write(s.wopts, batch)
}

// Snapshot operations

func (s *RocksDBStorage) SaveSnapshot(snapshot *Snapshot) error {
	data, err := json.Marshal(snapshot)
	if err != nil {
		return fmt.Errorf("failed to marshal snapshot: %w", err)
	}

	key := fmt.Sprintf("snapshot_%d", snapshot.Metadata.Index)
	return s.db.PutCF(s.wopts, s.cfSnapshot, []byte(key), data)
}

func (s *RocksDBStorage) LoadSnapshot() (*Snapshot, error) {
	// Find the latest snapshot
	it := s.db.NewIteratorCF(s.ropts, s.cfSnapshot)
	defer it.Close()

	it.SeekToLast()
	if !it.Valid() {
		return nil, fmt.Errorf("no snapshots found")
	}

	var snapshot Snapshot
	if err := json.Unmarshal(it.Value().Data(), &snapshot); err != nil {
		return nil, fmt.Errorf("failed to unmarshal snapshot: %w", err)
	}

	return &snapshot, nil
}

func (s *RocksDBStorage) GetSnapshotMetadata() (*SnapshotMetadata, error) {
	snapshot, err := s.LoadSnapshot()
	if err != nil {
		return nil, err
	}

	return &snapshot.Metadata, nil
}

// State machine operations

func (s *RocksDBStorage) ApplyEntry(entry *LogEntry) error {
	// Simple key-value operations
	switch entry.Command {
	case "PUT":
		var kv struct {
			Key   string `json:"key"`
			Value string `json:"value"`
		}
		if err := json.Unmarshal(entry.Data, &kv); err != nil {
			return fmt.Errorf("failed to unmarshal PUT command: %w", err)
		}
		return s.db.PutCF(s.wopts, s.cfSM, []byte(kv.Key), []byte(kv.Value))

	case "DELETE":
		var k struct {
			Key string `json:"key"`
		}
		if err := json.Unmarshal(entry.Data, &k); err != nil {
			return fmt.Errorf("failed to unmarshal DELETE command: %w", err)
		}
		return s.db.DeleteCF(s.wopts, s.cfSM, []byte(k.Key))

	default:
		return fmt.Errorf("unknown command: %s", entry.Command)
	}
}

func (s *RocksDBStorage) GetStateMachine() (map[string]string, error) {
	stateMachine := make(map[string]string)

	it := s.db.NewIteratorCF(s.ropts, s.cfSM)
	defer it.Close()

	for it.SeekToFirst(); it.Valid(); it.Next() {
		key := string(it.Key().Data())
		value := string(it.Value().Data())
		stateMachine[key] = value
	}

	return stateMachine, nil
}

func (s *RocksDBStorage) SetStateMachine(state map[string]string) error {
	batch := gorocksdb.NewWriteBatch()
	defer batch.Destroy()

	// Clear existing state machine
	it := s.db.NewIteratorCF(s.ropts, s.cfSM)
	for it.SeekToFirst(); it.Valid(); it.Next() {
		batch.DeleteCF(s.cfSM, it.Key().Data())
	}
	it.Close()

	// Set new state
	for key, value := range state {
		batch.PutCF(s.cfSM, []byte(key), []byte(value))
	}

	return s.db.Write(s.wopts, batch)
}

// Utility operations

func (s *RocksDBStorage) Sync() error {
	return s.db.SyncWAL()
}

func (s *RocksDBStorage) Close() error {
	s.cfState.Destroy()
	s.cfLog.Destroy()
	s.cfSnapshot.Destroy()
	s.cfSM.Destroy()
	s.ropts.Destroy()
	s.wopts.Destroy()
	s.opts.Destroy()
	s.db.Close()
	return nil
}
