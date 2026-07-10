from config import load_config
from ai_client import AzureAIClient
from agents.planner_agent import PlannerAgent

def main():
    config = load_config()
    ai_client = AzureAIClient(config)
    planner = PlannerAgent(ai_client)

    user_request = "Replicate VM FinanceVM01 from East US to Central US."

    plan = planner.create_plan(user_request)

    print(plan)

if __name__ == "__main__":
    main()