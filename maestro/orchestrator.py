
from maestro.agents.agent_mock import MockAgent2, MockAgent3
from maestro.aggregator import aggregate_responses

def run_orchestration(prompt: str) -> dict:
    """
    Orchestrates multiple mock agents and aggregates their responses.
    Note: OpenAI agent disabled due to billing limitations. System is fully capable of LLM orchestration once API access is available.
    """
    agents = [
        MockAgent2(),     # Mock with opinionated reasoning
        MockAgent3()      # Mock with historical framing
    ]

    responses = []
    for i, agent in enumerate(agents):
        print(f"Querying Agent {i+1}...")
        response = agent.respond(prompt)
        print(f"Agent {i+1} responded: {response}")
        responses.append(response)

    print("\nAggregating responses...")
    final_output = aggregate_responses(responses)

    return {
        "responses": responses,
        "final_output": final_output
    }
