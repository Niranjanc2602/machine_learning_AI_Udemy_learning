# ...existing code...
from dataclasses import dataclass
import os
from typing import Optional

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

PROMPT = """You are an intent classifier. Given a user message return one of: money, habit, progress, other.
Respond in JSON exactly: {{ "intent": "...", "score": 0.95, "explain": "..." }}

Decide the intent yourself based on the message. If 'candidate_hints' are provided, you may consider them but do NOT rely solely on them — pick whichever intent best matches the message.

Examples:
- "How much did I spend on coffee?" -> money
- "Remind me to run every morning" -> habit
- "Show progress for last week" -> progress
"""

def classify_intent(text: str) -> IntentResult:
    # Do not perform keyword scanning here — let the LLM decide the intent.
    if ChatOllama is None or create_agent is None or SystemMessage is None:
        # Ollama not available — return a neutral fallback
        return IntentResult("other", raw="ollama not available")

    llm = ChatOllama(
        base_url="http://localhost:11434",
        model="mistral",
        temperature=0.7
    )
    agent = create_agent(llm, tools=[])  # no external tools by default

    # Always pass empty/none candidate hints; LLM should pick the intent.
    messages = [
        SystemMessage(PROMPT),
        HumanMessage(f"Candidate hints: none\nUser message: {text}")
    ]

    try:
        result = agent.invoke({"messages": messages})
        resp = result.get("messages", [])[-1].content if result.get("messages") else ""
    except Exception as e:
        resp = f"ollama agent error: {e}"

    # try to parse JSON from response
    import json, re
    m = re.search(r"\{.*\}", resp, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            return IntentResult(obj.get("intent", "other"), confidence=obj.get("score"), raw=resp)
        except Exception:
            pass

    # final fallback
    return IntentResult("other", raw=resp)

if __name__ == "__main__":
    import sys
    txt = " ".join(sys.argv[1:]) or "Show me my spending this month"
    print(classify_intent(txt))
# ...existing code...