import json
from typing import Optional, Dict, List
from datetime import datetime, date
from fastapi import FastAPI, HTTPException
import uvicorn
from model.money_model import Transaction, TransactionInput, BudgetInput, CategoryHierarchy
from enum import Enum

app = FastAPI(title="Tally-Style Money MCP Server")

# ============ TALLY-STYLE LEDGER GROUPS ============
LEDGER_GROUPS = {
    "Primary": {
        "Bank Accounts": ["SBI Current", "HDFC Savings", "ICICI Salary"],
        "Cash-in-hand": ["Cash"],
        "Current Assets": ["Accounts Receivable", "Prepaid Expenses"],
        "Current Liabilities": ["Accounts Payable", "Outstanding Expenses"],
        "Capital Account": ["Owner's Capital"],
        "Direct Income": ["Sales Account"],
        "Direct Expenses": ["Purchase Account"]
    },
    "Income Categories": {
        "Salary": ["Monthly Salary", "Bonus", "Freelance"],
        "Other Income": ["Interest Received", "Rent Received"]
    },
    "Expense Categories": {
        "Food": ["Groceries", "Restaurant", "Coffee"],
        "Transport": ["Fuel", "Taxi", "Public Transport"],
        "Utilities": ["Electricity", "Internet", "Phone"]
    }
}

# ============ LEDGER ACCOUNTS (Tally Style) ============
class AccountType(str, Enum):
    BANK = "Bank"
    CASH = "Cash"
    ASSET = "Asset"
    LIABILITY = "Liability"
    INCOME = "Income"
    EXPENSE = "Expense"
    CAPITAL = "Capital"

ledgers: Dict[str, Dict] = {}  # ledger_name -> {balance, type, transactions}
transactions_db: Dict[str, Dict] = {}
budgets_db: Dict[str, float] = {}

def create_ledger(name: str, account_type: AccountType, group: str, opening_balance: float = 0.0):
    """Create new ledger account like Tally"""
    if name in ledgers:
        raise HTTPException(400, f"Ledger {name} already exists")
    
    ledgers[name] = {
        "name": name,
        "type": account_type,
        "group": group,
        "opening_balance": opening_balance,
        "current_balance": opening_balance,
        "transactions": []
    }
    return {"status": "success", "ledger": name}

# Initialize default ledgers (Tally style)
@app.on_event("startup")
async def init_ledgers():
    default_ledgers = [
        ("SBI Current", AccountType.BANK, "Bank Accounts", 50000),
        ("HDFC Savings", AccountType.BANK, "Bank Accounts", 25000),
        ("Cash", AccountType.CASH, "Cash-in-hand", 5000),
        ("Owner's Capital", AccountType.CAPITAL, "Capital Account", 80000)
    ]
    for name, acc_type, group, balance in default_ledgers:
        create_ledger(name, acc_type, group, balance)

# ============ TALLY-STYLE TRANSACTIONS ============
@app.post("/voucher/payment")  # Payment Voucher
def payment_voucher(tx: TransactionInput):
    """Payment voucher - Money going out (Expense/Payable)"""
    ledger = tx.ledger or "Cash"  # Default cash payment
    if ledger not in ledgers:
        raise HTTPException(400, f"Ledger {ledger} not found")
    
    tx_id = f"pay_{len(transactions_db) + 1}"
    transaction = {
        "id": tx_id,
        "date": tx.date,
        "ledger": ledger,
        "amount": tx.amount,
        "type": "Dr",  # Debit Expense/Cash Out
        "category": tx.category,
        "subcategory": tx.subcategory,
        "narration": tx.description,
        "voucher_type": "Payment"
    }
    
    # Update ledger balance (Debit increases expense)
    ledgers[ledger]["current_balance"] += tx.amount
    ledgers[ledger]["transactions"].append(transaction)
    
    transactions_db[tx_id] = transaction
    return {"status": "success", "voucher_no": tx_id, "ledger_balance": ledgers[ledger]["current_balance"]}

@app.post("/voucher/receipt")  # Receipt Voucher
def receipt_voucher(tx: TransactionInput):
    """Receipt voucher - Money coming in (Income/Receivable)"""
    ledger = tx.ledger or "Cash"
    if ledger not in ledgers:
        raise HTTPException(400, f"Ledger {ledger} not found")
    
    tx_id = f"rec_{len(transactions_db) + 1}"
    transaction = {
        "id": tx_id,
        "date": tx.date,
        "ledger": ledger,
        "amount": tx.amount,
        "type": "Cr",  # Credit Income/Cash In
        "category": tx.category,
        "subcategory": tx.subcategory,
        "narration": tx.description,
        "voucher_type": "Receipt"
    }
    
    # Update ledger balance (Credit decreases bank balance)
    ledgers[ledger]["current_balance"] -= tx.amount
    ledgers[ledger]["transactions"].append(transaction)
    
    transactions_db[tx_id] = transaction
    return {"status": "success", "voucher_no": tx_id, "ledger_balance": ledgers[ledger]["current_balance"]}

# ============ TALLY AUTOMATION ENDPOINTS ============
@app.get("/trial-balance")
def trial_balance():
    """Tally Trial Balance - Verify Debit = Credit"""
    debit_total = sum(ledger["current_balance"] for ledger in ledgers.values() 
                     if ledger["type"] in ["Expense", "Asset", "Cash", "Bank"])
    credit_total = sum(ledger["current_balance"] for ledger in ledgers.values() 
                      if ledger["type"] in ["Income", "Liability", "Capital"])
    
    return {
        "status": "success",
        "date": date.today().isoformat(),
        "debit_total": debit_total,
        "credit_total": credit_total,
        "balanced": abs(debit_total - credit_total) < 0.01,
        "ledgers": {name: ledger["current_balance"] for name, ledger in ledgers.items()}
    }

@app.get("/balance-sheet")
def balance_sheet():
    """Tally Balance Sheet - Assets = Liabilities + Capital"""
    assets = sum(ledger["current_balance"] for ledger in ledgers.values() 
                if ledger["type"] in ["Asset", "Cash", "Bank"])
    liabilities = sum(ledger["current_balance"] for ledger in ledgers.values() 
                     if ledger["type"] == "Liability")
    capital = sum(ledger["current_balance"] for ledger in ledgers.values() 
                 if ledger["type"] == "Capital")
    
    return {
        "status": "success",
        "as_on_date": date.today().isoformat(),
        "assets": assets,
        "liabilities": liabilities,
        "capital": capital,
        "net_worth": capital + liabilities - assets,
        "balanced": abs(assets - (liabilities + capital)) < 0.01
    }

@app.get("/bank-reconciliation/{ledger_name}")
def bank_reconciliation(ledger_name: str):
    """Daily Bank Reconciliation like Tally"""
    if ledger_name not in ledgers:
        raise HTTPException(404, f"Ledger {ledger_name} not found")
    
    ledger = ledgers[ledger_name]
    transactions = ledger["transactions"][-30:]  # Last 30 days
    
    reconciled = sum(t["amount"] for t in transactions if t.get("reconciled", False))
    pending = sum(t["amount"] for t in transactions if not t.get("reconciled", False))
    
    return {
        "status": "success",
        "ledger": ledger_name,
        "current_balance": ledger["current_balance"],
        "total_transactions": len(transactions),
        "reconciled_amount": reconciled,
        "pending_amount": pending,
        "reconciliation_status": "Complete" if pending == 0 else "Pending"
    }

@app.get("/cash-flow")
def cash_flow_summary():
    """Daily Cash Flow Statement"""
    cash_ledgers = ["Cash", "SBI Current", "HDFC Savings"]
    today = date.today().isoformat()
    
    today_inflow = sum(t["amount"] for tx in transactions_db.values() 
                      if tx["date"] == today and tx["voucher_type"] == "Receipt")
    today_outflow = sum(t["amount"] for tx in transactions_db.values() 
                       if tx["date"] == today and tx["voucher_type"] == "Payment")
    
    return {
        "status": "success",
        "date": today,
        "opening_balance": sum(ledgers[l]["current_balance"] for l in cash_ledgers),
        "today_inflow": today_inflow,
        "today_outflow": today_outflow,
        "net_cash_flow": today_inflow - today_outflow,
        "closing_balance": sum(ledgers[l]["current_balance"] for l in cash_ledgers)
    }

@app.get("/ledgers")
def get_ledgers():
    """List all ledger accounts with balances"""
    return {
        "status": "success",
        "total_ledgers": len(ledgers),
        "ledgers": [
            {
                "name": ledger["name"],
                "group": ledger["group"],
                "type": ledger["type"],
                "balance": ledger["current_balance"],
                "opening_balance": ledger["opening_balance"]
            }
            for ledger in ledgers.values()
        ]
    }

# Keep existing endpoints for backward compatibility
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "tally_money_mcp", "ledgers_count": len(ledgers)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
