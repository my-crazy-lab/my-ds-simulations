// +build integration

package integration

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/stretchr/testify/suite"
)

// PaymentFlowTestSuite contains integration tests for payment processing
type PaymentFlowTestSuite struct {
	suite.Suite
	baseURL    string
	httpClient *http.Client
	apiKey     string
}

// SetupSuite runs before all tests in the suite
func (suite *PaymentFlowTestSuite) SetupSuite() {
	suite.baseURL = "https://localhost:8446/api/v1"
	suite.apiKey = "pk_test_123456789abcdef123456789abcdef12"
	
	// Create HTTP client that accepts self-signed certificates
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	suite.httpClient = &http.Client{
		Transport: tr,
		Timeout:   30 * time.Second,
	}

	// Wait for services to be ready
	suite.waitForServices()
}

// TestPaymentFlowSuite runs the integration test suite
func TestPaymentFlowSuite(t *testing.T) {
	suite.Run(t, new(PaymentFlowTestSuite))
}

// waitForServices waits for all required services to be available
func (suite *PaymentFlowTestSuite) waitForServices() {
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

// makeRequest makes an authenticated HTTP request
func (suite *PaymentFlowTestSuite) makeRequest(method, endpoint string, body interface{}) (*http.Response, error) {
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
	req.Header.Set("Authorization", "Bearer "+suite.apiKey)
	req.Header.Set("X-Request-ID", fmt.Sprintf("test-%d", time.Now().UnixNano()))

	return suite.httpClient.Do(req)
}

// TestCardTokenization tests card tokenization functionality
func (suite *PaymentFlowTestSuite) TestCardTokenization() {
	tokenRequest := map[string]interface{}{
		"card_number":   "4111111111111111", // Test Visa card
		"expiry_month":  "12",
		"expiry_year":   "2025",
		"cardholder_name": "John Doe",
	}

	resp, err := suite.makeRequest("POST", "/tokens", tokenRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusCreated, resp.StatusCode)

	var response map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&response)
	require.NoError(suite.T(), err)

	data, ok := response["data"].(map[string]interface{})
	require.True(suite.T(), ok)

	// Verify token format
	token, ok := data["token"].(string)
	require.True(suite.T(), ok)
	assert.Regexp(suite.T(), `^tok_[A-Za-z0-9]{24}$`, token)

	// Verify card details are masked
	assert.Equal(suite.T(), "1111", data["last_four"])
	assert.Equal(suite.T(), "VISA", data["card_brand"])
	assert.NotContains(suite.T(), response, "card_number") // PAN should not be returned
}

// TestPaymentAuthorization tests payment authorization
func (suite *PaymentFlowTestSuite) TestPaymentAuthorization() {
	// First tokenize a card
	tokenRequest := map[string]interface{}{
		"card_number":  "4111111111111111",
		"expiry_month": "12",
		"expiry_year":  "2025",
	}

	tokenResp, err := suite.makeRequest("POST", "/tokens", tokenRequest)
	require.NoError(suite.T(), err)
	defer tokenResp.Body.Close()

	var tokenResponse map[string]interface{}
	err = json.NewDecoder(tokenResp.Body).Decode(&tokenResponse)
	require.NoError(suite.T(), err)

	tokenData := tokenResponse["data"].(map[string]interface{})
	cardToken := tokenData["token"].(string)

	// Now create payment
	paymentRequest := map[string]interface{}{
		"amount":      "10000", // $100.00
		"currency":    "USD",
		"description": "Test payment",
		"card_token":  cardToken,
		"billing_address": map[string]interface{}{
			"street":  "123 Main St",
			"city":    "New York",
			"state":   "NY",
			"zip":     "10001",
			"country": "US",
		},
	}

	resp, err := suite.makeRequest("POST", "/payments", paymentRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusCreated, resp.StatusCode)

	var response map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&response)
	require.NoError(suite.T(), err)

	data, ok := response["data"].(map[string]interface{})
	require.True(suite.T(), ok)

	// Verify payment details
	paymentID, ok := data["payment_id"].(string)
	require.True(suite.T(), ok)
	assert.Regexp(suite.T(), `^pay_[A-Za-z0-9]{24}$`, paymentID)

	assert.Equal(suite.T(), "AUTHORIZED", data["status"])
	assert.Equal(suite.T(), "10000", data["amount"])
	assert.Equal(suite.T(), "USD", data["currency"])
}

// TestPaymentWithFraudDetection tests fraud detection integration
func (suite *PaymentFlowTestSuite) TestPaymentWithFraudDetection() {
	// Create a high-risk payment (large amount)
	tokenRequest := map[string]interface{}{
		"card_number":  "4111111111111111",
		"expiry_month": "12",
		"expiry_year":  "2025",
	}

	tokenResp, err := suite.makeRequest("POST", "/tokens", tokenRequest)
	require.NoError(suite.T(), err)
	defer tokenResp.Body.Close()

	var tokenResponse map[string]interface{}
	err = json.NewDecoder(tokenResp.Body).Decode(&tokenResponse)
	require.NoError(suite.T(), err)

	tokenData := tokenResponse["data"].(map[string]interface{})
	cardToken := tokenData["token"].(string)

	// High-risk payment
	paymentRequest := map[string]interface{}{
		"amount":      "100000", // $1,000.00 - high amount
		"currency":    "USD",
		"description": "High risk test payment",
		"card_token":  cardToken,
		"billing_address": map[string]interface{}{
			"street":  "123 Fraud St", // Suspicious address
			"city":    "Scam City",
			"state":   "XX",
			"zip":     "00000",
			"country": "US",
		},
	}

	resp, err := suite.makeRequest("POST", "/payments", paymentRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	var response map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&response)
	require.NoError(suite.T(), err)

	data, ok := response["data"].(map[string]interface{})
	require.True(suite.T(), ok)

	// Should have fraud score
	fraudScore, exists := data["fraud_score"]
	assert.True(suite.T(), exists)
	assert.NotNil(suite.T(), fraudScore)

	// May be blocked or require review
	status := data["status"].(string)
	assert.Contains(suite.T(), []string{"AUTHORIZED", "FAILED"}, status)
}

// TestThreeDSecureFlow tests 3D Secure authentication
func (suite *PaymentFlowTestSuite) TestThreeDSecureFlow() {
	// Tokenize card
	tokenRequest := map[string]interface{}{
		"card_number":  "4000000000000002", // 3DS test card
		"expiry_month": "12",
		"expiry_year":  "2025",
	}

	tokenResp, err := suite.makeRequest("POST", "/tokens", tokenRequest)
	require.NoError(suite.T(), err)
	defer tokenResp.Body.Close()

	var tokenResponse map[string]interface{}
	err = json.NewDecoder(tokenResp.Body).Decode(&tokenResponse)
	require.NoError(suite.T(), err)

	tokenData := tokenResponse["data"].(map[string]interface{})
	cardToken := tokenData["token"].(string)

	// Payment with 3DS enabled
	paymentRequest := map[string]interface{}{
		"amount":      "5000",
		"currency":    "USD",
		"description": "3DS test payment",
		"card_token":  cardToken,
		"three_d_secure": map[string]interface{}{
			"enabled":    true,
			"return_url": "https://merchant.com/3ds-return",
		},
		"billing_address": map[string]interface{}{
			"street":  "123 Main St",
			"city":    "New York",
			"state":   "NY",
			"zip":     "10001",
			"country": "US",
		},
	}

	resp, err := suite.makeRequest("POST", "/payments", paymentRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	var response map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&response)
	require.NoError(suite.T(), err)

	data, ok := response["data"].(map[string]interface{})
	require.True(suite.T(), ok)

	// Should have 3DS redirect URL or be authenticated
	threeDSStatus := data["three_ds_status"].(string)
	assert.Contains(suite.T(), []string{"ENROLLED", "AUTHENTICATED", "NOT_ENROLLED"}, threeDSStatus)

	if threeDSStatus == "ENROLLED" {
		// Should have redirect URL
		assert.Contains(suite.T(), data, "three_ds_redirect_url")
	}
}

// TestPaymentCapture tests payment capture
func (suite *PaymentFlowTestSuite) TestPaymentCapture() {
	// First create and authorize a payment
	tokenRequest := map[string]interface{}{
		"card_number":  "4111111111111111",
		"expiry_month": "12",
		"expiry_year":  "2025",
	}

	tokenResp, err := suite.makeRequest("POST", "/tokens", tokenRequest)
	require.NoError(suite.T(), err)
	defer tokenResp.Body.Close()

	var tokenResponse map[string]interface{}
	err = json.NewDecoder(tokenResp.Body).Decode(&tokenResponse)
	require.NoError(suite.T(), err)

	tokenData := tokenResponse["data"].(map[string]interface{})
	cardToken := tokenData["token"].(string)

	paymentRequest := map[string]interface{}{
		"amount":      "7500",
		"currency":    "USD",
		"description": "Capture test payment",
		"card_token":  cardToken,
		"capture":     false, // Authorization only
	}

	paymentResp, err := suite.makeRequest("POST", "/payments", paymentRequest)
	require.NoError(suite.T(), err)
	defer paymentResp.Body.Close()

	var paymentResponse map[string]interface{}
	err = json.NewDecoder(paymentResp.Body).Decode(&paymentResponse)
	require.NoError(suite.T(), err)

	paymentData := paymentResponse["data"].(map[string]interface{})
	paymentID := paymentData["payment_id"].(string)

	// Now capture the payment
	captureRequest := map[string]interface{}{
		"amount": "7500", // Full amount
	}

	captureResp, err := suite.makeRequest("POST", fmt.Sprintf("/payments/%s/capture", paymentID), captureRequest)
	require.NoError(suite.T(), err)
	defer captureResp.Body.Close()

	assert.Equal(suite.T(), http.StatusOK, captureResp.StatusCode)

	var captureResponse map[string]interface{}
	err = json.NewDecoder(captureResp.Body).Decode(&captureResponse)
	require.NoError(suite.T(), err)

	captureData := captureResponse["data"].(map[string]interface{})
	assert.Equal(suite.T(), "CAPTURED", captureData["status"])
}

// TestPaymentRefund tests payment refund
func (suite *PaymentFlowTestSuite) TestPaymentRefund() {
	// Create and capture a payment first
	tokenRequest := map[string]interface{}{
		"card_number":  "4111111111111111",
		"expiry_month": "12",
		"expiry_year":  "2025",
	}

	tokenResp, err := suite.makeRequest("POST", "/tokens", tokenRequest)
	require.NoError(suite.T(), err)
	defer tokenResp.Body.Close()

	var tokenResponse map[string]interface{}
	err = json.NewDecoder(tokenResp.Body).Decode(&tokenResponse)
	require.NoError(suite.T(), err)

	tokenData := tokenResponse["data"].(map[string]interface{})
	cardToken := tokenData["token"].(string)

	paymentRequest := map[string]interface{}{
		"amount":      "6000",
		"currency":    "USD",
		"description": "Refund test payment",
		"card_token":  cardToken,
		"capture":     true, // Auto-capture
	}

	paymentResp, err := suite.makeRequest("POST", "/payments", paymentRequest)
	require.NoError(suite.T(), err)
	defer paymentResp.Body.Close()

	var paymentResponse map[string]interface{}
	err = json.NewDecoder(paymentResp.Body).Decode(&paymentResponse)
	require.NoError(suite.T(), err)

	paymentData := paymentResponse["data"].(map[string]interface{})
	paymentID := paymentData["payment_id"].(string)

	// Wait a moment for capture to complete
	time.Sleep(2 * time.Second)

	// Now refund the payment
	refundRequest := map[string]interface{}{
		"amount": "3000", // Partial refund
		"reason": "Customer request",
	}

	refundResp, err := suite.makeRequest("POST", fmt.Sprintf("/payments/%s/refund", paymentID), refundRequest)
	require.NoError(suite.T(), err)
	defer refundResp.Body.Close()

	assert.Equal(suite.T(), http.StatusCreated, refundResp.StatusCode)

	var refundResponse map[string]interface{}
	err = json.NewDecoder(refundResp.Body).Decode(&refundResponse)
	require.NoError(suite.T(), err)

	refundData := refundResponse["data"].(map[string]interface{})
	refundID, ok := refundData["refund_id"].(string)
	require.True(suite.T(), ok)
	assert.Regexp(suite.T(), `^ref_[A-Za-z0-9]{24}$`, refundID)

	assert.Equal(suite.T(), "3000", refundData["amount"])
	assert.Equal(suite.T(), "USD", refundData["currency"])
}

// TestConcurrentPayments tests concurrent payment processing
func (suite *PaymentFlowTestSuite) TestConcurrentPayments() {
	const numPayments = 10
	const paymentAmount = "1000"

	// Tokenize card first
	tokenRequest := map[string]interface{}{
		"card_number":  "4111111111111111",
		"expiry_month": "12",
		"expiry_year":  "2025",
	}

	tokenResp, err := suite.makeRequest("POST", "/tokens", tokenRequest)
	require.NoError(suite.T(), err)
	defer tokenResp.Body.Close()

	var tokenResponse map[string]interface{}
	err = json.NewDecoder(tokenResp.Body).Decode(&tokenResponse)
	require.NoError(suite.T(), err)

	tokenData := tokenResponse["data"].(map[string]interface{})
	cardToken := tokenData["token"].(string)

	// Channel to collect results
	results := make(chan error, numPayments)

	// Launch concurrent payments
	for i := 0; i < numPayments; i++ {
		go func(index int) {
			paymentRequest := map[string]interface{}{
				"amount":      paymentAmount,
				"currency":    "USD",
				"description": fmt.Sprintf("Concurrent payment %d", index),
				"card_token":  cardToken,
			}

			resp, err := suite.makeRequest("POST", "/payments", paymentRequest)
			if err != nil {
				results <- err
				return
			}
			defer resp.Body.Close()

			if resp.StatusCode != http.StatusCreated {
				results <- fmt.Errorf("unexpected status code: %d", resp.StatusCode)
				return
			}

			results <- nil
		}(i)
	}

	// Wait for all payments to complete
	successCount := 0
	for i := 0; i < numPayments; i++ {
		err := <-results
		if err == nil {
			successCount++
		} else {
			suite.T().Logf("Payment failed: %v", err)
		}
	}

	// At least 80% should succeed
	assert.GreaterOrEqual(suite.T(), successCount, int(float64(numPayments)*0.8))
}

// TestInvalidCardData tests handling of invalid card data
func (suite *PaymentFlowTestSuite) TestInvalidCardData() {
	// Test invalid card number
	tokenRequest := map[string]interface{}{
		"card_number":  "1234567890123456", // Invalid card
		"expiry_month": "12",
		"expiry_year":  "2025",
	}

	resp, err := suite.makeRequest("POST", "/tokens", tokenRequest)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusBadRequest, resp.StatusCode)

	// Test expired card
	expiredTokenRequest := map[string]interface{}{
		"card_number":  "4111111111111111",
		"expiry_month": "01",
		"expiry_year":  "2020", // Expired
	}

	expiredResp, err := suite.makeRequest("POST", "/tokens", expiredTokenRequest)
	require.NoError(suite.T(), err)
	defer expiredResp.Body.Close()

	assert.Equal(suite.T(), http.StatusBadRequest, expiredResp.StatusCode)
}

// TestHealthCheck tests service health endpoints
func (suite *PaymentFlowTestSuite) TestHealthCheck() {
	resp, err := suite.makeRequest("GET", "/../health", nil)
	require.NoError(suite.T(), err)
	defer resp.Body.Close()

	assert.Equal(suite.T(), http.StatusOK, resp.StatusCode)

	var healthResponse map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&healthResponse)
	require.NoError(suite.T(), err)

	assert.Equal(suite.T(), "healthy", healthResponse["status"])
	assert.Equal(suite.T(), "authorization-service", healthResponse["service"])
}
