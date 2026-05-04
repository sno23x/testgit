-- Migration: add currency support to debts
-- Run once on server: sqlite3 /path/to/pos.db < migrate_currency.sql

ALTER TABLE customers ADD COLUMN total_debt_thb REAL DEFAULT 0;
ALTER TABLE debt_payments ADD COLUMN currency VARCHAR(5) DEFAULT 'LAK';
ALTER TABLE sales ADD COLUMN change_amount REAL DEFAULT 0;
