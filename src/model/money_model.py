from dataclasses import dataclass
from pydantic import BaseModel
from typing import Optional

# ============ Data Models ============
@dataclass
class Transaction:
    id: str
    amount: float
    category: str
    subcategory: str
    description: str
    date: str
    type: str  # "income" or "expense"

class TransactionInput(BaseModel):
    amount: float
    category: str  # e.g., "Food"
    subcategory: str  # e.g., "Burger"
    description: str
    date: str
    type: str  # "income" or "expense"

class BudgetInput(BaseModel):
    category: str
    subcategory: Optional[str] = None  # Can set budget on parent or sub
    limit: float

class CategoryHierarchy(BaseModel):
    parent_category: str
    subcategories: list[str]