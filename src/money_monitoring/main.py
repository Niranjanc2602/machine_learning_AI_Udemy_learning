import json
from typing import Optional
from fastapi import FastAPI, HTTPException
import uvicorn
from model.money_model import Transaction, TransactionInput, BudgetInput, CategoryHierarchy

app = FastAPI(title="Money MCP Server - Tally Style")

# ============ In-Memory Database ============
transactions_db = {}
budgets_db = {}

# Category hierarchy (parent -> subcategories)
category_hierarchy = {
    "Food": ["Burger", "Coffee", "Groceries", "Restaurant"],
    "Transport": ["Fuel", "Taxi", "Public Transport", "Parking"],
    "Entertainment": ["Movies", "Gaming", "Books", "Sports"],
    "Utilities": ["Electricity", "Water", "Internet", "Phone"],
    "Salary": ["Monthly Salary", "Bonus", "Freelance"],
    "Other": ["Miscellaneous"]
}

# ============ Helper Functions ============
def get_all_subcategories(category: str) -> list[str]:
    """Get all subcategories for a parent category"""
    return category_hierarchy.get(category, [])

def is_parent_category(category: str) -> bool:
    """Check if category is a parent category"""
    return category in category_hierarchy

def get_parent_category(subcategory: str) -> Optional[str]:
    """Get parent category for a subcategory"""
    for parent, subs in category_hierarchy.items():
        if subcategory in subs:
            return parent
    return None

# ============ Money MCP Endpoints ============

@app.post("/add_transaction")
def add_transaction(tx: TransactionInput):
    """Add a new transaction with category/subcategory"""
    # Validate subcategory belongs to category
    if tx.subcategory not in get_all_subcategories(tx.category):
        raise HTTPException(status_code=400, detail=f"{tx.subcategory} is not under {tx.category}")
    
    tx_id = f"tx_{len(transactions_db) + 1}"
    transactions_db[tx_id] = {
        "id": tx_id,
        "amount": tx.amount,
        "category": tx.category,
        "subcategory": tx.subcategory,
        "description": tx.description,
        "date": tx.date,
        "type": tx.type  # income or expense
    }
    return {"status": "success", "transaction_id": tx_id, "data": transactions_db[tx_id]}

@app.get("/get_transactions")
def get_transactions(category: Optional[str] = None, subcategory: Optional[str] = None):
    """Get transactions filtered by category/subcategory"""
    filtered = dict(transactions_db)
    
    if category:
        filtered = {k: v for k, v in filtered.items() if v["category"].lower() == category.lower()}
    
    if subcategory:
        filtered = {k: v for k, v in filtered.items() if v["subcategory"].lower() == subcategory.lower()}
    
    return {"status": "success", "transactions": filtered}

@app.get("/get_spending/{query}")
def get_spending(query: str):
    """
    Get spending for category OR subcategory
    Examples: "Food" (returns all food spending), "Burger" (returns only burger)
    """
    # Check if it's a parent category
    if is_parent_category(query):
        subcats = get_all_subcategories(query)
        total = sum(tx["amount"] for tx in transactions_db.values() 
                   if tx["subcategory"] in subcats and tx["type"] == "expense")
        breakdown = {}
        for subcat in subcats:
            subcat_total = sum(tx["amount"] for tx in transactions_db.values() 
                             if tx["subcategory"] == subcat and tx["type"] == "expense")
            if subcat_total > 0:
                breakdown[subcat] = subcat_total
        
        return {
            "status": "success",
            "type": "parent_category",
            "category": query,
            "total_spending": total,
            "breakdown": breakdown
        }
    
    # Check if it's a subcategory
    parent = get_parent_category(query)
    if parent:
        total = sum(tx["amount"] for tx in transactions_db.values() 
                   if tx["subcategory"].lower() == query.lower() and tx["type"] == "expense")
        return {
            "status": "success",
            "type": "subcategory",
            "subcategory": query,
            "parent_category": parent,
            "total_spending": total
        }
    
    return {"status": "error", "message": f"{query} not found in categories"}

@app.get("/get_income/{query}")
def get_income(query: str):
    """Get income for category OR subcategory"""
    if is_parent_category(query):
        subcats = get_all_subcategories(query)
        total = sum(tx["amount"] for tx in transactions_db.values() 
                   if tx["subcategory"] in subcats and tx["type"] == "income")
        return {"status": "success", "category": query, "total_income": total}
    
    parent = get_parent_category(query)
    if parent:
        total = sum(tx["amount"] for tx in transactions_db.values() 
                   if tx["subcategory"].lower() == query.lower() and tx["type"] == "income")
        return {"status": "success", "subcategory": query, "total_income": total}
    
    return {"status": "error", "message": f"{query} not found in categories"}

@app.post("/set_budget")
def set_budget(budget: BudgetInput):
    """Set budget limit for category or subcategory"""
    budget_key = budget.category
    if budget.subcategory:
        budget_key = f"{budget.category}:{budget.subcategory}"
    
    budgets_db[budget_key] = budget.limit
    return {"status": "success", "budget_key": budget_key, "limit": budget.limit}

@app.get("/check_budget/{query}")
def check_budget(query: str):
    """Check if spending exceeds budget"""
    budget_key = None
    spending = 0
    
    if is_parent_category(query):
        budget_key = query
        subcats = get_all_subcategories(query)
        spending = sum(tx["amount"] for tx in transactions_db.values() 
                      if tx["subcategory"] in subcats and tx["type"] == "expense")
    else:
        parent = get_parent_category(query)
        if parent:
            budget_key = f"{parent}:{query}"
            spending = sum(tx["amount"] for tx in transactions_db.values() 
                          if tx["subcategory"].lower() == query.lower() and tx["type"] == "expense")
    
    if not budget_key or budget_key not in budgets_db:
        return {"status": "error", "message": f"No budget set for {query}"}
    
    limit = budgets_db[budget_key]
    exceeded = spending > limit
    
    return {
        "status": "success",
        "query": query,
        "spending": spending,
        "budget_limit": limit,
        "exceeded": exceeded,
        "remaining": limit - spending,
        "percentage": round((spending / limit) * 100, 2)
    }

@app.get("/balance")
def get_balance():
    """Get income vs expense balance (Tally style)"""
    total_income = sum(tx["amount"] for tx in transactions_db.values() if tx["type"] == "income")
    total_expense = sum(tx["amount"] for tx in transactions_db.values() if tx["type"] == "expense")
    balance = total_income - total_expense
    
    return {
        "status": "success",
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": balance,
        "savings_rate": round((balance / total_income * 100), 2) if total_income > 0 else 0
    }

@app.get("/summary")
def get_summary():
    """Get complete spending/income summary by parent category"""
    summary = {
        "expenses": {},
        "income": {},
        "total_income": 0,
        "total_expense": 0
    }
    
    for parent in category_hierarchy.keys():
        subcats = get_all_subcategories(parent)
        
        expense_total = sum(tx["amount"] for tx in transactions_db.values() 
                           if tx["subcategory"] in subcats and tx["type"] == "expense")
        income_total = sum(tx["amount"] for tx in transactions_db.values() 
                          if tx["subcategory"] in subcats and tx["type"] == "income")
        
        if expense_total > 0:
            summary["expenses"][parent] = expense_total
        if income_total > 0:
            summary["income"][parent] = income_total
    
    summary["total_income"] = sum(summary["income"].values())
    summary["total_expense"] = sum(summary["expenses"].values())
    
    return {"status": "success", "summary": summary}

@app.get("/categories")
def get_categories():
    """Get all categories and subcategories"""
    return {"status": "success", "categories": category_hierarchy}

@app.post("/add_category")
def add_category(data: CategoryHierarchy):
    """Add new parent category with subcategories"""
    if data.parent_category in category_hierarchy:
        return {"status": "error", "message": f"{data.parent_category} already exists"}
    
    category_hierarchy[data.parent_category] = data.subcategories
    return {"status": "success", "message": f"{data.parent_category} added", "categories": category_hierarchy}

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "money_mcp"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)