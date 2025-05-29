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
