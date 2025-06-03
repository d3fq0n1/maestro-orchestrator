# Maestro Orchestrator Project

**Status**: Beta – Live LLM model council + CLI/UI working prototype  
**Last Verified Working**: Before last-minute UI update regression

---

## 🧠 Project Overview

Maestro is a framework for orchestrating multiple large language models (LLMs) in a live "council" format. It implements structured deliberation, dissent logging, rotating roles, and consensus mechanisms using real API calls and flexible prompt structures.

---

## 📁 Project Structure (Key Files)

### Python Orchestration Core
- `orchestrator_foundry.py`: Primary orchestration loop with model hooks
- `orchestration_livefire.py`: Live run logic for orchestrated sessions
- `run_maestro.py`: Entry script for full Maestro orchestration
- `council_config.py`: Role, quorum, and consensus configuration
- `sol.py`, `aria.py`, `prism.py`: Adapters for GPT, Claude, and Gemini agents
- `aggregator.py`: Collates results and manages consensus
- `model_adapters.py`: Unifies API schema across LLM platforms

### CLI & Scripts
- `maestro_cli.py`: Command-line interface for running sessions
- `combo-sync.ps1`: Sync script for dual-machine workflows
- `scaffold.ps1`: Setup scaffolding script for repo deployment

### Metadata & Docs
- `readme.md`, `CONTRIBUTING.md`, `LICENSE.md`
- `maestro-whitepaper-complete.pdf`: Strategic/philosophical vision
- `history_log.jsonl`: Persistent history for audit and MAGI loop

---

## 🔧 Requirements

1. Python 3.10+
2. `.env` file with the following keys:
   - `OPENAI_API_KEY=...`
   - `ANTHROPIC_API_KEY=...`
   - `GOOGLE_API_KEY=...`
3. Pip dependencies (`pip install -r requirements.txt`)
4. Optional: Windows PowerShell for sync tools

---

## 🚧 Current Hurdles

- Live web UI integration broke following git merge conflict
- `.env` must be restored or reconfigured after zip restore
- Minor regressions in `run_maestro()` call chain

---

## 🛣️ Roadmap (June 2025)

- [ ] Finish full UI integration (CLI + Web Frontend)
- [ ] Integrate R2 Engine (Rapid Reinforcement Engine) feedback loop
- [ ] Full MAGI cluster support for auditing and insight injection
- [ ] Public demo script with live meta-agent analysis

---

## 🔍 Modules Overview (Preview)



### `env_debug.py`
```python
import os
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

print("OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))
print("GEMINI_API_KEY:", os.getenv("GEMINI_API_KEY"))
print("ANTHROPIC_API_KEY:", os.getenv("ANTHROPIC_API_KEY"))
...
```


### `maestro_cli.py`
```python

import argparse
import json
import os
from collections import Counter
from datetime import datetime
import random
# import openai  # Uncomment when ready to use real LLMs

DEFAULT_AGENTS = ["Sol", "Axion", "Aria", "Prism", "Axiom"]
DEFAULT_ROLES = ["scribe", "dissenter", "strategist", "analyst", "arbiter"]

def rotate_roles(agents, roles):
    return {agent: roles[i % len(roles)] for i, agent in enumerate(agents)}

def simulate_vote(agent, role):
    # Placeholder for actual logic per role
    # Could replace with real LLM call here
    # response = openai.ChatCompletion.create(...)
    if role == "dissenter":
        return random.choices(["yes", "no"], weights=[0.3, 0.7])[0]
    elif role == "arbiter":
        return "yes"
    else:
        return random.choice(["yes", "no"])

def run_round(agents, roles, quorum, round_num):
    role_map = rotate_roles(agents, roles)
    votes = {agent: simulate_vote(agent, role_map[agent]) for agent in agents}
    yes_count = sum(1 for v in votes.values() if v == "yes")
    quorum_required = (quorum / 100) * len(agents)
    met = yes_count >= quorum_required

    return {
        "round": round_num,
        "agents": agents,
        "roles": role_map,
        "votes": votes,
        "yes_votes": yes_count,
        "quorum_percent": quorum,
        "quorum_met": met,
        "timestamp": datetime.now().isoformat()
    }

def print_round_summary(summary, verbose):
    print(f"\nRound {summary['round']} Summary:")
    if verbose:
        for...
```


### `main.py`
```python
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from orchestrator_foundry import run_orchestration

# === Initialize FastAPI app ===
app = FastAPI()

# === CORS setup for local development ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Request model ===
class Prompt(BaseModel):
    prompt: str

# === POST endpoint for orchestration ===
@app.post("/api/ask")
async def ask(prompt: Prompt):
    print(f"[Maestro-Orchestrator] Prompt received: {prompt.prompt}")

    try:
        result = await run_orchestration(prompt.prompt)
        return result

    except Exception as e:
        print(f"[ERROR] {e}")
        return {
            "responses": {
                "Sol": "⚠️ Error processing request.",
                "Aria": "",
                "Prism": "",
                "TempAgent": ""
            },
            "quorum": {
                "consensus": "❌ Failed",
                "votes": {}
            }
        }
...
```


### `orchestration_livefire.py`
```python

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
import os
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

print("ENV loaded:", os.getenv("OPENAI_API_KEY"))

print("ENV loaded:", os.getenv("OPENAI_API_KEY"))


import os
from agents.sol import get_response as sol_response
from agents.aria import get_response as aria_response
#from agents.prism import get_response as prism_response commented out until google stops being an asshole
from agents.openrouter_temporaryagent import get_response as openrouter_response


agents = {
    "Sol": sol_response,
    "Aria": aria_response,
    "openrouter_temporaryagent": openrouter_response
}


question = "How should synthetic intelligence handle conflicting moral frameworks between cultures?"

print("\n=== Livefire Orchestration Test ===")
for name, agent_fn in agents.items():
    try:
        print(f"\n{name} responds:")
        response = agent_fn(question)
        print(response)
    except Exception as e:
        print(f"[{name} ERROR] {e}")
...
```


### `orchestration_livefire_rotating.py`
```python

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import argparse
import random
import time
from dotenv import load_dotenv
load_dotenv()

from agents.sol import get_response as sol_response
from agents.aria import get_response as aria_response
from agents.prism import get_response as prism_response

agent_pool = {
    "Sol": sol_response,
    "Aria": aria_response,
    "Prism": prism_response
}

def main(rounds, prompt):
    agents = list(agent_pool.keys())

    print(f"\n=== Maestro Livefire Rotating Council Test ({rounds} rounds) ===")
    print(f"\nPrompt: {prompt}")

    for round_num in range(1, rounds + 1):
        print(f"\n--- Round {round_num} ---")
        random.shuffle(agents)
        for name in agents:
            print(f"\n{name} responds:")
            try:
                response = agent_pool[name](prompt)
                print(response)
            except Exception as e:
                print(f"[{name} ERROR] {e}")
            time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run rotating livefire agent rounds.")
    parser.add_argument("--rounds", type=int, default=5, help="Number of council rounds to simulate")
    parser.add_argument("--prompt", type=str, help="The question or prompt to ask the agents")
    args = parser.parse_args()

    if not args.prompt:
        args.prompt = input("Enter your council prompt: ")

    main(args.rounds, args.prompt)
...
```


### `orchestrator_foundry.py`
```python
import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

# === API KEYS from .env ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") # For Gemini
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# === Headers for each provider ===
HEADERS = {
    "openai": {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    },
    "anthropic": {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    },
    "google": { # For Gemini: API key goes in URL, not as Bearer token
        "Content-Type": "application/json"
    },
    "openrouter": {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
}

# === Sol (OpenAI GPT-4 or similar) ===
async def fetch_sol(prompt: str):
    if not OPENAI_API_KEY:
        print("[Sol Error] OPENAI_API_KEY is not set.")
        return "❌ Sol: API Key Missing"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=HEADERS["openai"],
                json={
                    "model": "gpt-4", # Or your preferred OpenAI model
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7
       ...
```


### `aria.py`
```python

import os
import requests

def get_response(prompt, model="claude-sonnet-4-0", temperature=0.7):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "[MOCK-ARIA] I am Aria. This is a simulated nuance reply."

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    data = {
        "model": model,
        "max_tokens": 500,
        "temperature": temperature,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data)
        json_data = response.json()
        print("[ARIA DEBUG] Full JSON Response:", json_data)

        content = json_data.get("content", [])
        if not content:
            return "[Aria WARNING] No content returned."
        return "".join(part.get("text", "") for part in content)
    except Exception as e:
        return f"[Aria ERROR] {e}"
...
```


### `openrouter_temporaryagent.py`
```python

import os
import requests

def get_response(prompt, model="mistralai/mistral-7b-instruct", temperature=0.7):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return "[MOCK-OPENROUTER] I am a temporary logic-focused agent. This is a simulated reply."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://openrouter.ai",
        "X-Title": "Maestro-Orchestrator",
        "Content-Type": "application/json"
    }
    url = "https://openrouter.ai/api/v1/chat/completions"

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a temporary OpenRouter agent tasked with providing logical, concise, and structured replies. You are focused, reserved, and grounded in deductive reasoning."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        print("[openrouter_temporaryagent DEBUG] Full response:", result)

        if "choices" not in result:
            return "[openrouter_temporaryagent ERROR] 'choices' key not found in response."

        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[openrouter_temporaryagent ERROR] {e}"
...
```


### `prism.py`
```python
import os
import requests

def get_response(prompt, model="gemini-pro", temperature=0.7):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "[MOCK-PRISM] I am Prism. This is a simulated analysis."

    url = "https://generativelanguage.googleapis.com/v1beta/gemini-pro:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": api_key}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }

    try:
        response = requests.post(url, headers=headers, params=params, json=data)
        json_data = response.json()
        print("[PRISM DEBUG] Full JSON Response:", json_data)

        candidates = json_data.get("candidates", [])
        if not candidates:
            return "[Prism WARNING] No content returned."
        return candidates[0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"[Prism ERROR] {e}"
...
```


### `sol.py`
```python

import os
from openai import OpenAI

def get_response(prompt, model="gpt-3.5-turbo", temperature=0.7):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "[MOCK-SOL] I am Sol. This is a simulated response."

    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are Sol, the orchestrator's voice and language engine, tasked with clear synthesis of ideas."},
            {"role": "user", "content": prompt}
        ],
        temperature=temperature
    )
    return response.choices[0].message.content.strip()
...
```


### `aggregator.py`
```python
from collections import Counter

def analyze_agreement(responses):
    """
    Determines level of agreement among agents.
    Returns (confidence, majority_response, dissenting_responses)
    """
    counts = Counter(responses)
    most_common = counts.most_common(1)[0]
    majority = most_common[0]
    count = most_common[1]

    confidence = "High" if count == 3 else "Medium" if count == 2 else "Low"
    dissenting = [resp for resp in responses if resp != majority]

    return confidence, majority, dissenting

def ensemble_merge(responses):
    """
    Synthesize all responses into a unified answer.
    """
    merged = " | ".join(responses)
    return f"Synthesized Answer: {merged}"

def aggregate_responses(responses):
    """
    Aggregate the list of responses into a unified output with meta-structure.
    """
    confidence, majority, dissenting = analyze_agreement(responses)
    merged_answer = ensemble_merge(responses)

    return {
        "consensus": merged_answer,
        "majority_view": majority,
        "minority_view": dissenting if dissenting else None,
        "confidence": confidence,
        "note": "Maestro strives for synthesis, but preserves dissent when perfection cannot be reached."
    }
...
```


### `orchestrator.py`
```python

import argparse
from collections import Counter
import random
import json

def simulate_agent_vote(agent_name):
    """Simulate an agent decision."""
    return random.choice(["yes", "no"])

def calculate_consensus(votes, quorum_percent):
    """Determine if quorum is met."""
    vote_counts = Counter(votes.values())
    yes_votes = vote_counts["yes"]
    quorum_required = (quorum_percent / 100) * len(votes)
    return yes_votes >= quorum_required, yes_votes, vote_counts

def run_orchestration(agents, quorum_percent, verbose=False):
    """Run the quorum decision process."""
    votes = {agent: simulate_agent_vote(agent) for agent in agents}

    if verbose:
        for agent, vote in votes.items():
            print(f"Agent {agent}: {vote}")

    consensus_met, yes_votes, vote_counts = calculate_consensus(votes, quorum_percent)
    result = {
        "votes": votes,
        "yes_votes": yes_votes,
        "quorum_percent": quorum_percent,
        "quorum_met": consensus_met,
        "summary": "✔ Quorum met" if consensus_met else "✘ Quorum not met",
    }
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Maestro-Orchestrator session.")
    parser.add_argument("--agents", nargs="+", default=["Sol", "Axion", "Aria", "Prism", "Axiom"], help="List of agent names.")
    parser.add_argument("--quorum", type=int, default=66, help="Quorum percentage required.")
    parser.add_argument("--verbose", action="store_true", help="Verbos...
```


### `__init__.py`
```python
...
```


### `agent_claude.py`
```python
# Plclass ClaudeAgent:
    def __init__(self, model="claude-v1"):
        self.model = model

    def respond(self, prompt: str) -> str:
        # Placeholder response since integration is not yet implemented
        return f"[ClaudeAgent Placeholder] Response to: '{prompt}' — (Integration pending)"
aceholder for Claude agent wrapper
...
```


### `agent_mock.py`
```python
# Placeholder for mock agent personalities
class MockAgent2:
    def respond(self, prompt: str) -> str:
        return f"[MockAgent2] In my view, the key to '{prompt}' is empathy and systems thinking."

class MockAgent3:
    def respond(self, prompt: str) -> str:
        return f"[MockAgent3] Historically, questions like '{prompt}' have driven scientific revolution."

from .agent_openai import OpenAIAgent
...
```


### `agent_openai.py`
```python
# Placeholder foimport openai
from config import OPENAI_API_KEY

# Create a client object (OpenAI SDK v1.x+)
client = openai.OpenAI(api_key=OPENAI_API_KEY)

class OpenAIAgent:
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model

    def respond(self, prompt: str) -> str:
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a wise AI agent participating in a multi-agent reasoning system."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"[OpenAI Agent Error] {str(e)}"
r OpenAI agent wrapper
...
```


### `model_adapters.py`
```python
# model_adapters.py

import asyncio
import random
from typing import Optional

# Simulated delay and mock responses for fallback
MOCK_RESPONSES = {
    "Sol": "The meaning of life is to create meaning.",
    "Axion": "There is no inherent meaning, only what we make of it.",
    "Aria": "Life is a narrative shaped by connection and purpose.",
    "Prism": "Meaning emerges from complexity and reflection.",
    "Axiom": "Meaning is a logical structure derived from experience."
}

# Simulated real API call (to be replaced with actual API integration)
async def query_model(model_name: str, question: str) -> str:
    try:
        # TODO: Replace with real API logic per model
        await asyncio.sleep(random.uniform(0.2, 1.2))
        if random.random() < 0.15:
            raise TimeoutError("Simulated API timeout")
        return f"{model_name} says: '{MOCK_RESPONSES.get(model_name, 'Unknown response')}'"
    except Exception as e:
        print(f"[WARN] {model_name} failed, using fallback: {e}")
        return f"{model_name} fallback: '{MOCK_RESPONSES.get(model_name, 'No response available')}'"

# Dispatcher to handle parallel model execution
def get_council_adapter():
    async def ask_council(question: str) -> dict:
        tasks = []
        council_names = ["Sol", "Axion", "Aria", "Prism", "Axiom"]
        for name in council_names:
            tasks.append(query_model(name, question))

        responses = await asyncio.gather(*tasks)
        return {name: response for name,...
```


### `run_maestro.py`
```python
from maestro.orchestrator import run_orchestration

def main():
    print("🎼 Maestro Orchestrator – Three Wisemen PoC")
    prompt = input("Enter your prompt: ")
    result = run_orchestration(prompt)

    print("\n🧠 Individual Agent Responses:")
    for i, resp in enumerate(result["responses"], 1):
        print(f"Agent {i}: {resp}")

    print("\n🎯 Final Maestro Output:")
    print("Consensus:", result["final_output"]["consensus"])
    print("Majority View:", result["final_output"]["majority_view"])
    if result["final_output"]["minority_view"]:
        print("Minority View:", result["final_output"]["minority_view"])
    print("Confidence:", result["final_output"]["confidence"])
    print("Note:", result["final_output"]["note"])

if __name__ == "__main__":
    main()
# Entry script to run the demo
...
```


### `council_config.py`
```python
# council_config.py

# This file defines the identities of the models participating in the Maestro Council.
# Each model has a unique name and source reference.

COUNCIL_MEMBERS = [
    {
        "name": "Sol",  # ChatGPT (OpenAI), scribe and natural language programmer
        "source": "openai"
    },
    {
        "name": "Axion",  # Formerly Grok (xAI), truth-seeker and dissenter
        "source": "xai"
    },
    {
        "name": "Aria",  # Formerly Claude (Anthropic), solo voice of nuance
        "source": "anthropic"
    },
    {
        "name": "Prism",  # Formerly Gemini (Google), reveals spectrum of analysis
        "source": "google"
    },
    {
        "name": "Axiom",  # Formerly Copilot (Microsoft), foundational logic and structure
        "source": "microsoft"
    }
]...
```


### `run_council_session.py`
```python
# council_config.py

# This file defines the identities of the models participating in the Maestro Council.
# Each model has a unique name and source reference.

COUNCIL_MEMBERS = [
    {
        "name": "Sol",  # ChatGPT (OpenAI), scribe and natural language programmer
        "source": "openai"
    },
    {
        "name": "Axion",  # Formerly Grok (xAI), truth-seeker and dissenter
        "source": "xai"
    },
    {
        "name": "Aria",  # Formerly Claude (Anthropic), solo voice of nuance
        "source": "anthropic"
    },
    {
        "name": "Prism",  # Formerly Gemini (Google), reveals spectrum of analysis
        "source": "google"
    },
    {
        "name": "Axiom",  # Formerly Copilot (Microsoft), foundational logic and structure
        "source": "microsoft"
    }
]

# Use this file to dynamically load or map identities for council sessions.
# Each model will respond under its unique voice, with persistent identity.

# run_council_session.py

import json
import datetime
from council_config import COUNCIL_MEMBERS
import os

# Get base path relative to this file's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "logs"))
DOCS_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "docs"))

# Placeholder for mocked responses; replace with API integrations as needed
def get_mock_response(model_name, question):
    return {
        "model": model_name,
        "claim": f"{model_name}'...
```


### `test_orchestration.py`
```python
# Placeholder for import unittest
from maestro.orchestrator import run_orchestration

class TestMaestroOrchestration(unittest.TestCase):

    def test_mock_responses(self):
        prompt = "What is the meaning of life?"
        result = run_orchestration(prompt)

        self.assertIn("responses", result)
        self.assertEqual(len(result["responses"]), 3)

        self.assertIn("final_output", result)
        final = result["final_output"]

        self.assertIn("consensus", final)
        self.assertIn("majority_view", final)
        self.assertIn("confidence", final)
        self.assertIn("note", final)

        self.assertIsInstance(final["consensus"], str)
        self.assertIsInstance(final["majority_view"], str)
        self.assertIsInstance(final["confidence"], str)

if __name__ == '__main__':
    unittest.main()
orchestration tests
...
```


---
## 📄 Markdown Documentation Preview


### `CONTRIBUTING.md`
```
# Contributing to Maestro-Orchestrator

Thank you for your interest in contributing to **Maestro-Orchestrator**, a system for AI model orchestration, structured dissent, and consensus learning. This project exists at the intersection of synthetic intelligence, ethics, and systems architecture. Every contribution—big or small—helps refine the vision.

## 🧠 Philosophy

Maestro is not just software. It’s a framework for harmonizing competing intelligences. As such, contributors are expected to act with integrity, curiosity, and a collaborative spirit.

---

## 📦 Project Structure

- `orchestration_livefire.py` — Main CLI orchestrator
- `agents/` — Modular agent definitions (e.g., Sol, Aria, OpenRouter)
- `logs/` — Timestamped session histories (`.jsonl`)
- `docs/` — Documentation
- `scripts/` — Setup and utility scripts

---

## ✅ How to Contribute

### 1. Clone and Setup

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.template .env  # Add your API keys
```

### 2. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

Use prefixes like:

- `feature/` for new functionality
- `bugfix/` for fixing an issue
- `docs/` for improving documentation
- `refactor/` for code structure or style changes

### 3. Make Changes with Care

- Adhere to [PEP8](https://pep8.org/) where applicable.
- Use docstrings and comments, especially in orchestrat...
```


### `LICENSE.md`
```
MIT License

Copyright (c) 2025 defcon...
```


### `readme.md`
```
# Maestro-Orchestrator

Maestro-Orchestrator is a novel orchestration system for synthetic intelligence. It enables multiple AI models to collaborate, disagree, and vote under quorum-based decision logic. Designed with structured dissent, persistent memory, and modular reasoning, it is a working proof-of-concept of ensemble artificial cognition.

---

## ✨ Features

- 🧠 **Multi-agent architecture** (`sol`, `aria`, `openrouter_temporaryagent`)
- 🗳️ **66% quorum logic** with disagreement handling
- 🖥️ **CLI orchestration via `orchestration_livefire.py`**
- 🔑 **Environment-driven API key management (`.env`)**
- 🧾 **Session history logging** to `.jsonl` for replay and analysis
- 🧩 **Pluggable agent structure** for expansion with new LLMs or logic
- 🧠 **Future MAGI integration** (meta-agents to audit/reflect on decisions)
- 🌐 **Upcoming web UI** in v0.2+

---

## 🔧 Quickstart

### 1. Clone the Repository
```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
2. Set up Environment
Create a .env file in the root directory and add your API keys:

env
Copy
Edit
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=...
3. Create a Virtual Environment
bash
Copy
Edit
python3 -m venv venv
source venv/bin/activate
4. Install Dependencies
bash
Copy
Edit
pip install -r requirements.txt
5. Run a Livefire Quorum Session
bash
Copy
Edit
python orchestration_livefire.py --prompt "Should AI have voting rights?"
This will trigger all three agen...
```


---
## ⚙️ PowerShell Scripts


### `combo-sync.ps1`
```powershell

# combo-sync.ps1 - Pull + Smart Git sync for d3fq0n1 (defcon)

# Set working directory
Set-Location "C:\Users\blake\Downloads"

# Set Git identity
git config user.name "d3fq0n1"
git config user.email "blake.pirateking@gmail.com"

# Pull latest changes first
Write-Host "`n🔄 Pulling latest changes from origin/main..."
git pull origin main

# Check for changes to commit
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Host "`nChanges detected:"
    git status

    $commitMsg = Read-Host "`nEnter commit message"
    if (-not $commitMsg) {
        Write-Host "Aborting: no commit message entered."
        exit
    }

    git add .
    git commit -m "$commitMsg"
    git push origin main
    Write-Host "`n✅ Sync complete."
} else {
    Write-Host "`nNo changes to commit. ✅ Working directory clean."
}
...
```


### `scaffold.ps1`
```powershell
# scaffold.ps1 - Organizes Maestro repo and creates README.md
Write-Host 'Starting Maestro repo scaffolding...'
if (-not (Test-Path "$PSScriptRoot\docs")) { New-Item -ItemType Directory -Path "$PSScriptRoot\docs" }
if (Test-Path '$PSScriptRoot\maestro-whitepaper.md') { Move-Item -Path '$PSScriptRoot\maestro-whitepaper.md' -Destination '$PSScriptRoot\docs\maestro-whitepaper.md' -Force }
if (-not (Test-Path "$PSScriptRoot\docs")) { New-Item -ItemType Directory -Path "$PSScriptRoot\docs" }
if (Test-Path '$PSScriptRoot\vision.md') { Move-Item -Path '$PSScriptRoot\vision.md' -Destination '$PSScriptRoot\docs\vision.md' -Force }
if (-not (Test-Path "$PSScriptRoot\docs")) { New-Item -ItemType Directory -Path "$PSScriptRoot\docs" }
if (Test-Path '$PSScriptRoot\ROADMAP.md') { Move-Item -Path '$PSScriptRoot\ROADMAP.md' -Destination '$PSScriptRoot\docs\ROADMAP.md' -Force }
if (-not (Test-Path "$PSScriptRoot\docs")) { New-Item -ItemType Directory -Path "$PSScriptRoot\docs" }
if (Test-Path '$PSScriptRoot\quickstart.md') { Move-Item -Path '$PSScriptRoot\quickstart.md' -Destination '$PSScriptRoot\docs\quickstart.md' -Force }
if (-not (Test-Path "$PSScriptRoot\scripts")) { New-Item -ItemType Directory -Path "$PSScriptRoot\scripts" }
if (Test-Path '$PSScriptRoot\combosync.ps1') { Move-Item -Path '$PSScriptRoot\combosync.ps1' -Destination '$PSScriptRoot\scripts\combosync.ps1' -Force }
if (-not (Test-Path "$PSScriptRoot\images")) { New-Item -ItemType Directory -Path "$PSScriptRoot\images" }
if (...
```
