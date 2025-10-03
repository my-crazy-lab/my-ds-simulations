// +build integration

package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/stretchr/testify/suite"
)

// LedgerIntegrationTestSuite contains integration tests for the ledger system
type LedgerIntegrationTestSuite struct {
	suite.Suite
	baseURL    string
	httpClient *http.Client
}

// SetupSuite runs before all tests in the suite
func (suite *LedgerIntegrationTestSuite) SetupSuite() {
	suite.baseURL = "http://localhost:8080/api/v1"
	suite.httpClient = &http.Client{
		Timeout: 30 * time.Second,
	}

	// Wait for services to be ready
	suite.waitForServices()
}

// TestLedgerIntegrationSuite runs the integration test suite
func TestLedgerIntegrationSuite(t *testing.T) {
	suite.Run(t, new(LedgerIntegrationTestSuite))
}

// waitForServices waits for all required services to be available
func (suite *LedgerIntegrationTestSuite) waitForServices() {
	maxRetries := 30
	retryInterval := 2 * time.Second

	for i := 0; i < maxRetries; i++ {
		resp, err := suite.httpClient.Get(suite.baseURL + "/../health")
		if err == nil && resp.StatusCode == http.StatusOK {
			resp.Body.Close()
			return
		}
		if resp != nil {
			resp.Body.Close()
		}
		time.Sleep(retryInterval)
	}

	suite.T().Fatal("Services did not become available within timeout")
}

// makeRequest makes an HTTP request and returns the response
func (suite *LedgerIntegrationTestSuite) makeRequest(method, endpoint string, body interface{}) (*http.Response, error) {
	var reqBody bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&reqBody).Encode(body); err != nil {
			return nil, err
		}
	}

	req, err := http.NewRequest(method, suite.baseURL+endpoint, &reqBody)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Request-ID", fmt.Sprintf("test-%d", time.Now().UnixNano()))

	return suite.httpClient.Do(req)
}

// TestAccountCreation tests account creation functionality
func (suite *LedgerIntegrationTestSuite) TestAccountCreation() {
	// Test data
	accountRequest := map[string]interface{}{
		"account_code": "TEST-001",
		"account_name": "Test Account",
		"account_type": "ASSET",
		"currency":     "USD",
		"description":  "Test account for integration testing",
	}

	// Create account
	resp, err := suite.makeRequest("POST", "/accounts", accountRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusCreated, resp.StatusCode)

	// Verify account was created
	var response map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&response)
	require.NoError(suite.T(), err)

	data, ok := response["data"].(map[string]interface{})
	require.True(suite.T(), ok)
	assert.Equal(suite.T(), "TEST-001", data["account_code"])
	assert.Equal(suite.T(), "Test Account", data["account_name"])
	assert.Equal(suite.T(), "ASSET", data["account_type"])
}

// TestDuplicateAccountCreation tests duplicate account prevention
func (suite *LedgerIntegrationTestSuite) TestDuplicateAccountCreation() {
	accountRequest := map[string]interface{}{
		"account_code": "TEST-DUP",
		"account_name": "Duplicate Test Account",
		"account_type": "ASSET",
		"currency":     "USD",
	}

	// Create account first time
	resp, err := suite.makeRequest("POST", "/accounts", accountRequest)
	require.NoError(suite.T(), err)
	resp.Body.Close()
	assert.Equal(suite.T(), http.StatusCreated, resp.StatusCode)

	// Try to create same account again
	resp, err = suite.makeRequest("POST", "/accounts", accountRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusConflict, resp.StatusCode)
}

// TestTransactionCreation tests transaction creation with double-entry validation
func (suite *LedgerIntegrationTestSuite) TestTransactionCreation() {
	// First create test accounts
	accounts := []map[string]interface{}{
		{
			"account_code": "CASH-TEST",
			"account_name": "Test Cash Account",
			"account_type": "ASSET",
			"currency":     "USD",
		},
		{
			"account_code": "DEPOSIT-TEST",
			"account_name": "Test Deposit Account",
			"account_type": "LIABILITY",
			"currency":     "USD",
		},
	}

	for _, account := range accounts {
		resp, err := suite.makeRequest("POST", "/accounts", account)
		require.NoError(suite.T(), err)
		resp.Body.Close()
	}

	// Create transaction
	transactionRequest := map[string]interface{}{
		"transaction_id": "TXN-TEST-001",
		"description":    "Test customer deposit",
		"currency":       "USD",
		"entries": []map[string]interface{}{
			{
				"account_code": "CASH-TEST",
				"entry_type":   "DEBIT",
				"amount":       "1000.00",
				"currency":     "USD",
				"description":  "Cash received",
			},
			{
				"account_code": "DEPOSIT-TEST",
				"entry_type":   "CREDIT",
				"amount":       "1000.00",
				"currency":     "USD",
				"description":  "Customer deposit",
			},
		},
	}

	resp, err := suite.makeRequest("POST", "/transactions", transactionRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusCreated, resp.StatusCode)

	var response map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&response)
	require.NoError(suite.T(), err)

	data, ok := response["data"].(map[string]interface{})
	require.True(suite.T(), ok)
	assert.Equal(suite.T(), "TXN-TEST-001", data["transaction_id"])
	assert.Equal(suite.T(), "COMMITTED", data["status"])
}

// TestUnbalancedTransaction tests that unbalanced transactions are rejected
func (suite *LedgerIntegrationTestSuite) TestUnbalancedTransaction() {
	transactionRequest := map[string]interface{}{
		"transaction_id": "TXN-UNBALANCED",
		"description":    "Unbalanced transaction test",
		"currency":       "USD",
		"entries": []map[string]interface{}{
			{
				"account_code": "CASH-TEST",
				"entry_type":   "DEBIT",
				"amount":       "1000.00",
				"currency":     "USD",
			},
			{
				"account_code": "DEPOSIT-TEST",
				"entry_type":   "CREDIT",
				"amount":       "500.00", // Unbalanced!
				"currency":     "USD",
			},
		},
	}

	resp, err := suite.makeRequest("POST", "/transactions", transactionRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusBadRequest, resp.StatusCode)
}

// TestBalanceCalculation tests account balance calculation
func (suite *LedgerIntegrationTestSuite) TestBalanceCalculation() {
	// Get initial balance
	resp, err := suite.makeRequest("GET", "/accounts/CASH-TEST/balance", nil)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusOK, resp.StatusCode)

	var balanceResponse map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&balanceResponse)
	require.NoError(suite.T(), err)

	data, ok := balanceResponse["data"].(map[string]interface{})
	require.True(suite.T(), ok)

	// Balance should be 1000.00 from previous test
	balanceStr, ok := data["balance_amount"].(string)
	require.True(suite.T(), ok)
	balance, err := decimal.NewFromString(balanceStr)
	require.NoError(suite.T(), err)
	assert.True(suite.T(), balance.Equal(decimal.NewFromFloat(1000.00)))
}

// TestIdempotency tests idempotent transaction processing
func (suite *LedgerIntegrationTestSuite) TestIdempotency() {
	idempotencyKey := fmt.Sprintf("test-idempotency-%d", time.Now().UnixNano())

	transactionRequest := map[string]interface{}{
		"transaction_id":  "TXN-IDEMPOTENT",
		"description":     "Idempotency test transaction",
		"currency":        "USD",
		"idempotency_key": idempotencyKey,
		"entries": []map[string]interface{}{
			{
				"account_code": "CASH-TEST",
				"entry_type":   "DEBIT",
				"amount":       "500.00",
				"currency":     "USD",
			},
			{
				"account_code": "DEPOSIT-TEST",
				"entry_type":   "CREDIT",
				"amount":       "500.00",
				"currency":     "USD",
			},
		},
	}

	// First request
	resp1, err := suite.makeRequest("POST", "/transactions", transactionRequest)
	require.NoError(suite.T(), err)
	resp1.Body.Close()
	assert.Equal(suite.T(), http.StatusCreated, resp1.StatusCode)

	// Second request with same idempotency key
	resp2, err := suite.makeRequest("POST", "/transactions", transactionRequest)
	require.NoError(suite.T(), err)
	resp2.Body.Close()
	assert.Equal(suite.T(), http.StatusOK, resp2.StatusCode) // Should return existing transaction
}

// TestTransactionReversal tests transaction reversal functionality
func (suite *LedgerIntegrationTestSuite) TestTransactionReversal() {
	// Create a transaction to reverse
	transactionRequest := map[string]interface{}{
		"transaction_id": "TXN-TO-REVERSE",
		"description":    "Transaction to be reversed",
		"currency":       "USD",
		"entries": []map[string]interface{}{
			{
				"account_code": "CASH-TEST",
				"entry_type":   "DEBIT",
				"amount":       "250.00",
				"currency":     "USD",
			},
			{
				"account_code": "DEPOSIT-TEST",
				"entry_type":   "CREDIT",
				"amount":       "250.00",
				"currency":     "USD",
			},
		},
	}

	resp, err := suite.makeRequest("POST", "/transactions", transactionRequest)
	require.NoError(suite.T(), err)
	resp.Body.Close()
	assert.Equal(suite.T(), http.StatusCreated, resp.StatusCode)

	// Reverse the transaction
	reversalRequest := map[string]interface{}{
		"reason": "Test reversal",
	}

	resp, err = suite.makeRequest("POST", "/transactions/TXN-TO-REVERSE/reverse", reversalRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusOK, resp.StatusCode)
}

// TestConcurrentTransactions tests concurrent transaction processing
func (suite *LedgerIntegrationTestSuite) TestConcurrentTransactions() {
	const numTransactions = 10
	const transactionAmount = "100.00"

	// Channel to collect results
	results := make(chan error, numTransactions)

	// Launch concurrent transactions
	for i := 0; i < numTransactions; i++ {
		go func(index int) {
			transactionRequest := map[string]interface{}{
				"transaction_id": fmt.Sprintf("TXN-CONCURRENT-%d", index),
				"description":    fmt.Sprintf("Concurrent transaction %d", index),
				"currency":       "USD",
				"entries": []map[string]interface{}{
					{
						"account_code": "CASH-TEST",
						"entry_type":   "DEBIT",
						"amount":       transactionAmount,
						"currency":     "USD",
					},
					{
						"account_code": "DEPOSIT-TEST",
						"entry_type":   "CREDIT",
						"amount":       transactionAmount,
						"currency":     "USD",
					},
				},
			}

			resp, err := suite.makeRequest("POST", "/transactions", transactionRequest)
			if err != nil {
				results <- err
				return
			}
			resp.Body.Close()

			if resp.StatusCode != http.StatusCreated {
				results <- fmt.Errorf("unexpected status code: %d", resp.StatusCode)
				return
			}

			results <- nil
		}(i)
	}

	// Wait for all transactions to complete
	for i := 0; i < numTransactions; i++ {
		err := <-results
		assert.NoError(suite.T(), err)
	}
}

// TestAuditTrail tests audit trail functionality
func (suite *LedgerIntegrationTestSuite) TestAuditTrail() {
	// Get audit trail for a transaction
	resp, err := suite.makeRequest("GET", "/audit/trail/TXN-TEST-001", nil)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusOK, resp.StatusCode)

	var auditResponse map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&auditResponse)
	require.NoError(suite.T(), err)

	data, ok := auditResponse["data"].(map[string]interface{})
	require.True(suite.T(), ok)

	events, ok := data["events"].([]interface{})
	require.True(suite.T(), ok)
	assert.Greater(suite.T(), len(events), 0)
}

// TestReconciliation tests reconciliation functionality
func (suite *LedgerIntegrationTestSuite) TestReconciliation() {
	// Trigger reconciliation
	reconciliationRequest := map[string]interface{}{
		"reconciliation_date": time.Now().Format("2006-01-02"),
	}

	resp, err := suite.makeRequest("POST", "/admin/reconcile", reconciliationRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusOK, resp.StatusCode)

	var response map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&response)
	require.NoError(suite.T(), err)

	data, ok := response["data"].(map[string]interface{})
	require.True(suite.T(), ok)

	batchID, ok := data["batch_id"].(string)
	require.True(suite.T(), ok)
	assert.NotEmpty(suite.T(), batchID)
}

// TestHealthCheck tests service health endpoints
func (suite *LedgerIntegrationTestSuite) TestHealthCheck() {
	resp, err := suite.makeRequest("GET", "/../health", nil)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusOK, resp.StatusCode)

	var healthResponse map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&healthResponse)
	require.NoError(suite.T(), err)

	assert.Equal(suite.T(), "healthy", healthResponse["status"])
	assert.Equal(suite.T(), "ledger-service", healthResponse["service"])
}

// TestMetrics tests metrics endpoint
func (suite *LedgerIntegrationTestSuite) TestMetrics() {
	resp, err := suite.makeRequest("GET", "/admin/metrics", nil)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusOK, resp.StatusCode)

	var metricsResponse map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&metricsResponse)
	require.NoError(suite.T(), err)

	// Should contain transaction metrics
	assert.Contains(suite.T(), metricsResponse, "transactions_total")
	assert.Contains(suite.T(), metricsResponse, "accounts_total")
}
