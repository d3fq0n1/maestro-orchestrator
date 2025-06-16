import argparse
import json
import uuid
from datetime import datetime
from collections import Counter
import os
import random
import sys

# For loading API keys from a .env file
from dotenv import load_dotenv

# Official, current client libraries for all services
# Ensure you have installed them:
# pip install python-dotenv openai anthropic google-generativeai
import openai
import anthropic
import google.generativeai as genai

# --- Session Management Capsule ---
class GeminiCapsule:
    """Handles loading and saving the conversational session state to a JSON file."""
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
        """Loads an existing session from file or creates a new one."""
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
        """Saves the current session data to the file."""
        self.session_data["last_updated"] = datetime.utcnow().isoformat()
        with open(self.session_file, 'w') as f:
            json.dump(self.session_data, f, indent=2)

    def add_round(self, round_data):
        """Adds a completed orchestration round to the session history."""
        self.session_data["history"].append(round_data)
        self.save_session()

    def get_full_history(self):
        """Returns the entire conversation history."""
        return self.session_data["history"]

# --- Agent Definitions ---
class BaseAgent:
    """Abstract base class for all AI agents."""
    def __init__(self, name):
        self.name = name

    def generate_response(self, prompt: str) -> str:
        raise NotImplementedError

    def vote_on_response(self, prompt: str, responses: dict) -> str:
        raise NotImplementedError

    def _validate_vote(self, choice: str, valid_names: list) -> str:
        """
        Validates the agent's vote. If the choice contains a valid agent name,
        returns that name. Otherwise, returns a random choice.
        """
        for name in valid_names:
            if name.lower() in choice.lower():
                return name
        return random.choice(valid_names)

class OpenAIAgent(BaseAgent):
    """Agent implementation for OpenAI models like GPT-4o."""
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

class ClaudeAgent(BaseAgent):
    """Agent implementation for Anthropic's Claude models."""
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

class GeminiAgent(BaseAgent):
    """Agent implementation for Google's Gemini models."""
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
            choice = response.text.strip()
            return self._validate_vote(choice, list(responses.keys()))
        except Exception as e:
            return f"ERROR: Google Gemini API Error during voting: {e}"

# --- Agent Factory ---
def get_agent_by_name(name, config):
    """Factory function to create agent instances based on name."""
    n = name.lower()
    if n == "sol":
        return OpenAIAgent(name, model="gpt-4o-mini", api_key=config.get("OPENAI_API_KEY"))
    if n == "aria":
        return ClaudeAgent(name, model="claude-3-haiku-20240307", api_key=config.get("ANTHROPIC_API_KEY"))
    if n == "prism": # This is me, Gemini.
        return GeminiAgent(name, model="gemini-1.5-flash-latest", api_key=config.get("GEMINI_API_KEY"))
    if n == "axion":
        return OpenAIAgent(name, model="gpt-4o", api_key=config.get("OPENAI_API_KEY"))
    print(f"WARN: No specific agent class found for '{name}'. It will be skipped.", file=sys.stderr)
    return None

# --- Core Orchestration Function ---
def run_orchestration(agents, prompt, quorum_percent, verbose=False):
    """
    Manages a single round of response generation, voting, and result determination.
    """
    round_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    responses = {}
    votes = {}
    errors = {}

    print("\n--- Generating Responses ---")
    for agent in agents:
        try:
            resp = agent.generate_response(prompt)
            if resp.startswith("ERROR:"):
                errors[agent.name] = resp
            else:
                responses[agent.name] = resp
            if verbose:
                print(f"[{agent.name}] Response:\n{resp}\n")
        except Exception as e:
            errors[agent.name] = f"FATAL Response error: {str(e)}"

    if not responses:
        print("No valid responses were generated. Skipping voting round.", file=sys.stderr)
        return {
            "round_id": round_id, "timestamp": timestamp, "prompt": prompt,
            "summary": "✘ Orchestration failed. No agents produced a valid response.", "errors": errors
        }

    print("\n--- Casting Votes ---")
    voting_agents = [agent for agent in agents if agent.name not in errors]
    for agent in voting_agents:
        try:
            vote = agent.vote_on_response(prompt, responses)
            if vote.startswith("ERROR:"):
                 errors[agent.name] = f"Voting error: {vote}"
            else:
                votes[agent.name] = vote
            if verbose:
                print(f"[{agent.name}] Voted for: {vote}")
        except Exception as e:
            errors[agent.name] = f"FATAL Voting error: {str(e)}"

    vote_counts = Counter(votes.values())
    top_vote, top_count = (vote_counts.most_common(1)[0] if vote_counts else (None, 0))

    quorum_required = int((quorum_percent / 100) * len(votes))
    quorum_met = top_count >= quorum_required and top_vote is not None
    
    summary = "✘ No valid votes received"
    if top_vote:
        summary = f"{'✔' if quorum_met else '✘'} Quorum {'met' if quorum_met else 'not met'}. Winner: {top_vote} ({top_count}/{len(votes)} votes)."

    result = {
        "round_id": round_id, "timestamp": timestamp, "prompt": prompt,
        "configuration": {"agents": [a.name for a in agents], "quorum_percent": quorum_percent},
        "responses": responses,
        "voting_results": {
            "votes_cast": votes, "vote_counts": dict(vote_counts), "top_vote": top_vote,
            "top_count": top_count, "quorum_required": quorum_required, "quorum_met": quorum_met,
        },
        "final_winner": top_vote if quorum_met else None,
        "winning_response": responses.get(top_vote) if quorum_met else None,
        "summary": summary, "errors": errors if errors else None,
    }
    return result

# --- CLI Entrypoint ---
if __name__ == "__main__":
    # Load environment variables from a .env file automatically
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run a Maestro-Orchestrator session.")
    parser.add_argument("--agents", nargs="+", default=["Sol", "Aria", "Prism", "Axion"], help="List of agent names.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt", type=str, help="Single prompt for one orchestration round.")
    group.add_argument("--rounds", nargs="+", help="List of prompts to run as sequential rounds.")

    parser.add_argument("--quorum", type=int, default=51, help="Quorum percentage required for a winning vote.")
    parser.add_argument("--session-file", type=str, default="maestro_session.json", help="File to store conversation history.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output.")
    parser.add_argument("--json-out", type=str, help="Optional JSON output file for the final round result.")
    args = parser.parse_args()

    # The config dictionary is now populated from the loaded .env file
    config = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    }

    agent_objs = [get_agent_by_name(name, config) for name in args.agents]
    agent_objs = [agent for agent in agent_objs if agent is not None]

    if not agent_objs:
        print("FATAL: No agents could be initialized. Check configuration and API keys in your .env file.", file=sys.stderr)
        sys.exit(1)

    capsule = GeminiCapsule(session_file=args.session_file)
    prompts = [args.prompt] if args.prompt else args.rounds

for idx, prompt in enumerate(prompts, 1):
    print("\n" + "=" * 60)
    print(f"\n=== Round {idx}/{len(prompts)}: \"{prompt}\" ===")
    result = run_orchestration(agent_objs, prompt, args.quorum, verbose=args.verbose)
    capsule.add_round(result)

    print("\n--- Orchestration Complete ---")
    print(result['summary'])
    if result.get('final_winner'):
        print(f"\nWinning Response from {result['final_winner']}:\n{result['winning_response']}")

    if result.get('errors'):
        print("\n--- Errors ---")
        for agent, err in result['errors'].items():
            print(f"[{agent}]: {err}")

    if args.json_out:
        base, ext = os.path.splitext(args.json_out)
        out_path = f"{base}_round{idx}{ext}" if len(prompts) > 1 else args.json_out
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved detailed results for this round to: {out_path}")
