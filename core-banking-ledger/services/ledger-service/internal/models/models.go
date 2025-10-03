package models

import (
	"database/sql/driver"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"
)

// AccountType represents the type of account
type AccountType string

const (
	AccountTypeAsset     AccountType = "ASSET"
	AccountTypeLiability AccountType = "LIABILITY"
	AccountTypeEquity    AccountType = "EQUITY"
	AccountTypeRevenue   AccountType = "REVENUE"
	AccountTypeExpense   AccountType = "EXPENSE"
)

// TransactionStatus represents the status of a transaction
type TransactionStatus string

const (
	TransactionStatusPending   TransactionStatus = "PENDING"
	TransactionStatusCommitted TransactionStatus = "COMMITTED"
	TransactionStatusFailed    TransactionStatus = "FAILED"
	TransactionStatusReversed  TransactionStatus = "REVERSED"
)

// EntryType represents the type of journal entry
type EntryType string

const (
	EntryTypeDebit  EntryType = "DEBIT"
	EntryTypeCredit EntryType = "CREDIT"
)

// ReconciliationStatus represents the status of reconciliation
type ReconciliationStatus string

const (
	ReconciliationStatusPending     ReconciliationStatus = "PENDING"
	ReconciliationStatusMatched     ReconciliationStatus = "MATCHED"
	ReconciliationStatusUnmatched   ReconciliationStatus = "UNMATCHED"
	ReconciliationStatusDiscrepancy ReconciliationStatus = "DISCREPANCY"
)

// ChartOfAccounts represents an account in the chart of accounts
type ChartOfAccounts struct {
	ID                uuid.UUID    `json:"id" db:"id"`
	AccountCode       string       `json:"account_code" db:"account_code"`
	AccountName       string       `json:"account_name" db:"account_name"`
	AccountType       AccountType  `json:"account_type" db:"account_type"`
	ParentAccountCode *string      `json:"parent_account_code,omitempty" db:"parent_account_code"`
	IsActive          bool         `json:"is_active" db:"is_active"`
	Currency          string       `json:"currency" db:"currency"`
	Description       *string      `json:"description,omitempty" db:"description"`
	CreatedAt         time.Time    `json:"created_at" db:"created_at"`
	UpdatedAt         time.Time    `json:"updated_at" db:"updated_at"`
	CreatedBy         *string      `json:"created_by,omitempty" db:"created_by"`
}

// AccountBalance represents the current balance of an account
type AccountBalance struct {
	ID                uuid.UUID       `json:"id" db:"id"`
	AccountCode       string          `json:"account_code" db:"account_code"`
	Currency          string          `json:"currency" db:"currency"`
	BalanceAmount     decimal.Decimal `json:"balance_amount" db:"balance_amount"`
	PendingAmount     decimal.Decimal `json:"pending_amount" db:"pending_amount"`
	AvailableAmount   decimal.Decimal `json:"available_amount" db:"available_amount"`
	LastTransactionID *uuid.UUID      `json:"last_transaction_id,omitempty" db:"last_transaction_id"`
	LastUpdated       time.Time       `json:"last_updated" db:"last_updated"`
	VersionNumber     int64           `json:"version_number" db:"version_number"`
}

// Transaction represents a financial transaction
type Transaction struct {
	ID              uuid.UUID         `json:"id" db:"id"`
	TransactionID   string            `json:"transaction_id" db:"transaction_id"`
	Description     string            `json:"description" db:"description"`
	ReferenceNumber *string           `json:"reference_number,omitempty" db:"reference_number"`
	TransactionDate time.Time         `json:"transaction_date" db:"transaction_date"`
	ValueDate       time.Time         `json:"value_date" db:"value_date"`
	Status          TransactionStatus `json:"status" db:"status"`
	TotalAmount     decimal.Decimal   `json:"total_amount" db:"total_amount"`
	Currency        string            `json:"currency" db:"currency"`
	SourceSystem    *string           `json:"source_system,omitempty" db:"source_system"`
	BatchID         *string           `json:"batch_id,omitempty" db:"batch_id"`
	IdempotencyKey  *string           `json:"idempotency_key,omitempty" db:"idempotency_key"`
	CreatedAt       time.Time         `json:"created_at" db:"created_at"`
	UpdatedAt       time.Time         `json:"updated_at" db:"updated_at"`
	CreatedBy       *string           `json:"created_by,omitempty" db:"created_by"`
	ApprovedBy      *string           `json:"approved_by,omitempty" db:"approved_by"`
	ApprovedAt      *time.Time        `json:"approved_at,omitempty" db:"approved_at"`
	CorrelationID   uuid.UUID         `json:"correlation_id" db:"correlation_id"`
	TraceID         *string           `json:"trace_id,omitempty" db:"trace_id"`
	Entries         []TransactionEntry `json:"entries,omitempty"`
}

// TransactionEntry represents a journal entry within a transaction
type TransactionEntry struct {
	ID              uuid.UUID       `json:"id" db:"id"`
	TransactionID   uuid.UUID       `json:"transaction_id" db:"transaction_id"`
	EntrySequence   int             `json:"entry_sequence" db:"entry_sequence"`
	AccountCode     string          `json:"account_code" db:"account_code"`
	EntryType       EntryType       `json:"entry_type" db:"entry_type"`
	Amount          decimal.Decimal `json:"amount" db:"amount"`
	Currency        string          `json:"currency" db:"currency"`
	Description     *string         `json:"description,omitempty" db:"description"`
	ReferenceData   *JSONB          `json:"reference_data,omitempty" db:"reference_data"`
	CreatedAt       time.Time       `json:"created_at" db:"created_at"`
}

// AuditTrail represents an audit log entry
type AuditTrail struct {
	ID             uuid.UUID  `json:"id" db:"id"`
	EventID        string     `json:"event_id" db:"event_id"`
	EventType      string     `json:"event_type" db:"event_type"`
	EntityType     string     `json:"entity_type" db:"entity_type"`
	EntityID       string     `json:"entity_id" db:"entity_id"`
	OldValues      *JSONB     `json:"old_values,omitempty" db:"old_values"`
	NewValues      *JSONB     `json:"new_values,omitempty" db:"new_values"`
	ChangedFields  []string   `json:"changed_fields,omitempty" db:"changed_fields"`
	EventTimestamp time.Time  `json:"event_timestamp" db:"event_timestamp"`
	UserID         *string    `json:"user_id,omitempty" db:"user_id"`
	SessionID      *string    `json:"session_id,omitempty" db:"session_id"`
	IPAddress      *string    `json:"ip_address,omitempty" db:"ip_address"`
	UserAgent      *string    `json:"user_agent,omitempty" db:"user_agent"`
	CorrelationID  *uuid.UUID `json:"correlation_id,omitempty" db:"correlation_id"`
	TraceID        *string    `json:"trace_id,omitempty" db:"trace_id"`
	HashValue      string     `json:"hash_value" db:"hash_value"`
	PreviousHash   *string    `json:"previous_hash,omitempty" db:"previous_hash"`
	MerkleRoot     *string    `json:"merkle_root,omitempty" db:"merkle_root"`
}

// ReconciliationBatch represents a reconciliation batch
type ReconciliationBatch struct {
	ID                     uuid.UUID            `json:"id" db:"id"`
	BatchID                string               `json:"batch_id" db:"batch_id"`
	ReconciliationDate     time.Time            `json:"reconciliation_date" db:"reconciliation_date"`
	StartTime              time.Time            `json:"start_time" db:"start_time"`
	EndTime                *time.Time           `json:"end_time,omitempty" db:"end_time"`
	Status                 ReconciliationStatus `json:"status" db:"status"`
	TotalTransactions      int64                `json:"total_transactions" db:"total_transactions"`
	MatchedTransactions    int64                `json:"matched_transactions" db:"matched_transactions"`
	UnmatchedTransactions  int64                `json:"unmatched_transactions" db:"unmatched_transactions"`
	DiscrepancyAmount      decimal.Decimal      `json:"discrepancy_amount" db:"discrepancy_amount"`
	Currency               string               `json:"currency" db:"currency"`
	CreatedBy              *string              `json:"created_by,omitempty" db:"created_by"`
}

// ReconciliationDetail represents a reconciliation detail
type ReconciliationDetail struct {
	ID                uuid.UUID            `json:"id" db:"id"`
	BatchID           uuid.UUID            `json:"batch_id" db:"batch_id"`
	TransactionID     *uuid.UUID           `json:"transaction_id,omitempty" db:"transaction_id"`
	ExternalReference *string              `json:"external_reference,omitempty" db:"external_reference"`
	AccountCode       *string              `json:"account_code,omitempty" db:"account_code"`
	ExpectedAmount    *decimal.Decimal     `json:"expected_amount,omitempty" db:"expected_amount"`
	ActualAmount      *decimal.Decimal     `json:"actual_amount,omitempty" db:"actual_amount"`
	DifferenceAmount  *decimal.Decimal     `json:"difference_amount,omitempty" db:"difference_amount"`
	Status            ReconciliationStatus `json:"status" db:"status"`
	Notes             *string              `json:"notes,omitempty" db:"notes"`
	ResolvedAt        *time.Time           `json:"resolved_at,omitempty" db:"resolved_at"`
	ResolvedBy        *string              `json:"resolved_by,omitempty" db:"resolved_by"`
	CreatedAt         time.Time            `json:"created_at" db:"created_at"`
}

// IdempotencyKey represents an idempotency key for duplicate prevention
type IdempotencyKey struct {
	KeyValue     string     `json:"key_value" db:"key_value"`
	EntityType   string     `json:"entity_type" db:"entity_type"`
	EntityID     string     `json:"entity_id" db:"entity_id"`
	ResponseData *JSONB     `json:"response_data,omitempty" db:"response_data"`
	CreatedAt    time.Time  `json:"created_at" db:"created_at"`
	ExpiresAt    time.Time  `json:"expires_at" db:"expires_at"`
}

// DistributedLock represents a distributed lock
type DistributedLock struct {
	LockName   string     `json:"lock_name" db:"lock_name"`
	LockOwner  string     `json:"lock_owner" db:"lock_owner"`
	AcquiredAt time.Time  `json:"acquired_at" db:"acquired_at"`
	ExpiresAt  time.Time  `json:"expires_at" db:"expires_at"`
	Metadata   *JSONB     `json:"metadata,omitempty" db:"metadata"`
}

// JSONB represents a PostgreSQL JSONB field
type JSONB map[string]interface{}

// Value implements the driver.Valuer interface
func (j JSONB) Value() (driver.Value, error) {
	if j == nil {
		return nil, nil
	}
	return json.Marshal(j)
}

// Scan implements the sql.Scanner interface
func (j *JSONB) Scan(value interface{}) error {
	if value == nil {
		*j = nil
		return nil
	}

	bytes, ok := value.([]byte)
	if !ok {
		return fmt.Errorf("cannot scan %T into JSONB", value)
	}

	return json.Unmarshal(bytes, j)
}

// CreateTransactionRequest represents a request to create a transaction
type CreateTransactionRequest struct {
	TransactionID   string                      `json:"transaction_id" binding:"required"`
	Description     string                      `json:"description" binding:"required"`
	ReferenceNumber *string                     `json:"reference_number,omitempty"`
	ValueDate       *time.Time                  `json:"value_date,omitempty"`
	Currency        string                      `json:"currency" binding:"required"`
	SourceSystem    *string                     `json:"source_system,omitempty"`
	BatchID         *string                     `json:"batch_id,omitempty"`
	IdempotencyKey  *string                     `json:"idempotency_key,omitempty"`
	Entries         []CreateTransactionEntryRequest `json:"entries" binding:"required,min=2"`
}

// CreateTransactionEntryRequest represents a request to create a transaction entry
type CreateTransactionEntryRequest struct {
	AccountCode   string          `json:"account_code" binding:"required"`
	EntryType     EntryType       `json:"entry_type" binding:"required"`
	Amount        decimal.Decimal `json:"amount" binding:"required"`
	Currency      string          `json:"currency" binding:"required"`
	Description   *string         `json:"description,omitempty"`
	ReferenceData *JSONB          `json:"reference_data,omitempty"`
}

// CreateAccountRequest represents a request to create an account
type CreateAccountRequest struct {
	AccountCode       string      `json:"account_code" binding:"required"`
	AccountName       string      `json:"account_name" binding:"required"`
	AccountType       AccountType `json:"account_type" binding:"required"`
	ParentAccountCode *string     `json:"parent_account_code,omitempty"`
	Currency          string      `json:"currency" binding:"required"`
	Description       *string     `json:"description,omitempty"`
}

// UpdateAccountRequest represents a request to update an account
type UpdateAccountRequest struct {
	AccountName string  `json:"account_name,omitempty"`
	Description *string `json:"description,omitempty"`
	IsActive    *bool   `json:"is_active,omitempty"`
}

// TransferRequest represents a request to transfer funds between accounts
type TransferRequest struct {
	FromAccountCode string          `json:"from_account_code" binding:"required"`
	ToAccountCode   string          `json:"to_account_code" binding:"required"`
	Amount          decimal.Decimal `json:"amount" binding:"required"`
	Currency        string          `json:"currency" binding:"required"`
	Description     string          `json:"description" binding:"required"`
	ReferenceNumber *string         `json:"reference_number,omitempty"`
	IdempotencyKey  *string         `json:"idempotency_key,omitempty"`
}

// BalanceResponse represents a balance response
type BalanceResponse struct {
	AccountCode     string          `json:"account_code"`
	AccountName     string          `json:"account_name"`
	Currency        string          `json:"currency"`
	BalanceAmount   decimal.Decimal `json:"balance_amount"`
	PendingAmount   decimal.Decimal `json:"pending_amount"`
	AvailableAmount decimal.Decimal `json:"available_amount"`
	LastUpdated     time.Time       `json:"last_updated"`
}

// TransactionHistoryResponse represents transaction history
type TransactionHistoryResponse struct {
	Transactions []Transaction `json:"transactions"`
	TotalCount   int64         `json:"total_count"`
	Page         int           `json:"page"`
	PageSize     int           `json:"page_size"`
}

// AuditTrailResponse represents audit trail response
type AuditTrailResponse struct {
	Events     []AuditTrail `json:"events"`
	TotalCount int64        `json:"total_count"`
	Page       int          `json:"page"`
	PageSize   int          `json:"page_size"`
}

// ReconciliationReportResponse represents reconciliation report
type ReconciliationReportResponse struct {
	Batch   ReconciliationBatch    `json:"batch"`
	Details []ReconciliationDetail `json:"details"`
}

// ErrorResponse represents an error response
type ErrorResponse struct {
	Error       string                 `json:"error"`
	Code        string                 `json:"code,omitempty"`
	Details     map[string]interface{} `json:"details,omitempty"`
	Timestamp   time.Time              `json:"timestamp"`
	RequestID   string                 `json:"request_id,omitempty"`
	TraceID     string                 `json:"trace_id,omitempty"`
}

// SuccessResponse represents a success response
type SuccessResponse struct {
	Message   string      `json:"message"`
	Data      interface{} `json:"data,omitempty"`
	Timestamp time.Time   `json:"timestamp"`
	RequestID string      `json:"request_id,omitempty"`
	TraceID   string      `json:"trace_id,omitempty"`
}
