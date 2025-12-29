# ...existing imports...
from dataclasses import dataclass
import os
import requests
import json
from typing import Optional, Dict, Any
from urllib.parse import quote

# try to import Ollama / langchain_core helpers (user-provided runtime)
try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    from langchain.agents import create_agent
except Exception:
    ChatOllama = None
    SystemMessage = HumanMessage = AIMessage = None
    create_agent = None

@dataclass
class IntentResult:
    intent: str
    confidence: Optional[float] = None
    raw: Optional[str] = None
    endpoint: Optional[str] = None  # NEW: Suggested Money MCP endpoint
    params: Optional[Dict[str, Any]] = None  # NEW: Parameters for endpoint

MONEY_MCP_URL = "http://localhost:8001"  # Dockerized Money MCP service

PROMPT = """You are an intent classifier AND endpoint router for Money MCP (Tally-style accounting).
Given a user message return one of: money, habit, progress, other.

For MONEY intents, also suggest the exact Money MCP endpoint + parameters.

Respond in JSON exactly: 
{ 
  "intent": "money", 
  "score": 0.95, 
  "explain": "...",
  "endpoint": "/endpoint", 
  "params": {...}
}

MONEY MCP ENDPOINTS:
- POST /voucher/receipt - Add income: "add 50000 salary to SBI", "received 2000 cash"
- POST /voucher/payment - Add expense: "spent 1500 groceries from cash", "paid 5000 fuel SBI"
- GET /trial-balance - Trial balance: "trial balance", "check accounts"
- GET /balance-sheet - Balance sheet: "balance sheet", "net worth"
- GET /bank-reconciliation/{ledger} - Bank recon: "SBI reconciliation", "reconcile HDFC"
- GET /cash-flow - Cash flow: "cash flow today", "today's transactions"
- GET /ledgers - All ledgers: "show all accounts", "ledger balances"

Examples:
- "How much did I spend on coffee?" -> {intent: "money", endpoint: "/get_spending/coffee", params: {}}
- "Add 50000 salary to SBI account" -> {intent: "money", endpoint: "/voucher/receipt", params: {ledger: "SBI Current", amount: 50000, category: "Salary", date: "today"}}
- "What's my balance sheet?" -> {intent: "money", endpoint: "/balance-sheet", params: {}}
"""

MONEY_LEDGERS = ["SBI Current", "HDFC Savings", "ICICI Salary", "Cash"]

def call_money_mcp(endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Call Money MCP API endpoint"""
    try:
        url = f"{MONEY_MCP_URL}{endpoint}"
        
        if endpoint.startswith("/voucher/"):
            # POST voucher endpoints
            response = requests.post(url, json=params)
        else:
            # GET endpoints
            param_str = "?" + "&".join(f"{k}={quote(str(v))}" for k, v in (params or {}).items())
            response = requests.get(url + param_str)
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Money MCP error: {str(e)}"}

def classify_intent(text: str) -> IntentResult:
    if ChatOllama is None or create_agent is None or SystemMessage is None:
        return IntentResult("other", raw="ollama not available")

    llm = ChatOllama(
        base_url="http://localhost:11434",
        model="mistral",
        temperature=0.7
    )
    agent = create_agent(llm, tools=[])  

    messages = [
        SystemMessage(PROMPT),
        HumanMessage(f"User message: {text}")
    ]

    try:
        result = agent.invoke({"messages": messages})
        resp = result.get("messages", [])[-1].content if result.get("messages") else ""
    except Exception as e:
        resp = f"ollama agent error: {e}"

    # Parse JSON response
    import re
    m = re.search(r"\{.*\}", resp, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            intent_result = IntentResult(
                intent=obj.get("intent", "other"), 
                confidence=obj.get("score"),
                raw=resp,
                endpoint=obj.get("endpoint"),
                params=obj.get("params")
            )
            
            # Auto-enhance money params
            if intent_result.intent == "money" and intent_result.endpoint:
                intent_result.params = enhance_money_params(text, intent_result.params or {})
            
            return intent_result
        except Exception:
            pass

    return IntentResult("other", raw=resp)

def enhance_money_params(text: str, base_params: Dict[str, Any]) -> Dict[str, Any]:
    """Smart parameter extraction from natural language"""
    params = base_params.copy()
    
    # Auto-detect ledger (prioritize banks/cash)
    for ledger in MONEY_LEDGERS:
        if ledger.lower() in text.lower():
            params["ledger"] = ledger
            break
    
    # Auto-set date to today if not specified
    if "date" not in params:
        from datetime import date
        params["date"] = date.today().isoformat()
    
    # Extract category/subcategory patterns
    category_patterns = {
        "salary": ("Salary", "Monthly Salary"),
        "food": ("Food", "Groceries"),
        "coffee": ("Food", "Coffee"),
        "fuel": ("Transport", "Fuel"),
        "groceries": ("Food", "Groceries")
    }
    
    text_lower = text.lower()
    for keyword, (cat, subcat) in category_patterns.items():
        if keyword in text_lower:
            params["category"] = cat
            params["subcategory"] = subcat
            break
    
    return params

def process_intent(intent_result: IntentResult) -> Dict[str, Any]:
    """Process intent and return result"""
    if intent_result.intent == "money" and intent_result.endpoint:
        result = call_money_mcp(intent_result.endpoint, intent_result.params)
        return {
            "intent": "money",
            "endpoint_called": intent_result.endpoint,
            "params": intent_result.params,
            "money_mcp_response": result
        }
    
    return {
        "intent": intent_result.intent,
        "confidence": intent_result.confidence,
        "message": "Intent recognized but no Money MCP endpoint matched"
    }

if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or "Add 5000 salary to SBI and show balance sheet"
    
    intent = classify_intent(text)
    print("Intent:", intent.intent)
    print("Endpoint:", intent.endpoint)
    print("Params:", intent.params)
    
    result = process_intent(intent)
    print(json.dumps(result, indent=2))
