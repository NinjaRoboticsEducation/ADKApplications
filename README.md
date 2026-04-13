# Developing Local AI Applications with Google Agent Development Kit and Gemma 4

## Introduction and Prerequisite Clarifications

The paradigm of artificial intelligence development is experiencing a rapid and fundamental shift. We are moving away from monolithic, cloud-dependent large language models toward modular, locally hosted agentic systems. This evolution affords application developers unprecedented control over data privacy, inference costs, and system latency. The Google Agent Development Kit (ADK) represents a foundational, open-source framework designed to orchestrate these sophisticated applications, enabling developers to build production-ready multi-agent systems with greater flexibility and precise control. By combining the ADK with local model serving runtimes such as Ollama, it is now entirely feasible to run complex, reasoning-capable agents on consumer hardware without relying on external Application Programming Interfaces (APIs).

To ensure complete educational clarity throughout this comprehensive guide, several foundational concepts must be defined. **Inference** refers to the computational process by which a trained artificial intelligence model generates text or predictions based on user inputs or prompts. **RAG** (Retrieval-Augmented Generation) is a popular architectural pattern that significantly improves model accuracy and reduces hallucinations; it works by fetching relevant external data from a database and appending it to the user's prompt just before inference occurs, essentially giving the model a search engine to read from before it answers. **Quantization** is a mathematical compression technique that reduces the precision of a model's internal weights (for example, converting highly precise 16-bit floating-point numbers to smaller 4-bit integers). This process drastically lowers the amount of Random Access Memory (RAM) required to load and run the model, without proportionally degrading its reasoning capabilities.

Before proceeding with the design of a specialized agentic architecture, rigorous engineering principles dictate that we must verify the operational parameters. To answer the query correctly and precisely without guessing, and to tailor the architecture perfectly to the underlying needs, I must formally request clarification on several system requirements. Never assuming system requirements is a cornerstone of robust software development. In a live consultation environment, the following clarifying questions would be mandatory to confirm before finalizing the codebase:

| Clarification Category | Specific Questions to Confirm Architecture | Architectural Impact |
| :--- | :--- | :--- |
| **Operational Latency** | What is the maximum acceptable time-to-first-token (TTFT) for the end user? | Dictates whether we can use larger, slower models or if we must rely on smaller, highly quantized edge models. |
| **Offline Compliance** | Does the application operate in an air-gapped environment with strict security compliance? | Determines if we can utilize hybrid setups (e.g., using Vertex AI for complex routing) or if 100% local Ollama execution is mandatory. |
| **Tool Execution Risk** | Will the agent execute destructive actions (e.g., modifying databases, writing files)? | Requires the implementation of "human-in-the-loop" approval plugins within the ADK if the risk is high. |
| **Context Retention** | How far back does the agent need to remember user interactions? | Influences the choice between short-term in-memory sessions versus persistent database-backed long-term memory banks. |

Operating under the assumption that the goal is to construct a highly robust, offline-capable, and modular agentic architecture that prioritizes reasoning, autonomous tool-use, and structured memory management on the specified hardware, the following sections provide an exhaustive, step-by-step masterclass on implementing this system.

## Hardware Analysis and Model Selection Strategy

Selecting the appropriate large language model is arguably the most critical architectural decision when designing a local agentic system. An agent is only as capable as its underlying reasoning engine. The agent's ability to plan multi-step processes, route tasks to sub-agents, and execute precise function calls relies entirely on the model's inherent logical capabilities and its training regarding structured outputs.

The target hardware environment for this deployment is a MacBook Pro equipped with an Apple Silicon M-series processor (e.g., M2 Max) and 32 Gigabytes (GB) of RAM. Apple Silicon's architecture, specifically its Unified Memory, is highly advantageous for local artificial intelligence. Unlike traditional PC architectures where the Central Processing Unit (CPU) and Graphics Processing Unit (GPU) have separate memory pools connected by a slow data bus, Apple's Unified Memory allows the GPU to directly access the entire 32 GB RAM pool. This eliminates the massive bottleneck of transferring model weights between system RAM and dedicated Video RAM (VRAM). However, 32 GB is a hard physical limit. The operating system will consume several gigabytes, leaving a constrained envelope for the model weights and the context window (the temporary memory used to hold the current conversation).

### Analysis of the Gemma 4 Family

The Gemma 4 series is a family of open-weights models built by Google DeepMind. Released as an evolution of the Gemma architecture, the Gemma 4 models are explicitly optimized for handling complex logic and agentic workflows, moving far beyond simple chatbot interactions. They feature native function-calling support, making them perfectly suited for the ADK. The models are available in four distinct sizes, each tailored to different hardware tiers.

| Model Variant | Architecture Type | Active Parameters | Total Parameters | Base VRAM/RAM Requirement (Unquantized) |
| :--- | :--- | :--- | :--- | :--- |
| Gemma 4 E2B | Dense | 2.3 Billion | 5.1 Billion | ~10 GB |
| Gemma 4 E4B | Dense | 4.5 Billion | 8.0 Billion | ~16 GB |
| Gemma 4 26B A4B | Mixture-of-Experts (MoE) | 3.8 Billion | 25.2 Billion | ~52 GB |
| Gemma 4 31B | Dense | 30.7 Billion | 30.7 Billion | ~62 GB |

The "E" in the E2B and E4B models stands for "Effective" parameters, and these are dense models specifically designed for edge device deployments like mobile phones or lightweight laptops. A dense model is one where every single parameter (artificial neuron connection) is activated during every single word prediction. While highly capable for their size, the E2B and E4B models often lack the deep, nuanced reasoning required for complex, multi-step agentic planning.

Conversely, the 31B Dense model offers state-of-the-art accuracy but requires a massive 62 GB of unified memory to run unquantized. Even when heavily quantized, running the 31B model on a 32 GB machine would leave absolutely no room for the Key-Value (KV) cache. The KV cache is the memory the model uses to remember the prompt you just sent it. If the KV cache cannot fit in RAM, the computer will begin "swapping" (using the much slower solid-state hard drive as overflow memory), which degrades token generation speed from lightning-fast to completely unusable.

### The Optimal Recommendation: Gemma 4 26B MoE

For an agentic workflow operating on a 32 GB M2 Max machine, the Gemma 4 26B A4B model is the definitively optimal choice. This model utilizes a Mixture-of-Experts (MoE) architecture. MoE is a revolutionary neural network design that divides the massive model into smaller, specialized sub-networks called "experts." During inference, a routing mechanism evaluates the current word being processed and activates only the most relevant experts. Therefore, while the model contains 25.2 billion total parameters of deep knowledge, it only activates 3.8 billion parameters at any given time. This allows the 26B model to provide the profound reasoning capabilities of a massive workstation model while running with the speed and computational cost of a small laptop model.

To fit this 25.2 billion parameter model into 32 GB of RAM, we must employ quantization. The Ollama runtime offers various quantization formats. The `Q4_K_M` format (4-bit quantization) compresses the model down to approximately 15 GB. This is the ideal balance. By occupying only 15 GB for the model weights, the system reserves ample memory for macOS background processes and leaves a large buffer for the context window. While Ollama defaults to a 2048-token context window, utilizing the 4-bit quantization on a 32 GB machine allows us to safely expand the context window to 8192 tokens. This expansion is critical for agentic workflows, as the agent must often ingest massive amounts of text returned by its tools (like web search results or database dumps) before formulating an answer.

### Alternative Model Considerations

If the user's specific workflow demands a multi-agent hierarchy where several smaller agents run simultaneously in parallel, the 26B model may consume too much memory. In such highly concurrent scenarios, alternative models should be considered:

*   **Qwen 2.5 / Qwen 3 (7B or 14B):** The Qwen series is renowned in the open-source community for its exceptional adherence to JSON formatting, making it incredibly reliable for strict tool calling and function execution.
*   **DeepSeek-Coder (V2 Lite):** If the ADK agent's primary purpose is automated software development, repository analysis, or code generation, the DeepSeek family provides superior syntax comprehension compared to generalized models.
*   **Gemma 4 E4B:** If battery life and thermals are the absolute priority, the 4-billion parameter Gemma variant runs effortlessly on the M2 Max, requiring only about 5.5 to 6 GB of memory in 4-bit quantization, though it may struggle with highly abstract reasoning tasks.

## Comprehensive Environment Setup and Installation Guide

Deploying a local AI application requires meticulous configuration of both the model serving runtime (Ollama) and the Python application execution environment (Google ADK). The following step-by-step instructions provide clear guidance that can be followed sequentially to ensure a clean, isolated environment, preventing dependency conflicts with other software on the macOS system.

### Step 1: Installing and Configuring Ollama

Ollama is an open-source inference engine that loads quantized model weights and serves them via a lightweight, local REST API. This API mimics the OpenAI standard, allowing frameworks like the ADK to interact with local models as if they were cloud services.

1. Navigate to the official Ollama website and download the macOS installation package. Run the installer to place the application in your Applications folder.
2. Open the macOS Terminal application.
3. Start the Ollama server process to ensure it is actively listening for requests in the background. Execute the following command:
   ```bash
   ollama serve
   ```
4. Open a second, new Terminal window. You will now pull the recommended 4-bit quantized version of the Gemma 4 26B model from the Ollama registry. Execute this command:
   ```bash
   ollama pull gemma4:26b
   ```
   *Note: This download is approximately 15 GB to 18 GB and will take time depending on your internet connection bandwidth.*

### Step 2: Optimizing the Context Window via Modelfile

To fully utilize the 32 GB of RAM available on the M2 Max and allow the agent to process extensive tool outputs, we must create a custom Ollama `Modelfile` to explicitly expand the context window.

1. In the terminal, create a new file named `Modelfile` and populate it with the necessary configuration parameters using the following command snippet:
   ```bash
   cat << 'EOF' > Modelfile
   FROM gemma4:26b
   PARAMETER num_ctx 8192
   PARAMETER temperature 0.2
   EOF
   ```
   *Educational Note: The `num_ctx` parameter defines the maximum number of tokens the model can remember in a single session. The `temperature` parameter controls the creativity of the model. A lower temperature (0.2) makes the model more deterministic and analytical, which is highly preferred for agents that must follow strict formatting rules for tool use.*

2. Build the customized model variant within Ollama:
   ```bash
   ollama create gemma4-agent -f Modelfile
   ```
3. Verify that your newly created model is available in the local registry:
   ```bash
   ollama list
   ```

### Step 3: Installing the Google Agent Development Kit (ADK)

The Google Agent Development Kit requires Python version 3.9 or higher to function correctly. It is highly recommended to use a Python virtual environment to encapsulate the project dependencies.

1. Create a dedicated directory for your agent project and navigate into it:
   ```bash
   mkdir local_adk_project
   cd local_adk_project
   ```
2. Initialize a Python virtual environment. This creates a sandboxed area for Python packages:
   ```bash
   python3 -m venv .venv
   ```
3. Activate the virtual environment. This command must be run every time you open a new terminal to work on the project:
   ```bash
   source .venv/bin/activate
   ```
4. Install the Google ADK framework using the Python Package Installer (pip). We will also install `litellm`. LiteLLM is a critical routing library that acts as a translation bridge. Because the ADK natively defaults to expecting Google Cloud Vertex AI endpoints, LiteLLM intercepts these requests and formats them perfectly for the local Ollama REST API.
   ```bash
   pip install google-adk litellm
   ```

## The "Hello World" Application Tutorial

With the environment perfectly configured, we can now construct a foundational AI application. This tutorial will demonstrate how to build an autonomous agent equipped with a custom tool, and how to execute it locally using the Gemma 4 model.

### Resolving Local Connectivity and Auth Bugs

Before writing the code, it is imperative to address two known bugs when using the ADK completely offline with Ollama:

1.  **The Local Tool-Calling Routing Bug:** If a developer specifies the model provider simply as `ollama`, the model will often enter an infinite loop of tool calls. To circumvent this, explicitly use the `ollama_chat` provider prefix in the LiteLLM configuration (`"ollama_chat/gemma4-agent"`). This forces the LiteLLM bridge to utilize the OpenAI-compatible `/v1/chat/completions` endpoint exposed by Ollama, which robustly and natively supports function calling.
2.  **The Vertex AI Authentication Error:** The ADK orchestrator (`AdkApp`) implicitly triggers the `vertexai` library initialization behind the scenes. This expects a valid Google Cloud project ID and associated Application Default Credentials (ADC). Without these, it throws a `GoogleAuthError`. To bypass this, we explicitly initialize the Vertex SDK using "dummy" anonymous credentials at the top of our script.

### Code Implementation

Create a new file named `agent.py` in your project directory. Copy and paste the following heavily commented code block. 

```python
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
# An LLM is essentially a brain in a jar; it cannot affect the real world.
# Tools are standard Python functions that serve as the agent's hands.
# The docstring (the text inside the triple quotes) is absolutely critical.
# The model reads this exact docstring to understand what the tool does.
def get_system_status(service_name: str) -> dict:
    """
    Checks the current status of a simulated internal enterprise system.
    
    Args:
        service_name: The name of the service to check (e.g., 'database', 'web_server').
        
    Returns:
        A dictionary containing the operational status and uptime of the service.
    """
    print(f"\n[Executing Tool] Checking status for '{service_name}'...")
    
    mock_status_db = {
        "database": {"status": "operational", "uptime": "99.9%", "issues": "None"},
        "web_server": {"status": "degraded", "uptime": "95.0%", "issues": "High latency"},
        "auth_service": {"status": "offline", "uptime": "0.0%", "issues": "Server crashed"}
    }
    
    normalized_name = service_name.lower().replace(" ", "_")
    
    if normalized_name in mock_status_db:
        return mock_status_db[normalized_name]
    else:
        return {"status": "error", "message": f"Service '{service_name}' not found."}

# =====================================================================
# 2. Configure the Local Model Connection
# =====================================================================
# We instantiate the ADK LiteLlm wrapper to bridge the ADK to Ollama.
# Crucially, we use the 'ollama_chat/' prefix to avoid the infinite loop bug.
local_model = LiteLlm(model="ollama_chat/gemma4-agent")  

# =====================================================================
# 3. Define the Root Agent
# =====================================================================
infrastructure_agent = Agent(
    model=local_model,
    name="system_monitor_agent",
    description="An autonomous agent that monitors enterprise system health.",
    instruction=(
        "You are a highly capable IT monitoring assistant. "
        "When a user asks about a system, you must ALWAYS use the get_system_status tool to check it. "
        "Never guess the status of a system. "
        "Always summarize your findings in a professional, concise manner."
    ),
    tools=[get_system_status] # We register the Python function as a tool here
)

# =====================================================================
# 4. Wrap in AdkApp and Execute
# =====================================================================
# The AdkApp class manages the asynchronous event loop and intercepts tool calls.
app = AdkApp(agent=infrastructure_agent)

async def main():
    user_id = "macbook_admin_01"
    print("--- ADK Local Agent Initialized successfully ---")
    
    # Create an active conversation session. Since Session is a Pydantic object,
    # we correctly access the ID via dot notation.
    session = await app.async_create_session(user_id=user_id)
    session_id = session.id
    
    user_prompt = "Can you check if the database is running smoothly, and also check the web server?"
    print(f"\nUser: {user_prompt}")
    
    # We execute the query asynchronously. We pass the session_id so the agent
    # remembers what is happening in this specific chat.
    # Note: async_stream_query yields an async_generator, so it must not be 'awaited' directly.
    response_stream = app.async_stream_query(
        user_id=user_id,
        session_id=session_id,
        message=user_prompt
    )
    
    print("\nAgent Response: ", end="")
    # Use 'async for' to correctly iterate over the asynchronous stream chunks
    async for chunk in response_stream:
        # Check if the chunk contains text content meant for the user
        if "content" in chunk and "text" in chunk["content"]:
            print(chunk["content"]["text"], end="", flush=True)
    print("\n")

if __name__ == "__main__":
    # Point LiteLlm/ADK to the locally running Ollama instance safely
    os.environ["OLLAMA_API_BASE"] = "http://localhost:11434"
    
    # Run the asynchronous main function
    asyncio.run(main())
```

### Understanding the Execution Flow

To run the application, ensure your virtual environment is activated and execute:

```bash
./.venv/bin/python agent.py
```

When you run this script, the ADK framework handles the background orchestration. First, it wraps your `user_prompt` and the system `instruction` together. It converts your Python function `get_system_status` into a JSON Schema and sends all of this to Gemma 4 via the Ollama REST API.

Gemma 4 analyzes the prompt, reads the JSON schema, and outputs a special "tool call" payload. The ADK intercepts this payload, pauses the model, executes your Python function locally, and captures the resulting dictionary (`{"status": "operational", "uptime": "99.9%", "issues": "None"}`). 

The ADK then sends a new request back to Gemma 4 containing the returned tool data. The model reads the result, synthesizes a natural language response summarizing the statuses, and streams it back to your terminal screen.

---

## Visualizing and Debugging: Using the ADK Web Local UI

While executing scripts from the terminal is excellent for production deployment, building and debugging complex agents requiring high visibility into the conversational flow benefits enormously from a visual interface. The ADK ecosystem provides a powerful integrated web tool for local visualization and debugging.

The ADK framework bundles a streamlined Web UI that connects directly to the agents declared in your project. It acts as a sandbox space to chat with your agent visually, inspect tool call requests piece by piece, and adjust prompts rapidly.

### How to Launch the Web UI

1. **Ensure Environment Variables are Ready:** Make sure your `.venv` is activated.
2. **Launch the Interface:** Open your terminal in the directory where your project lives and run the built-in CLI command:
   ```bash
   adk web
   ```
3. **Accessing the Portal:**  The `adk` command will launch a local development server (typically hosted on `http://localhost:8000` or port 8080). Open a standard web browser (Chrome, Safari, Mozilla) and navigate to the provided localhost URL.
4. **Interactive Sandbox:** From the interface, you can select any `Agent` you have defined in your codebase. You can trace its decision-making steps, view raw JSON requests for tool calls, and observe exactly what data the agent extracts from your Python tools visually. 

The web UI drastically lowers the turnaround time for refining agent system instructions, making it the preferred method for developing advanced workflows.

---

## Project Structure and Core Concepts

As applications scale, maintaining a highly organized project architecture becomes paramount. The ADK was explicitly designed to apply standard software engineering principles. Placing all code into a single `agent.py` file is an anti-pattern that leads to unmaintainable code.

A standard, scalable ADK project directory should be structured logically to separate concerns:

```
local_adk_project/
├── .env                  # Environment variables (API keys, Ollama base URLs)
├── requirements.txt      # Python dependencies for reproducible builds
├── main.py               # The application entry point and Runner configuration
├── agents.py             # Declarations of the LLM Agents and their prompts
├── tools.py              # Custom Python functions exposed as tools
├── plugins.py            # Extensions for monitoring, tracing, or event logging
└── skills/               # Directory-based specialized Agent Skills
    └── database_admin/   
        ├── SKILL.md      # Core instructions for the database administration skill
        └── references/   # Supplementary domain knowledge files
```

### Description of Core Files and Their Purposes

1.  **`agents.py` (Agent Orchestration):** Defines the `Agent` objects. In a multi-agent architecture, the developer defines a `RouterAgent` that delegates tasks to a specialized `CodeAgent` or `ResearchAgent`. Defining these agents in a dedicated file prevents the application logic from becoming entangled with prompt engineering.
2.  **`tools.py` (Capability Integration):** Tools are discrete, callable capabilities with strongly typed inputs and structured results. Isolating them allows developers to perform rigorous unit testing on the functions independently of the LLM. 
3.  **`main.py` (The Runner):** The runner is responsible for initializing the `AdkApp`, establishing connections to databases for persistent session storage, loading environment variables via the `dotenv` library, and managing standard interfaces.
4.  **`plugins.py` (Observability):** Developers can write plugins to intercept events occurring within the agent loop, such as a `LoggerPlugin` to write overy tool call to a log file.

## Extending the Architecture: Model Context Protocol (MCP) Integration

While defining tools as simple Python functions within `tools.py` is effective for internal application logic, modern AI systems frequently require access to massive external datasets, enterprise software systems, and complex third-party APIs. To solve this interoperability crisis, the industry has widely adopted the **Model Context Protocol (MCP)**.

MCP is an open-source standard originally pioneered by Anthropic that dictates exactly how AI models securely access external resources and tools. By building or connecting to an existing MCP Server, a developer can instantly grant their ADK agent access to local file systems, PostgreSQL databases, GitHub repositories, or Google Cloud services without writing any custom API wrapper code.

### Implementing an MCP Toolset within the ADK

The Google Agent Development Kit fully supports MCP. To connect the agent to an external MCP server, the developer utilizes the `MCPToolset` class. The following example demonstrates how to integrate a local filesystem MCP server using the stdio transport channel.

1.  **Import the necessary modules:** 
    ```python
    import os
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioServerParameters
    ```

2.  **Define the `MCPToolset` connection parameters:** This instructs the ADK on how to launch the external server process:
    ```python
    # Configure the MCP Toolset to connect to a local server
    file_system_mcp_tools = MCPToolset(
        connection_params=StdioServerParameters(
            command='npx',
            # Launch the filesystem MCP server and grant it access to a specific folder
            args=['-y', '@modelcontextprotocol/server-filesystem', '/Users/Shared'],
            env=os.environ.copy() 
        )
    )
    ```

3.  **Register the `MCPToolset` with the Agent:** During initialization, the ADK automatically interrogates the MCP server, retrieves available tools, and exposes them seamlessly to the model:
    ```python
    research_agent = Agent(
        model=local_model,
        name="research_assistant",
        instruction="You are a data analyst. Use the provided file system tools to read local files.",
        tools=[file_system_mcp_tools]
    )
    ```

By leveraging MCP, the agent breaks free from the limitations of simple Python functions, gaining the ability to interact dynamically with entire local ecosystems or complex cloud architectures in a highly standardized manner.

## Extending the Architecture: Designing Agent Skills

An Agent Skill is a structured, modular package of instructions and resources that an agent can load dynamically only when it is required. This implements a "just-in-time" knowledge retrieval system, drastically optimizing the context window for large instruction sets.

### Directory-Based Skill Architecture

The framework utilizes a specific three-level hierarchy for organizing these skills:
*   **L1 (Metadata):** YAML frontmatter located at the top of the `SKILL.md` file. This defines the skill's name and description.
*   **L2 (Instructions):** The Markdown body of `SKILL.md` containing the detailed logical instructions.
*   **L3 (Resources):** Supplementary text files stored in a `references/` subdirectory. 

The `SKILL.md` file acts as the brain of the operation, formatted as follows:

```markdown
---
name: python_security_reviewer
description: A specialized skill for analyzing Python code for security vulnerabilities.
---

# Instructions
You are an expert cybersecurity auditor. When asked to review code, follow these steps strictly:
1. Identify all input validation points in the provided code snippet.
2. Check for hardcoded credentials or insecure API key handling.
3. If specific cryptographic standards are required, use the `load_skill_resource` tool to read the `references/security_guidelines.md` file.
```

### Loading Skills into the Agent

To expose this directory-based skill to the Gemma 4 model:

```python
import pathlib
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.skills.loaders import load_skill_from_dir

# 1. Resolve the absolute path to the skills directory
skills_dir = pathlib.Path(__file__).parent / "skills" / "code_reviewer"

# 2. Load the skill from the directory structure
security_skill = load_skill_from_dir(skills_dir)

# 3. Package the skill into a toolset
skill_toolset = SkillToolset(skills=[security_skill])

# 4. Assign the toolset to the agent
security_agent = Agent(
    model=local_model,
    name="auditor_agent",
    instruction="You are an auditing agent. Load relevant skills to get detailed instructions.",
    tools=[skill_toolset] 
)
```

## Extending the Architecture: State, Sessions, and Persistent Memory

Agents operating in isolation cannot maintain multi-turn conversations. Each prompt is treated as a completely blank slate. The ADK solves this through state management: short-term **Sessions** and long-term **Memories**.

### Managing Short-Term Context (Sessions)

A session represents a single conversational thread. It records the sequences of user prompts, agent responses, and tool requests. Running locally, the `AdkApp` utilizes an `InMemorySessionService`.

To ensure contextual continuity, retrieve a session ID upon initialization and pass it into subsequent query calls:

```python
# Initialize an in-memory session for a specific user
session = await app.async_create_session(user_id="developer_01")
current_session_id = session.id

# First interaction
await app.async_stream_query(
    user_id="developer_01",
    session_id=current_session_id,
    message="Hello, my favorite programming language is Python."
)

# Second interaction within the same session
response = app.async_stream_query(
    user_id="developer_01",
    session_id=current_session_id,
    message="What did I say my favorite language was?"
)
# The agent will successfully recall "Python".
```

For production deployments, developers persist these sessions permanently by overriding the default service with a `DatabaseSessionService` backed by SQL.

### Managing Long-Term Context (Memory)

Long-term memory allows the agent to recall vital information across entirely different sessions weeks later.

1. **Integrating the Memory Tool:** Add the `PreloadMemoryTool` to the agent's tool array.
   ```python
   from google.adk.tools.preload_memory_tool import PreloadMemoryTool
   
   memory_agent = Agent(
       model=local_model,
       name="stateful_assistant",
       instruction="Use the PreloadMemoryTool to check user preferences.",
       tools=[PreloadMemoryTool()]
   )
   ```

2. **Committing Sessions to Memory:** Explicitly instruct the ADK to analyze a completed session, extract permanent data points, and store them securely.
   ```python
   # After a meaningful session concludes, extract and save facts
   await app.async_add_session_to_memory(session=completed_session_object)
   ```

## Conclusion

The convergence of the Google Agent Development Kit and highly capable local models like the Gemma 4 26B represents a monumental leap forward in software application development. By successfully deploying this architecture on an Apple Silicon machine utilizing Unified Memory, developers can completely bypass the latency bottlenecks, exorbitant inference costs, and stringent data privacy concerns associated with cloud-based LLM APIs. 

The ADK provides the necessary, robust scaffolding to elevate static language models from simple chatbots to autonomous, action-oriented reasoning engines. Through the meticulous implementation of custom function tools, the integration of third-party enterprise ecosystems via the Model Context Protocol (MCP), and the modular instruction management provided by Agent Skills, the developer is empowered to construct highly sophisticated intelligent systems natively.
