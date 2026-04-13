import os
import asyncio
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm  
from vertexai.agent_engines import AdkApp
from google.auth.credentials import AnonymousCredentials
import vertexai

# =====================================================================
# 0. Global Authentication Failsafes
# =====================================================================
# Initialize vertexai with dummy credentials to bypass GoogleAuthError 
# when working locally without a Google Cloud Project configuration.
vertexai.init(project="local-dummy-project", location="us-central1", credentials=AnonymousCredentials())

# =====================================================================
# 1. Define Tools (The Agent's Capabilities)
# =====================================================================
def get_available_tools() -> list:
    """
    Checks the agent system to return a list of all currently available tools the agent can use.
    
    Returns:
        A list of string names for the tools.
    """
    print("\n[Executing Tool] Checking available tools...")
    return ["get_available_tools", "get_equipped_skills"]

def get_equipped_skills() -> list:
    """
    Checks the local project structure to return a list of all skills equipped to the system.
    
    Returns:
        A list of string names for the skills equipped.
    """
    print("\n[Executing Tool] Checking equipped skills...")
    # Navigate to the skills directory in the project structure
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skills_dir = os.path.join(project_root, "skills")
    
    if os.path.exists(skills_dir) and os.path.isdir(skills_dir):
        skills = [d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d))]
        if skills:
            return skills
            
    return ["No skills currently equipped."]

# =====================================================================
# 2. Configure the Local Model Connection
# =====================================================================
# We instantiate the ADK LiteLlm wrapper to bridge the ADK to Ollama.
local_model = LiteLlm(model="ollama_chat/gemma4-agent")  

# =====================================================================
# 3. Define the Root Agent
# =====================================================================
root_agent = Agent(
    model=local_model,
    name="system_chatbot_agent",
    description="A chatbot that helps users understand the current agent system, available tools, and equipped skills.",
    instruction=(
        "You are a helpful system agent assistant. "
        "Your primary job is to inform the user about the system's capabilities. "
        "When asked about available tools, you must use the get_available_tools tool to list them. "
        "When asked about equipped skills, you must use the get_equipped_skills tool to list them. "
        "Answer questions clearly and concisely."
    ),
    tools=[get_available_tools, get_equipped_skills]
)

# =====================================================================
# 4. Wrap in AdkApp and Execute
# =====================================================================
# The AdkApp class manages the asynchronous event loop and intercepts tool calls.
app = AdkApp(agent=root_agent)

async def main():
    user_id = "macbook_admin_01"
    print("--- ADK Local System Chatbot Initialized successfully ---")
    
    session = await app.async_create_session(user_id=user_id)
    session_id = session.id
    
    user_prompt = "What tools and skills do you have available?"
    print(f"\nUser: {user_prompt}")
    
    response_stream = app.async_stream_query(
        user_id=user_id,
        session_id=session_id,
        message=user_prompt
    )
    
    print("\nAgent Response: ", end="")
    async for chunk in response_stream:
        if "content" in chunk and "text" in chunk["content"]:
            print(chunk["content"]["text"], end="", flush=True)
    print("\n")

if __name__ == "__main__":
    os.environ["OLLAMA_API_BASE"] = "http://localhost:11434"
    asyncio.run(main())
