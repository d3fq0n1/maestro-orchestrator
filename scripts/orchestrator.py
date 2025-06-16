import argparse
import json
import uuid
from datetime import datetime
from collections import Counter
import os
import random
import sys
import requests
import pandas as pd
from dotenv import load_dotenv

import openai
import anthropic
import google.generativeai as genai

# --- Session Management Capsule ---
class GeminiCapsule:
    def __init__(self, session_file='maestro_session.json'):
        self.session_file = session_file
        self.session_data = {
            "session_id": str(uuid.uuid4()),
            "history": [],
            "token_usage": 0,
            "last_updated": None
        }
        self.load_session()

    def load_session(self):
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    self.session_data = json.load(f)
                    print(f"INFO: Loaded existing session: {self.session_data['session_id']}")
            except (json.JSONDecodeError, IOError) as e:
                print(f"WARN: Could not load session file. Creating a new one. Error: {e}", file=sys.stderr)
                self.save_session()
        else:
            print(f"INFO: No session file found. Creating new session: {self.session_data['session_id']}")
            self.save_session()

    def save_session(self):
        self.session_data["last_updated"] = datetime.utcnow().isoformat()
        with open(self.session_file, 'w') as f:
            json.dump(self.session_data, f, indent=2)

    def add_round(self, round_data):
        self.session_data["history"].append(round_data)
        self.save_session()

    def get_full_history(self):
        return self.session_data["history"]

# --- Base Agent ---
class BaseAgent:
    def __init__(self, name):
        self.name = name

    def generate_response(self, prompt: str) -> str:
        raise NotImplementedError

    def vote_on_response(self, prompt: str, responses: dict) -> str:
        raise NotImplementedError

    def _validate_vote(self, choice: str, valid_names: list) -> str:
        for name in valid_names:
            if name.lower() in choice.lower():
                return name
        return random.choice(valid_names)

# --- OpenAI Agent ---
class OpenAIAgent(BaseAgent):
    def __init__(self, name, model, api_key=None):
        super().__init__(name)
        self.model = model
        if not api_key:
            raise ValueError(f"API key for {self.name} (OpenAI) is missing.")
        self.client = openai.OpenAI(api_key=api_key)

    def generate_response(self, prompt: str) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a world-class expert assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            return resp.choices[0].message.content.strip()
        except openai.APIError as e:
            return f"ERROR: OpenAI API Error: {e}"

    def vote_on_response(self, prompt: str, responses: dict) -> str:
        formatted = "\n\n".join(f"--- RESPONSE FROM {agent} ---\n{resp}" for agent, resp in responses.items())
        vote_prompt = (
            f"The user's original query was: \"{prompt}\"\n\n"
            "Below are the responses from several AI agents. Your task is to analyze them and choose the single best response. "
            f"The available agents are: {', '.join(responses.keys())}.\n\n"
            f"{formatted}\n\n"
            "Considering accuracy, completeness, and clarity, which agent provided the best response? "
            "Reply ONLY with the name of the winning agent."
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an impartial and expert judge."},
                    {"role": "user", "content": vote_prompt}
                ],
                temperature=0,
                max_tokens=10,
            )
            choice = resp.choices[0].message.content.strip()
            return self._validate_vote(choice, list(responses.keys()))
        except openai.APIError as e:
            return f"ERROR: OpenAI API Error during voting: {e}"

# --- Claude Agent ---
class ClaudeAgent(BaseAgent):
    def __init__(self, name, model, api_key=None):
        super().__init__(name)
        self.model = model
        if not api_key:
            raise ValueError(f"API key for {self.name} (Anthropic) is missing.")
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate_response(self, prompt: str) -> str:
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=0.7,
                system="You are a world-class expert assistant.",
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text.strip()
        except anthropic.APIError as e:
            return f"ERROR: Anthropic API Error: {e}"

    def vote_on_response(self, prompt: str, responses: dict) -> str:
        formatted = "\n\n".join(f"--- RESPONSE FROM {agent} ---\n{resp}" for agent, resp in responses.items())
        vote_prompt = (
            f"The user's original query was: \"{prompt}\"\n\n"
            "Below are the responses from several AI agents. Your task is to analyze them and choose the single best response. "
            f"The available agents are: {', '.join(responses.keys())}.\n\n"
            f"{formatted}\n\n"
            "Considering accuracy, completeness, and clarity, which agent provided the best response? "
            "Reply ONLY with the name of the winning agent."
        )
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                temperature=0,
                system="You are an impartial and expert judge.",
                messages=[{"role": "user", "content": vote_prompt}]
            )
            choice = message.content[0].text.strip()
            return self._validate_vote(choice, list(responses.keys()))
        except anthropic.APIError as e:
            return f"ERROR: Anthropic API Error during voting: {e}"

# --- Gemini Agent ---
class GeminiAgent(BaseAgent):
    def __init__(self, name, model, api_key=None):
        super().__init__(name)
        self.model_name = model
        if not api_key:
            raise ValueError(f"API key for {self.name} (Google) is missing.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.model_name)

    def generate_response(self, prompt: str) -> str:
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            return f"ERROR: Google Gemini API Error: {e}"

    def vote_on_response(self, prompt: str, responses: dict) -> str:
        formatted = "\n\n".join(f"--- RESPONSE FROM {agent} ---\n{resp}" for agent, resp in responses.items())
        vote_prompt = (
            f"The user's original query was: \"{prompt}\"\n\n"
            "Below are the responses from several AI agents. Your task is to analyze them and choose the single best response. "
            f"The available agents are: {', '.join(responses.keys())}.\n\n"
            f"{formatted}\n\n"
            "Considering accuracy, completeness, and clarity, which agent provided the best response? "
            "Reply ONLY with the name of the winning agent."
        )
        try:
            response = self.model.generate_content(vote_prompt, generation_config={"temperature": 0, "max_output_tokens": 10})
            return self._validate_vote(response.text.strip(), list(responses.keys()))
        except Exception as e:
            return f"ERROR: Google Gemini API Error during voting: {e}"

# --- OpenRouter Agent ---
class OpenRouterAgent(BaseAgent):
    def __init__(self, name, model, api_key=None):
        super().__init__(name)
        self.model = model
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(f"API key for {self.name} (OpenRouter) is missing.")
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

    def _chat(self, messages, temperature=0.7, max_tokens=1024):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            resp = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"ERROR: OpenRouter API Error: {e}"

    def generate_response(self, prompt: str) -> str:
        return self._chat([
            {"role": "system", "content": "You are a world-class expert assistant."},
            {"role": "user", "content": prompt}
        ])

    def vote_on_response(self, prompt: str, responses: dict) -> str:
        formatted = "\n\n".join(f"--- RESPONSE FROM {agent} ---\n{resp}" for agent, resp in responses.items())
        vote_prompt = (
            f"The user's original query was: \"{prompt}\"\n\n"
            "Below are the responses from several AI agents. Your task is to analyze them and choose the single best response. "
            f"The available agents are: {', '.join(responses.keys())}.\n\n"
            f"{formatted}\n\n"
            "Considering accuracy, completeness, and clarity, which agent provided the best response? "
            "Reply ONLY with the name of the winning agent."
        )
        raw = self._chat([
            {"role": "system", "content": "You are an impartial and expert judge."},
            {"role": "user", "content": vote_prompt}
        ], temperature=0, max_tokens=10)
        return self._validate_vote(raw, list(responses.keys()))

# --- Agent Registry ---
def get_agent_by_name(agent_name, api_keys):
    alias_map = {
        "sol": ["sol", "openai"],
        "aria": ["aria", "claude"],
        "prism": ["prism", "gemini"],
        "openrouter": ["openrouter", "router"]
    }
    for canonical, aliases in alias_map.items():
        if agent_name.lower() in aliases:
            agent_name = canonical
            break

    agent_map = {
        "sol": lambda: OpenAIAgent("Sol", model="gpt-4", api_key=api_keys.get("OPENAI_API_KEY")),
        "aria": lambda: ClaudeAgent("Aria", model="claude-3-opus-20240229", api_key=api_keys.get("ANTHROPIC_API_KEY")),
        "prism": lambda: GeminiAgent("Prism", model="gemini-1.5-flash", api_key=api_keys.get("GOOGLE_API_KEY")),
        "openrouter": lambda: OpenRouterAgent("OpenRouter", model="mistralai/mistral-7b-instruct:free", api_key=api_keys.get("OPENROUTER_API_KEY")),
    }

    if agent_name in agent_map:
        return agent_map[agent_name]()
    else:
        raise ValueError(f"Unknown agent name: {agent_name}")

# --- Orchestration Logic ---
def run_orchestration(prompt, agent_names, api_keys, session, verbose=True):
    agents = {name: get_agent_by_name(name, api_keys) for name in agent_names}

    if verbose:
        print("\n--- Generating responses ---")
    responses = {name: agent.generate_response(prompt) for name, agent in agents.items()}

    if verbose:
        print("\n--- Responses ---")
        for name, response in responses.items():
            print(f"\n[{name}]\n{response}\n")

    if verbose:
        print("--- Voting round ---")
    votes = [agent.vote_on_response(prompt, responses) for agent in agents.values()]
    tally = Counter(votes)
    winner = tally.most_common(1)[0][0]

    if verbose:
        print(f"\n✅ Winning agent: {winner} with {tally[winner]} vote(s)")

    session.add_round({
        "prompt": prompt,
        "responses": responses,
        "votes": dict(tally),
        "winner": winner,
        "timestamp": datetime.utcnow().isoformat()
    })

# --- CLI Entrypoint ---
if __name__ == "__main__":
    load_dotenv()

    parser = argparse.ArgumentParser(description="Maestro-Orchestrator CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt", type=str, help="Single prompt to ask the agents")
    group.add_argument("--rounds", nargs='+', help="Multiple prompts to run in sequence")
    group.add_argument('--input-file', type=str, help='Path to CSV file containing prompt list')
    parser.add_argument("--agents", nargs='+', default=["sol", "aria", "prism", "openrouter"], help="List of agents to include")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle prompt order if using CSV")

    args = parser.parse_args()

    if args.input_file:
        try:
            df = pd.read_csv(args.input_file)
            if "Question" not in df.columns:
                sys.exit("ERROR: CSV must contain a 'Question' column.")
            questions = df["Question"].dropna().tolist()
            if args.shuffle:
                random.shuffle(questions)
            prompts = questions
        except Exception as e:
            sys.exit(f"ERROR: Failed to read input file: {e}")
    else:
        prompts = [args.prompt] if args.prompt else args.rounds

    keys = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY"),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY"),
    }

    capsule = GeminiCapsule()

    for prompt in prompts:
        run_orchestration(prompt, args.agents, keys, capsule, verbose=not args.quiet)
