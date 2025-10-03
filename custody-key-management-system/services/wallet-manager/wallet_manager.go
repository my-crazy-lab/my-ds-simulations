package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/lib/pq"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

// Wallet represents a digital asset wallet
type Wallet struct {
	ID           string    `json:"id" db:"id"`
	WalletType   string    `json:"wallet_type" db:"wallet_type"`
	Blockchain   string    `json:"blockchain" db:"blockchain"`
	Name         string    `json:"name" db:"name"`
	Description  string    `json:"description" db:"description"`
	Threshold    int       `json:"threshold" db:"threshold"`
	TotalSigners int       `json:"total_signers" db:"total_signers"`
	Status       string    `json:"status" db:"status"`
	CreatedAt    time.Time `json:"created_at" db:"created_at"`
	UpdatedAt    time.Time `json:"updated_at" db:"updated_at"`
	CreatedBy    string    `json:"created_by" db:"created_by"`
}

// WalletAddress represents a wallet address
type WalletAddress struct {
	ID             string    `json:"id" db:"id"`
	WalletID       string    `json:"wallet_id" db:"wallet_id"`
	Address        string    `json:"address" db:"address"`
	AddressType    string    `json:"address_type" db:"address_type"`
	DerivationPath string    `json:"derivation_path" db:"derivation_path"`
	PublicKey      string    `json:"public_key" db:"public_key"`
	IsActive       bool      `json:"is_active" db:"is_active"`
	CreatedAt      time.Time `json:"created_at" db:"created_at"`
}

// WalletBalance represents wallet balance information
type WalletBalance struct {
	WalletID      string  `json:"wallet_id" db:"wallet_id"`
	Asset         string  `json:"asset" db:"asset"`
	Balance       string  `json:"balance" db:"balance"`
	LockedBalance string  `json:"locked_balance" db:"locked_balance"`
	LastUpdated   time.Time `json:"last_updated" db:"last_updated"`
}

// CreateWalletRequest represents wallet creation request
type CreateWalletRequest struct {
	WalletType   string `json:"wallet_type" binding:"required"`
	Blockchain   string `json:"blockchain" binding:"required"`
	Name         string `json:"name" binding:"required"`
	Description  string `json:"description"`
	Threshold    int    `json:"threshold"`
	TotalSigners int    `json:"total_signers"`
}

// CreateAddressRequest represents address creation request
type CreateAddressRequest struct {
	AddressType    string `json:"address_type" binding:"required"`
	DerivationPath string `json:"derivation_path"`
}

// WalletManager handles wallet operations
type WalletManager struct {
	db          *sql.DB
	redisClient *redis.Client
	tracer      trace.Tracer
}

// NewWalletManager creates a new wallet manager instance
func NewWalletManager(db *sql.DB, redisClient *redis.Client) *WalletManager {
	tracer := otel.Tracer("wallet-manager")
	return &WalletManager{
		db:          db,
		redisClient: redisClient,
		tracer:      tracer,
	}
}

// CreateWallet creates a new wallet
func (wm *WalletManager) CreateWallet(ctx context.Context, req CreateWalletRequest, userID string) (*Wallet, error) {
	ctx, span := wm.tracer.Start(ctx, "create_wallet")
	defer span.End()

	// Generate wallet ID
	walletID := uuid.New().String()

	// Validate wallet type and blockchain combination
	if err := wm.validateWalletConfig(req.WalletType, req.Blockchain, req.Threshold, req.TotalSigners); err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("invalid wallet configuration: %w", err)
	}

	// Create wallet record
	wallet := &Wallet{
		ID:           walletID,
		WalletType:   req.WalletType,
		Blockchain:   req.Blockchain,
		Name:         req.Name,
		Description:  req.Description,
		Threshold:    req.Threshold,
		TotalSigners: req.TotalSigners,
		Status:       "CREATING",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
		CreatedBy:    userID,
	}

	// Insert wallet into database
	query := `
		INSERT INTO wallets (id, wallet_type, blockchain, name, description, threshold, total_signers, status, created_at, updated_at, created_by)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
	`
	_, err := wm.db.ExecContext(ctx, query,
		wallet.ID, wallet.WalletType, wallet.Blockchain, wallet.Name, wallet.Description,
		wallet.Threshold, wallet.TotalSigners, wallet.Status, wallet.CreatedAt, wallet.UpdatedAt, wallet.CreatedBy,
	)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to create wallet: %w", err)
	}

	// Initialize key generation process
	if err := wm.initiateKeyGeneration(ctx, wallet); err != nil {
		span.RecordError(err)
		// Update wallet status to failed
		wm.updateWalletStatus(ctx, walletID, "FAILED")
		return nil, fmt.Errorf("failed to initiate key generation: %w", err)
	}

	// Cache wallet information
	walletJSON, _ := json.Marshal(wallet)
	wm.redisClient.Set(ctx, fmt.Sprintf("wallet:%s", walletID), walletJSON, time.Hour)

	// Log audit event
	wm.logAuditEvent(ctx, "WALLET_CREATED", walletID, userID, map[string]interface{}{
		"wallet_type": req.WalletType,
		"blockchain":  req.Blockchain,
		"name":        req.Name,
	})

	span.SetAttributes(
		attribute.String("wallet.id", walletID),
		attribute.String("wallet.type", req.WalletType),
		attribute.String("wallet.blockchain", req.Blockchain),
	)

	return wallet, nil
}

// GetWallet retrieves wallet information
func (wm *WalletManager) GetWallet(ctx context.Context, walletID string) (*Wallet, error) {
	ctx, span := wm.tracer.Start(ctx, "get_wallet")
	defer span.End()

	// Try cache first
	cached, err := wm.redisClient.Get(ctx, fmt.Sprintf("wallet:%s", walletID)).Result()
	if err == nil {
		var wallet Wallet
		if json.Unmarshal([]byte(cached), &wallet) == nil {
			return &wallet, nil
		}
	}

	// Query database
	var wallet Wallet
	query := `
		SELECT id, wallet_type, blockchain, name, description, threshold, total_signers, status, created_at, updated_at, created_by
		FROM wallets WHERE id = $1
	`
	err = wm.db.QueryRowContext(ctx, query, walletID).Scan(
		&wallet.ID, &wallet.WalletType, &wallet.Blockchain, &wallet.Name, &wallet.Description,
		&wallet.Threshold, &wallet.TotalSigners, &wallet.Status, &wallet.CreatedAt, &wallet.UpdatedAt, &wallet.CreatedBy,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("wallet not found")
		}
		span.RecordError(err)
		return nil, fmt.Errorf("failed to get wallet: %w", err)
	}

	// Cache result
	walletJSON, _ := json.Marshal(wallet)
	wm.redisClient.Set(ctx, fmt.Sprintf("wallet:%s", walletID), walletJSON, time.Hour)

	return &wallet, nil
}

// CreateAddress creates a new address for a wallet
func (wm *WalletManager) CreateAddress(ctx context.Context, walletID string, req CreateAddressRequest, userID string) (*WalletAddress, error) {
	ctx, span := wm.tracer.Start(ctx, "create_address")
	defer span.End()

	// Verify wallet exists and is active
	wallet, err := wm.GetWallet(ctx, walletID)
	if err != nil {
		return nil, err
	}
	if wallet.Status != "ACTIVE" {
		return nil, fmt.Errorf("wallet is not active")
	}

	// Generate address ID
	addressID := uuid.New().String()

	// Generate derivation path if not provided
	derivationPath := req.DerivationPath
	if derivationPath == "" {
		derivationPath, err = wm.generateDerivationPath(ctx, walletID, wallet.Blockchain)
		if err != nil {
			span.RecordError(err)
			return nil, fmt.Errorf("failed to generate derivation path: %w", err)
		}
	}

	// Generate address and public key
	address, publicKey, err := wm.generateAddress(ctx, walletID, wallet.Blockchain, derivationPath)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to generate address: %w", err)
	}

	// Create address record
	walletAddress := &WalletAddress{
		ID:             addressID,
		WalletID:       walletID,
		Address:        address,
		AddressType:    req.AddressType,
		DerivationPath: derivationPath,
		PublicKey:      publicKey,
		IsActive:       true,
		CreatedAt:      time.Now(),
	}

	// Insert address into database
	query := `
		INSERT INTO wallet_addresses (id, wallet_id, address, address_type, derivation_path, public_key, is_active, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`
	_, err = wm.db.ExecContext(ctx, query,
		walletAddress.ID, walletAddress.WalletID, walletAddress.Address, walletAddress.AddressType,
		walletAddress.DerivationPath, walletAddress.PublicKey, walletAddress.IsActive, walletAddress.CreatedAt,
	)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to create address: %w", err)
	}

	// Log audit event
	wm.logAuditEvent(ctx, "ADDRESS_CREATED", walletID, userID, map[string]interface{}{
		"address_id":      addressID,
		"address":         address,
		"address_type":    req.AddressType,
		"derivation_path": derivationPath,
	})

	span.SetAttributes(
		attribute.String("wallet.id", walletID),
		attribute.String("address.id", addressID),
		attribute.String("address.type", req.AddressType),
	)

	return walletAddress, nil
}

// GetWalletBalance retrieves wallet balance information
func (wm *WalletManager) GetWalletBalance(ctx context.Context, walletID string) ([]WalletBalance, error) {
	ctx, span := wm.tracer.Start(ctx, "get_wallet_balance")
	defer span.End()

	// Try cache first
	cacheKey := fmt.Sprintf("balance:%s", walletID)
	cached, err := wm.redisClient.Get(ctx, cacheKey).Result()
	if err == nil {
		var balances []WalletBalance
		if json.Unmarshal([]byte(cached), &balances) == nil {
			return balances, nil
		}
	}

	// Query database
	query := `
		SELECT wallet_id, asset, balance, locked_balance, last_updated
		FROM wallet_balances WHERE wallet_id = $1 AND balance != '0'
		ORDER BY asset
	`
	rows, err := wm.db.QueryContext(ctx, query, walletID)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to get wallet balance: %w", err)
	}
	defer rows.Close()

	var balances []WalletBalance
	for rows.Next() {
		var balance WalletBalance
		err := rows.Scan(&balance.WalletID, &balance.Asset, &balance.Balance, &balance.LockedBalance, &balance.LastUpdated)
		if err != nil {
			span.RecordError(err)
			continue
		}
		balances = append(balances, balance)
	}

	// Cache result for 5 minutes
	balanceJSON, _ := json.Marshal(balances)
	wm.redisClient.Set(ctx, cacheKey, balanceJSON, 5*time.Minute)

	return balances, nil
}

// Helper functions

func (wm *WalletManager) validateWalletConfig(walletType, blockchain string, threshold, totalSigners int) error {
	// Validate wallet type
	validTypes := map[string]bool{
		"SINGLE_SIG": true,
		"MULTI_SIG":  true,
		"MPC":        true,
		"COLD":       true,
		"HOT":        true,
	}
	if !validTypes[walletType] {
		return fmt.Errorf("invalid wallet type: %s", walletType)
	}

	// Validate blockchain
	validBlockchains := map[string]bool{
		"BITCOIN":  true,
		"ETHEREUM": true,
		"LITECOIN": true,
		"CARDANO":  true,
		"SOLANA":   true,
	}
	if !validBlockchains[blockchain] {
		return fmt.Errorf("invalid blockchain: %s", blockchain)
	}

	// Validate multi-sig parameters
	if walletType == "MULTI_SIG" || walletType == "MPC" {
		if threshold <= 0 || totalSigners <= 0 {
			return fmt.Errorf("threshold and total signers must be positive")
		}
		if threshold > totalSigners {
			return fmt.Errorf("threshold cannot exceed total signers")
		}
		if totalSigners > 15 {
			return fmt.Errorf("maximum 15 signers supported")
		}
	}

	return nil
}

func (wm *WalletManager) initiateKeyGeneration(ctx context.Context, wallet *Wallet) error {
	// This would integrate with the key management service
	// For now, simulate key generation process
	
	// Update wallet status to active after key generation
	go func() {
		time.Sleep(2 * time.Second) // Simulate key generation time
		wm.updateWalletStatus(context.Background(), wallet.ID, "ACTIVE")
	}()

	return nil
}

func (wm *WalletManager) updateWalletStatus(ctx context.Context, walletID, status string) error {
	query := `UPDATE wallets SET status = $1, updated_at = $2 WHERE id = $3`
	_, err := wm.db.ExecContext(ctx, query, status, time.Now(), walletID)
	if err != nil {
		return fmt.Errorf("failed to update wallet status: %w", err)
	}

	// Invalidate cache
	wm.redisClient.Del(ctx, fmt.Sprintf("wallet:%s", walletID))
	return nil
}

func (wm *WalletManager) generateDerivationPath(ctx context.Context, walletID, blockchain string) (string, error) {
	// Get next address index for this wallet
	var addressIndex int
	query := `SELECT COALESCE(MAX(CAST(SPLIT_PART(derivation_path, '/', 6) AS INTEGER)), -1) + 1 FROM wallet_addresses WHERE wallet_id = $1`
	err := wm.db.QueryRowContext(ctx, query, walletID).Scan(&addressIndex)
	if err != nil && err != sql.ErrNoRows {
		return "", err
	}

	// Generate BIP44 derivation path
	var coinType int
	switch blockchain {
	case "BITCOIN":
		coinType = 0
	case "ETHEREUM":
		coinType = 60
	case "LITECOIN":
		coinType = 2
	default:
		coinType = 0
	}

	return fmt.Sprintf("m/44'/%d'/0'/0/%d", coinType, addressIndex), nil
}

func (wm *WalletManager) generateAddress(ctx context.Context, walletID, blockchain, derivationPath string) (string, string, error) {
	// This would integrate with the key management service to derive addresses
	// For now, generate mock addresses
	
	// Generate a mock address based on wallet ID and derivation path
	hash := sha256.Sum256([]byte(walletID + derivationPath))
	
	var address, publicKey string
	switch blockchain {
	case "BITCOIN":
		address = "bc1q" + hex.EncodeToString(hash[:20])
		publicKey = hex.EncodeToString(hash[:33])
	case "ETHEREUM":
		address = "0x" + hex.EncodeToString(hash[:20])
		publicKey = hex.EncodeToString(hash[:33])
	default:
		address = hex.EncodeToString(hash[:20])
		publicKey = hex.EncodeToString(hash[:33])
	}

	return address, publicKey, nil
}

func (wm *WalletManager) logAuditEvent(ctx context.Context, eventType, walletID, userID string, details map[string]interface{}) {
	auditEvent := map[string]interface{}{
		"event_type": eventType,
		"wallet_id":  walletID,
		"user_id":    userID,
		"timestamp":  time.Now().Unix(),
		"details":    details,
	}

	// Send to audit log service (Redis for now)
	eventJSON, _ := json.Marshal(auditEvent)
	wm.redisClient.LPush(ctx, "audit_events", eventJSON)
}

// HTTP handlers

func (wm *WalletManager) createWalletHandler(c *gin.Context) {
	var req CreateWalletRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	userID := c.GetHeader("X-User-ID")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User ID required"})
		return
	}

	wallet, err := wm.CreateWallet(c.Request.Context(), req, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, wallet)
}

func (wm *WalletManager) getWalletHandler(c *gin.Context) {
	walletID := c.Param("walletId")
	
	wallet, err := wm.GetWallet(c.Request.Context(), walletID)
	if err != nil {
		if err.Error() == "wallet not found" {
			c.JSON(http.StatusNotFound, gin.H{"error": "Wallet not found"})
		} else {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}

	c.JSON(http.StatusOK, wallet)
}

func (wm *WalletManager) createAddressHandler(c *gin.Context) {
	walletID := c.Param("walletId")
	
	var req CreateAddressRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	userID := c.GetHeader("X-User-ID")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User ID required"})
		return
	}

	address, err := wm.CreateAddress(c.Request.Context(), walletID, req, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, address)
}

func (wm *WalletManager) getWalletBalanceHandler(c *gin.Context) {
	walletID := c.Param("walletId")
	
	balances, err := wm.GetWalletBalance(c.Request.Context(), walletID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"balances": balances})
}

func (wm *WalletManager) healthCheckHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":    "healthy",
		"service":   "wallet-manager",
		"timestamp": time.Now().Unix(),
	})
}

func main() {
	// Database connection
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://custody_user:secure_custody_pass@localhost:5440/custody_system?sslmode=disable"
	}

	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		log.Fatal("Failed to connect to database:", err)
	}
	defer db.Close()

	// Redis connection
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6386"
	}

	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Fatal("Failed to parse Redis URL:", err)
	}
	redisClient := redis.NewClient(opt)

	// Initialize wallet manager
	walletManager := NewWalletManager(db, redisClient)

	// Setup Gin router
	r := gin.Default()

	// Health check
	r.GET("/health", walletManager.healthCheckHandler)

	// API routes
	api := r.Group("/api/v1")
	{
		api.POST("/wallets", walletManager.createWalletHandler)
		api.GET("/wallets/:walletId", walletManager.getWalletHandler)
		api.POST("/wallets/:walletId/addresses", walletManager.createAddressHandler)
		api.GET("/wallets/:walletId/balance", walletManager.getWalletBalanceHandler)
	}

	// Start server
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Wallet Manager service starting on port %s", port)
	log.Fatal(http.ListenAndServe(":"+port, r))
}
