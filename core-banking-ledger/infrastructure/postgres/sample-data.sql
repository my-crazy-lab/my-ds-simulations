-- Sample Data for Core Banking Ledger System
-- This creates a realistic chart of accounts and sample transactions

-- Insert Chart of Accounts (Standard Banking Chart)
INSERT INTO chart_of_accounts (account_code, account_name, account_type, parent_account_code, currency, description) VALUES
-- Assets (1000-1999)
('1000', 'ASSETS', 'ASSET', NULL, 'USD', 'Total Assets'),
('1100', 'Current Assets', 'ASSET', '1000', 'USD', 'Current Assets'),
('1101', 'Cash - Main Vault', 'ASSET', '1100', 'USD', 'Primary cash account'),
('1102', 'Cash - ATM Network', 'ASSET', '1100', 'USD', 'ATM cash reserves'),
('1103', 'Cash - Teller Stations', 'ASSET', '1100', 'USD', 'Teller cash drawers'),
('1200', 'Deposits with Central Bank', 'ASSET', '1100', 'USD', 'Required reserves'),
('1300', 'Interbank Deposits', 'ASSET', '1100', 'USD', 'Deposits with other banks'),
('1400', 'Customer Loans', 'ASSET', '1000', 'USD', 'Loans to customers'),
('1401', 'Personal Loans', 'ASSET', '1400', 'USD', 'Individual customer loans'),
('1402', 'Business Loans', 'ASSET', '1400', 'USD', 'Commercial loans'),
('1403', 'Mortgage Loans', 'ASSET', '1400', 'USD', 'Real estate loans'),
('1500', 'Investment Securities', 'ASSET', '1000', 'USD', 'Trading and investment securities'),
('1600', 'Fixed Assets', 'ASSET', '1000', 'USD', 'Property, plant, and equipment'),

-- Liabilities (2000-2999)
('2000', 'LIABILITIES', 'LIABILITY', NULL, 'USD', 'Total Liabilities'),
('2100', 'Customer Deposits', 'LIABILITY', '2000', 'USD', 'Customer deposit accounts'),
('2101', 'Checking Accounts', 'LIABILITY', '2100', 'USD', 'Customer checking accounts'),
('2102', 'Savings Accounts', 'LIABILITY', '2100', 'USD', 'Customer savings accounts'),
('2103', 'Time Deposits', 'LIABILITY', '2100', 'USD', 'Certificates of deposit'),
('2104', 'Money Market Accounts', 'LIABILITY', '2100', 'USD', 'Money market deposit accounts'),
('2200', 'Interbank Borrowings', 'LIABILITY', '2000', 'USD', 'Borrowings from other banks'),
('2300', 'Central Bank Borrowings', 'LIABILITY', '2000', 'USD', 'Discount window borrowings'),
('2400', 'Accrued Interest Payable', 'LIABILITY', '2000', 'USD', 'Interest owed to depositors'),
('2500', 'Other Liabilities', 'LIABILITY', '2000', 'USD', 'Miscellaneous liabilities'),

-- Equity (3000-3999)
('3000', 'EQUITY', 'EQUITY', NULL, 'USD', 'Total Equity'),
('3100', 'Share Capital', 'EQUITY', '3000', 'USD', 'Issued share capital'),
('3200', 'Retained Earnings', 'EQUITY', '3000', 'USD', 'Accumulated retained earnings'),
('3300', 'Reserves', 'EQUITY', '3000', 'USD', 'Regulatory and other reserves'),

-- Revenue (4000-4999)
('4000', 'REVENUE', 'REVENUE', NULL, 'USD', 'Total Revenue'),
('4100', 'Interest Income', 'REVENUE', '4000', 'USD', 'Interest earned on loans and investments'),
('4101', 'Loan Interest Income', 'REVENUE', '4100', 'USD', 'Interest from customer loans'),
('4102', 'Investment Interest Income', 'REVENUE', '4100', 'USD', 'Interest from securities'),
('4200', 'Fee Income', 'REVENUE', '4000', 'USD', 'Non-interest income'),
('4201', 'Account Maintenance Fees', 'REVENUE', '4200', 'USD', 'Monthly account fees'),
('4202', 'Transaction Fees', 'REVENUE', '4200', 'USD', 'Per-transaction fees'),
('4203', 'ATM Fees', 'REVENUE', '4200', 'USD', 'ATM usage fees'),
('4204', 'Wire Transfer Fees', 'REVENUE', '4200', 'USD', 'Wire transfer charges'),

-- Expenses (5000-5999)
('5000', 'EXPENSES', 'EXPENSE', NULL, 'USD', 'Total Expenses'),
('5100', 'Interest Expense', 'EXPENSE', '5000', 'USD', 'Interest paid on deposits and borrowings'),
('5101', 'Deposit Interest Expense', 'EXPENSE', '5100', 'USD', 'Interest paid to depositors'),
('5102', 'Borrowing Interest Expense', 'EXPENSE', '5100', 'USD', 'Interest on interbank borrowings'),
('5200', 'Operating Expenses', 'EXPENSE', '5000', 'USD', 'Day-to-day operating costs'),
('5201', 'Staff Salaries', 'EXPENSE', '5200', 'USD', 'Employee compensation'),
('5202', 'Technology Expenses', 'EXPENSE', '5200', 'USD', 'IT and system costs'),
('5203', 'Facility Costs', 'EXPENSE', '5200', 'USD', 'Rent and utilities'),
('5204', 'Regulatory Compliance', 'EXPENSE', '5200', 'USD', 'Compliance and audit costs'),
('5300', 'Loan Loss Provisions', 'EXPENSE', '5000', 'USD', 'Provisions for bad debts');

-- Initialize account balances for key accounts
INSERT INTO account_balances (account_code, currency, balance_amount, last_updated) VALUES
('1101', 'USD', 10000000.00, NOW()),  -- Cash - Main Vault: $10M
('1102', 'USD', 2000000.00, NOW()),   -- Cash - ATM Network: $2M
('1103', 'USD', 500000.00, NOW()),    -- Cash - Teller Stations: $500K
('1200', 'USD', 50000000.00, NOW()),  -- Deposits with Central Bank: $50M
('1401', 'USD', 75000000.00, NOW()),  -- Personal Loans: $75M
('1402', 'USD', 125000000.00, NOW()), -- Business Loans: $125M
('1403', 'USD', 200000000.00, NOW()), -- Mortgage Loans: $200M
('2101', 'USD', -150000000.00, NOW()), -- Checking Accounts: $150M (liability)
('2102', 'USD', -200000000.00, NOW()), -- Savings Accounts: $200M (liability)
('2103', 'USD', -100000000.00, NOW()), -- Time Deposits: $100M (liability)
('3100', 'USD', -50000000.00, NOW()),  -- Share Capital: $50M (equity)
('3200', 'USD', -12500000.00, NOW());  -- Retained Earnings: $12.5M (equity)

-- Sample transactions to demonstrate the system
-- Transaction 1: Customer deposit
INSERT INTO transactions (transaction_id, description, total_amount, currency, status, created_by, correlation_id) 
VALUES ('TXN-001', 'Customer cash deposit - John Doe', 5000.00, 'USD', 'COMMITTED', 'teller-001', uuid_generate_v4());

INSERT INTO transaction_entries (transaction_id, entry_sequence, account_code, entry_type, amount, currency, description) VALUES
((SELECT id FROM transactions WHERE transaction_id = 'TXN-001'), 1, '1101', 'DEBIT', 5000.00, 'USD', 'Cash received'),
((SELECT id FROM transactions WHERE transaction_id = 'TXN-001'), 2, '2101', 'CREDIT', 5000.00, 'USD', 'Customer checking account credit');

-- Transaction 2: Loan disbursement
INSERT INTO transactions (transaction_id, description, total_amount, currency, status, created_by, correlation_id) 
VALUES ('TXN-002', 'Personal loan disbursement - Jane Smith', 25000.00, 'USD', 'COMMITTED', 'loan-officer-002', uuid_generate_v4());

INSERT INTO transaction_entries (transaction_id, entry_sequence, account_code, entry_type, amount, currency, description) VALUES
((SELECT id FROM transactions WHERE transaction_id = 'TXN-002'), 1, '1401', 'DEBIT', 25000.00, 'USD', 'Loan asset created'),
((SELECT id FROM transactions WHERE transaction_id = 'TXN-002'), 2, '2101', 'CREDIT', 25000.00, 'USD', 'Funds deposited to customer account');

-- Transaction 3: Interest accrual
INSERT INTO transactions (transaction_id, description, total_amount, currency, status, created_by, correlation_id) 
VALUES ('TXN-003', 'Monthly interest accrual on savings accounts', 15000.00, 'USD', 'COMMITTED', 'system-batch', uuid_generate_v4());

INSERT INTO transaction_entries (transaction_id, entry_sequence, account_code, entry_type, amount, currency, description) VALUES
((SELECT id FROM transactions WHERE transaction_id = 'TXN-003'), 1, '5101', 'DEBIT', 15000.00, 'USD', 'Interest expense'),
((SELECT id FROM transactions WHERE transaction_id = 'TXN-003'), 2, '2400', 'CREDIT', 15000.00, 'USD', 'Accrued interest payable');

-- Transaction 4: Fee collection
INSERT INTO transactions (transaction_id, description, total_amount, currency, status, created_by, correlation_id) 
VALUES ('TXN-004', 'Monthly account maintenance fees', 2500.00, 'USD', 'COMMITTED', 'system-batch', uuid_generate_v4());

INSERT INTO transaction_entries (transaction_id, entry_sequence, account_code, entry_type, amount, currency, description) VALUES
((SELECT id FROM transactions WHERE transaction_id = 'TXN-004'), 1, '2101', 'DEBIT', 2500.00, 'USD', 'Fees deducted from customer accounts'),
((SELECT id FROM transactions WHERE transaction_id = 'TXN-004'), 2, '4201', 'CREDIT', 2500.00, 'USD', 'Account maintenance fee income');

-- Transaction 5: ATM withdrawal
INSERT INTO transactions (transaction_id, description, total_amount, currency, status, created_by, correlation_id) 
VALUES ('TXN-005', 'ATM withdrawal - Customer 12345', 200.00, 'USD', 'COMMITTED', 'atm-001', uuid_generate_v4());

INSERT INTO transaction_entries (transaction_id, entry_sequence, account_code, entry_type, amount, currency, description) VALUES
((SELECT id FROM transactions WHERE transaction_id = 'TXN-005'), 1, '2101', 'DEBIT', 200.00, 'USD', 'Customer account debited'),
((SELECT id FROM transactions WHERE transaction_id = 'TXN-005'), 2, '1102', 'CREDIT', 200.00, 'USD', 'ATM cash dispensed');

-- Transaction 6: Wire transfer (incoming)
INSERT INTO transactions (transaction_id, description, total_amount, currency, status, created_by, correlation_id) 
VALUES ('TXN-006', 'Incoming wire transfer - ABC Corp', 50000.00, 'USD', 'COMMITTED', 'wire-system', uuid_generate_v4());

INSERT INTO transaction_entries (transaction_id, entry_sequence, account_code, entry_type, amount, currency, description) VALUES
((SELECT id FROM transactions WHERE transaction_id = 'TXN-006'), 1, '1300', 'DEBIT', 50000.00, 'USD', 'Funds received from correspondent bank'),
((SELECT id FROM transactions WHERE transaction_id = 'TXN-006'), 2, '2101', 'CREDIT', 50000.00, 'USD', 'Customer business account credited');

-- Transaction 7: Loan payment
INSERT INTO transactions (transaction_id, description, total_amount, currency, status, created_by, correlation_id) 
VALUES ('TXN-007', 'Loan payment - Principal and Interest', 1250.00, 'USD', 'COMMITTED', 'loan-system', uuid_generate_v4());

INSERT INTO transaction_entries (transaction_id, entry_sequence, account_code, entry_type, amount, currency, description) VALUES
((SELECT id FROM transactions WHERE transaction_id = 'TXN-007'), 1, '2101', 'DEBIT', 1250.00, 'USD', 'Payment from customer account'),
((SELECT id FROM transactions WHERE transaction_id = 'TXN-007'), 2, '1401', 'CREDIT', 1000.00, 'USD', 'Principal payment'),
((SELECT id FROM transactions WHERE transaction_id = 'TXN-007'), 3, '4101', 'CREDIT', 250.00, 'USD', 'Interest income');

-- Sample reconciliation batch
INSERT INTO reconciliation_batches (batch_id, reconciliation_date, status, total_transactions, matched_transactions, created_by) 
VALUES ('RECON-2024-001', CURRENT_DATE, 'MATCHED', 7, 7, 'recon-system');

-- Sample reconciliation details
INSERT INTO reconciliation_details (batch_id, transaction_id, account_code, expected_amount, actual_amount, status) 
SELECT 
    (SELECT id FROM reconciliation_batches WHERE batch_id = 'RECON-2024-001'),
    t.id,
    te.account_code,
    te.amount,
    te.amount,
    'MATCHED'
FROM transactions t
JOIN transaction_entries te ON t.id = te.transaction_id
WHERE t.status = 'COMMITTED';

-- Create some sample idempotency keys
INSERT INTO idempotency_keys (key_value, entity_type, entity_id, response_data) VALUES
('deposit-john-doe-20240101-001', 'transaction', 'TXN-001', '{"status": "success", "transaction_id": "TXN-001"}'),
('loan-jane-smith-20240101-002', 'transaction', 'TXN-002', '{"status": "success", "transaction_id": "TXN-002"}'),
('wire-abc-corp-20240101-003', 'transaction', 'TXN-006', '{"status": "success", "transaction_id": "TXN-006"}');

-- Create sample distributed locks (these would normally be managed by the application)
INSERT INTO distributed_locks (lock_name, lock_owner, expires_at, metadata) VALUES
('account-balance-1101', 'ledger-service-001', NOW() + INTERVAL '5 minutes', '{"operation": "balance_update", "account": "1101"}'),
('transaction-processing', 'transaction-service-001', NOW() + INTERVAL '2 minutes', '{"batch_id": "BATCH-001"}');

-- Update statistics for better query planning
ANALYZE chart_of_accounts;
ANALYZE account_balances;
ANALYZE transactions;
ANALYZE transaction_entries;
ANALYZE audit_trail;
ANALYZE reconciliation_batches;
ANALYZE reconciliation_details;

-- Create some views for common queries
CREATE OR REPLACE VIEW v_account_summary AS
SELECT 
    coa.account_code,
    coa.account_name,
    coa.account_type,
    coa.currency,
    COALESCE(ab.balance_amount, 0) as current_balance,
    COALESCE(ab.pending_amount, 0) as pending_amount,
    COALESCE(ab.available_amount, 0) as available_balance,
    ab.last_updated
FROM chart_of_accounts coa
LEFT JOIN account_balances ab ON coa.account_code = ab.account_code
WHERE coa.is_active = true
ORDER BY coa.account_code;

CREATE OR REPLACE VIEW v_transaction_summary AS
SELECT 
    t.transaction_id,
    t.description,
    t.total_amount,
    t.currency,
    t.status,
    t.transaction_date,
    t.created_by,
    COUNT(te.id) as entry_count,
    SUM(CASE WHEN te.entry_type = 'DEBIT' THEN te.amount ELSE 0 END) as total_debits,
    SUM(CASE WHEN te.entry_type = 'CREDIT' THEN te.amount ELSE 0 END) as total_credits
FROM transactions t
LEFT JOIN transaction_entries te ON t.id = te.transaction_id
GROUP BY t.id, t.transaction_id, t.description, t.total_amount, t.currency, t.status, t.transaction_date, t.created_by
ORDER BY t.transaction_date DESC;

CREATE OR REPLACE VIEW v_daily_transaction_volume AS
SELECT 
    DATE(transaction_date) as transaction_date,
    COUNT(*) as transaction_count,
    SUM(total_amount) as total_volume,
    currency,
    status
FROM transactions
WHERE transaction_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(transaction_date), currency, status
ORDER BY transaction_date DESC;

-- Grant permissions on views
GRANT SELECT ON v_account_summary TO banking_user;
GRANT SELECT ON v_transaction_summary TO banking_user;
GRANT SELECT ON v_daily_transaction_volume TO banking_user;

-- Create indexes on views for better performance
CREATE INDEX idx_v_account_summary_code ON chart_of_accounts(account_code) WHERE is_active = true;
CREATE INDEX idx_v_transaction_summary_date ON transactions(transaction_date DESC);
CREATE INDEX idx_v_daily_volume_date ON transactions(DATE(transaction_date)) WHERE transaction_date >= CURRENT_DATE - INTERVAL '30 days';

-- Log completion
INSERT INTO audit_trail (event_id, event_type, entity_type, entity_id, new_values, hash_value, correlation_id)
VALUES (
    'INIT-' || extract(epoch from now())::text,
    'SYSTEM_INIT',
    'DATABASE',
    'core_banking',
    '{"message": "Sample data loaded successfully", "timestamp": "' || NOW() || '"}',
    encode(digest('sample_data_init_' || NOW()::text, 'sha256'), 'hex'),
    uuid_generate_v4()
);
