from ai_client import AzureAIClient

class PlannerAgent:
    def __init__(self, ai_client: AzureAIClient):
        self.ai_client = ai_client

    def create_plan(self, user_request: str) -> str:
        prompt = f"""
You are the Planner Agent for an Azure Site Recovery AI Orchestrator.

Your job is to create a safe, step-by-step execution plan.
Do not execute Azure changes.
Do not assume missing values.
Ask for missing required information.

User request:
{user_request}

Return:
1. Understood request
2. Missing information
3. Precheck plan
4. Execution plan
5. Approval gate
"""
        return self.ai_client.ask(prompt)