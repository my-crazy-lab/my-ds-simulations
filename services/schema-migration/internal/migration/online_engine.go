package migration

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	"github.com/microservices-saga/services/schema-migration/internal/infrastructure"
	"github.com/microservices-saga/services/schema-migration/internal/models"
	"github.com/sirupsen/logrus"
)

// OnlineEngine handles online schema migrations with minimal downtime
type OnlineEngine struct {
	db      *sql.DB
	config  OnlineMigrationConfig
	metrics *infrastructure.Metrics
	logger  *logrus.Logger
}

// OnlineMigrationConfig holds configuration for online migrations
type OnlineMigrationConfig struct {
	ChunkSize           int
	ThrottleDelay       time.Duration
	MaxLag              time.Duration
	ReplicationTimeout  time.Duration
	LockTimeout         time.Duration
	MaxRetries          int
	PerformanceThreshold float64
}

// NewOnlineEngine creates a new online migration engine
func NewOnlineEngine(
	db *sql.DB,
	config OnlineMigrationConfig,
	metrics *infrastructure.Metrics,
	logger *logrus.Logger,
) *OnlineEngine {
	return &OnlineEngine{
		db:      db,
		config:  config,
		metrics: metrics,
		logger:  logger,
	}
}

// ExecuteOnlineMigration executes an online schema migration
func (e *OnlineEngine) ExecuteOnlineMigration(ctx context.Context, migration *models.Migration) error {
	e.logger.Infof("Starting online migration: %s", migration.Name)

	start := time.Now()
	defer func() {
		duration := time.Since(start)
		e.metrics.MigrationDuration.WithLabelValues(migration.Name, "online").Observe(duration.Seconds())
	}()

	// Parse migration type
	migrationType := e.detectMigrationType(migration.UpSQL)

	switch migrationType {
	case "ADD_COLUMN":
		return e.executeAddColumn(ctx, migration)
	case "DROP_COLUMN":
		return e.executeDropColumn(ctx, migration)
	case "ADD_INDEX":
		return e.executeAddIndex(ctx, migration)
	case "DROP_INDEX":
		return e.executeDropIndex(ctx, migration)
	case "MODIFY_COLUMN":
		return e.executeModifyColumn(ctx, migration)
	case "ADD_CONSTRAINT":
		return e.executeAddConstraint(ctx, migration)
	case "DROP_CONSTRAINT":
		return e.executeDropConstraint(ctx, migration)
	default:
		return e.executeGenericMigration(ctx, migration)
	}
}

// executeAddColumn handles adding a new column
func (e *OnlineEngine) executeAddColumn(ctx context.Context, migration *models.Migration) error {
	e.logger.Infof("Executing ADD_COLUMN migration: %s", migration.Name)

	// Step 1: Add column with default value (if specified)
	if err := e.executeSQL(ctx, migration.UpSQL); err != nil {
		return fmt.Errorf("failed to add column: %w", err)
	}

	// Step 2: If there's a default value, backfill existing rows
	if e.hasDefaultValue(migration.UpSQL) {
		if err := e.backfillColumn(ctx, migration); err != nil {
			return fmt.Errorf("failed to backfill column: %w", err)
		}
	}

	e.logger.Infof("ADD_COLUMN migration completed: %s", migration.Name)
	return nil
}

// executeDropColumn handles dropping a column
func (e *OnlineEngine) executeDropColumn(ctx context.Context, migration *models.Migration) error {
	e.logger.Infof("Executing DROP_COLUMN migration: %s", migration.Name)

	// Step 1: Create a view without the column (for gradual rollout)
	tableName, columnName := e.parseDropColumn(migration.UpSQL)
	viewName := fmt.Sprintf("%s_migration_view", tableName)

	// Get all columns except the one being dropped
	columns, err := e.getTableColumns(ctx, tableName)
	if err != nil {
		return fmt.Errorf("failed to get table columns: %w", err)
	}

	var remainingColumns []string
	for _, col := range columns {
		if col != columnName {
			remainingColumns = append(remainingColumns, col)
		}
	}

	// Create view
	createViewSQL := fmt.Sprintf("CREATE OR REPLACE VIEW %s AS SELECT %s FROM %s",
		viewName, strings.Join(remainingColumns, ", "), tableName)

	if err := e.executeSQL(ctx, createViewSQL); err != nil {
		return fmt.Errorf("failed to create migration view: %w", err)
	}

	// Step 2: Wait for applications to switch to using the view
	e.logger.Infof("Migration view created. Applications should switch to using %s", viewName)
	
	// In a real implementation, this would wait for feature flags or manual confirmation
	time.Sleep(30 * time.Second)

	// Step 3: Drop the actual column
	if err := e.executeSQL(ctx, migration.UpSQL); err != nil {
		return fmt.Errorf("failed to drop column: %w", err)
	}

	// Step 4: Drop the migration view
	dropViewSQL := fmt.Sprintf("DROP VIEW IF EXISTS %s", viewName)
	if err := e.executeSQL(ctx, dropViewSQL); err != nil {
		e.logger.Errorf("Failed to drop migration view: %v", err)
		// Don't fail the migration for this
	}

	e.logger.Infof("DROP_COLUMN migration completed: %s", migration.Name)
	return nil
}

// executeAddIndex handles adding an index
func (e *OnlineEngine) executeAddIndex(ctx context.Context, migration *models.Migration) error {
	e.logger.Infof("Executing ADD_INDEX migration: %s", migration.Name)

	// Add CONCURRENTLY keyword for PostgreSQL to avoid locking
	sql := strings.Replace(migration.UpSQL, "CREATE INDEX", "CREATE INDEX CONCURRENTLY", 1)

	// Execute with extended timeout for large tables
	ctx, cancel := context.WithTimeout(ctx, e.config.ReplicationTimeout)
	defer cancel()

	if err := e.executeSQL(ctx, sql); err != nil {
		return fmt.Errorf("failed to create index: %w", err)
	}

	e.logger.Infof("ADD_INDEX migration completed: %s", migration.Name)
	return nil
}

// executeDropIndex handles dropping an index
func (e *OnlineEngine) executeDropIndex(ctx context.Context, migration *models.Migration) error {
	e.logger.Infof("Executing DROP_INDEX migration: %s", migration.Name)

	// Add CONCURRENTLY keyword for PostgreSQL
	sql := strings.Replace(migration.UpSQL, "DROP INDEX", "DROP INDEX CONCURRENTLY", 1)

	if err := e.executeSQL(ctx, sql); err != nil {
		return fmt.Errorf("failed to drop index: %w", err)
	}

	e.logger.Infof("DROP_INDEX migration completed: %s", migration.Name)
	return nil
}

// executeModifyColumn handles modifying a column (complex operation)
func (e *OnlineEngine) executeModifyColumn(ctx context.Context, migration *models.Migration) error {
	e.logger.Infof("Executing MODIFY_COLUMN migration: %s", migration.Name)

	// This is a complex operation that requires:
	// 1. Create new column with new type
	// 2. Backfill data with conversion
	// 3. Create triggers to keep both columns in sync
	// 4. Switch applications to use new column
	// 5. Drop old column

	tableName, oldColumn, newColumn := e.parseModifyColumn(migration.UpSQL)

	// Step 1: Add new column
	addColumnSQL := fmt.Sprintf("ALTER TABLE %s ADD COLUMN %s", tableName, newColumn)
	if err := e.executeSQL(ctx, addColumnSQL); err != nil {
		return fmt.Errorf("failed to add new column: %w", err)
	}

	// Step 2: Backfill data
	if err := e.backfillModifiedColumn(ctx, tableName, oldColumn, newColumn); err != nil {
		return fmt.Errorf("failed to backfill modified column: %w", err)
	}

	// Step 3: Create triggers to keep columns in sync
	if err := e.createSyncTriggers(ctx, tableName, oldColumn, newColumn); err != nil {
		return fmt.Errorf("failed to create sync triggers: %w", err)
	}

	e.logger.Infof("MODIFY_COLUMN migration phase 1 completed: %s", migration.Name)
	e.logger.Infof("Applications should now switch to use the new column")

	return nil
}

// executeAddConstraint handles adding constraints
func (e *OnlineEngine) executeAddConstraint(ctx context.Context, migration *models.Migration) error {
	e.logger.Infof("Executing ADD_CONSTRAINT migration: %s", migration.Name)

	// For foreign key constraints, add them as NOT VALID first, then validate
	if strings.Contains(strings.ToUpper(migration.UpSQL), "FOREIGN KEY") {
		// Add constraint as NOT VALID
		notValidSQL := strings.Replace(migration.UpSQL, ";", " NOT VALID;", 1)
		if err := e.executeSQL(ctx, notValidSQL); err != nil {
			return fmt.Errorf("failed to add constraint as NOT VALID: %w", err)
		}

		// Validate constraint (this can take time but doesn't block writes)
		constraintName := e.extractConstraintName(migration.UpSQL)
		tableName := e.extractTableName(migration.UpSQL)
		validateSQL := fmt.Sprintf("ALTER TABLE %s VALIDATE CONSTRAINT %s", tableName, constraintName)
		
		if err := e.executeSQL(ctx, validateSQL); err != nil {
			return fmt.Errorf("failed to validate constraint: %w", err)
		}
	} else {
		// For other constraints, execute directly
		if err := e.executeSQL(ctx, migration.UpSQL); err != nil {
			return fmt.Errorf("failed to add constraint: %w", err)
		}
	}

	e.logger.Infof("ADD_CONSTRAINT migration completed: %s", migration.Name)
	return nil
}

// executeDropConstraint handles dropping constraints
func (e *OnlineEngine) executeDropConstraint(ctx context.Context, migration *models.Migration) error {
	e.logger.Infof("Executing DROP_CONSTRAINT migration: %s", migration.Name)

	if err := e.executeSQL(ctx, migration.UpSQL); err != nil {
		return fmt.Errorf("failed to drop constraint: %w", err)
	}

	e.logger.Infof("DROP_CONSTRAINT migration completed: %s", migration.Name)
	return nil
}

// executeGenericMigration handles generic migrations
func (e *OnlineEngine) executeGenericMigration(ctx context.Context, migration *models.Migration) error {
	e.logger.Infof("Executing generic migration: %s", migration.Name)

	// For generic migrations, we need to be more careful
	// Check if the migration might cause locks
	if e.mightCauseLocks(migration.UpSQL) {
		e.logger.Warnf("Migration might cause locks, consider breaking it down: %s", migration.Name)
	}

	if err := e.executeSQL(ctx, migration.UpSQL); err != nil {
		return fmt.Errorf("failed to execute migration: %w", err)
	}

	e.logger.Infof("Generic migration completed: %s", migration.Name)
	return nil
}

// backfillColumn backfills a column with default values
func (e *OnlineEngine) backfillColumn(ctx context.Context, migration *models.Migration) error {
	tableName := e.extractTableName(migration.UpSQL)
	
	// Get total row count
	var totalRows int64
	err := e.db.QueryRowContext(ctx, fmt.Sprintf("SELECT COUNT(*) FROM %s", tableName)).Scan(&totalRows)
	if err != nil {
		return fmt.Errorf("failed to get row count: %w", err)
	}

	if totalRows == 0 {
		return nil // No rows to backfill
	}

	e.logger.Infof("Backfilling %d rows in table %s", totalRows, tableName)

	// Process in chunks
	offset := int64(0)
	for offset < totalRows {
		// Check performance impact
		if err := e.checkPerformanceImpact(ctx); err != nil {
			e.logger.Warnf("Performance impact detected, throttling: %v", err)
			time.Sleep(e.config.ThrottleDelay)
		}

		// Process chunk
		chunkSize := int64(e.config.ChunkSize)
		if offset+chunkSize > totalRows {
			chunkSize = totalRows - offset
		}

		if err := e.processBackfillChunk(ctx, tableName, offset, chunkSize); err != nil {
			return fmt.Errorf("failed to process backfill chunk: %w", err)
		}

		offset += chunkSize
		
		// Progress reporting
		progress := float64(offset) / float64(totalRows) * 100
		e.metrics.MigrationProgress.WithLabelValues(migration.Name).Set(progress)
		
		e.logger.Debugf("Backfill progress: %.2f%% (%d/%d)", progress, offset, totalRows)

		// Throttle to avoid overwhelming the database
		time.Sleep(e.config.ThrottleDelay)
	}

	return nil
}

// Helper methods (simplified implementations)

func (e *OnlineEngine) detectMigrationType(sql string) string {
	upperSQL := strings.ToUpper(sql)
	if strings.Contains(upperSQL, "ADD COLUMN") {
		return "ADD_COLUMN"
	}
	if strings.Contains(upperSQL, "DROP COLUMN") {
		return "DROP_COLUMN"
	}
	if strings.Contains(upperSQL, "CREATE INDEX") {
		return "ADD_INDEX"
	}
	if strings.Contains(upperSQL, "DROP INDEX") {
		return "DROP_INDEX"
	}
	if strings.Contains(upperSQL, "ALTER COLUMN") {
		return "MODIFY_COLUMN"
	}
	if strings.Contains(upperSQL, "ADD CONSTRAINT") {
		return "ADD_CONSTRAINT"
	}
	if strings.Contains(upperSQL, "DROP CONSTRAINT") {
		return "DROP_CONSTRAINT"
	}
	return "GENERIC"
}

func (e *OnlineEngine) executeSQL(ctx context.Context, sql string) error {
	_, err := e.db.ExecContext(ctx, sql)
	return err
}

func (e *OnlineEngine) hasDefaultValue(sql string) bool {
	return strings.Contains(strings.ToUpper(sql), "DEFAULT")
}

func (e *OnlineEngine) parseDropColumn(sql string) (string, string) {
	// Simplified parsing - in production, use proper SQL parser
	return "table_name", "column_name"
}

func (e *OnlineEngine) getTableColumns(ctx context.Context, tableName string) ([]string, error) {
	// Implementation would query information_schema
	return []string{"id", "name", "email"}, nil
}

func (e *OnlineEngine) parseModifyColumn(sql string) (string, string, string) {
	// Simplified parsing
	return "table_name", "old_column", "new_column"
}

func (e *OnlineEngine) backfillModifiedColumn(ctx context.Context, tableName, oldColumn, newColumn string) error {
	// Implementation would copy and convert data from old to new column
	return nil
}

func (e *OnlineEngine) createSyncTriggers(ctx context.Context, tableName, oldColumn, newColumn string) error {
	// Implementation would create triggers to keep columns in sync
	return nil
}

func (e *OnlineEngine) extractConstraintName(sql string) string {
	// Simplified extraction
	return "constraint_name"
}

func (e *OnlineEngine) extractTableName(sql string) string {
	// Simplified extraction
	return "table_name"
}

func (e *OnlineEngine) mightCauseLocks(sql string) bool {
	upperSQL := strings.ToUpper(sql)
	lockingOperations := []string{
		"ALTER TABLE",
		"CREATE TABLE",
		"DROP TABLE",
		"TRUNCATE",
	}
	
	for _, op := range lockingOperations {
		if strings.Contains(upperSQL, op) {
			return true
		}
	}
	
	return false
}

func (e *OnlineEngine) checkPerformanceImpact(ctx context.Context) error {
	// Implementation would check database performance metrics
	return nil
}

func (e *OnlineEngine) processBackfillChunk(ctx context.Context, tableName string, offset, chunkSize int64) error {
	// Implementation would process a chunk of rows for backfill
	return nil
}
