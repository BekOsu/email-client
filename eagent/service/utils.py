import os
import time
import logging
from dotenv import load_dotenv
from langchain_community.agent_toolkits import GmailToolkit

from langchain import hub
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain_community.callbacks import get_openai_callback
from langsmith import traceable
import tiktoken
from langchain_community.tools.gmail.utils import (
    build_resource_service,
    get_gmail_credentials,
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

model_name = os.getenv("OPENAI_API_MODEL", "gpt-3.5-turbo")
api_key = os.getenv("OPENAI_API_KEY")
credentials_path = os.getenv(
    "CREDENTIALS_PATH", "/path/to/credentials.json"
)

if not api_key:
    raise ValueError("The OPENAI_API_KEY environment variable is not set.")

# Define maximum token limits for the model
MAX_TOKENS = 4000  # Adjust based on your model (e.g., 8000 for GPT-4)


# Token counting utility
def calculate_token_count(input_data: dict, model: str = "gpt-4o-mini") -> int:
    """
    Calculate the number of tokens in the input data for a specific model.
    """
    encoding = tiktoken.encoding_for_model(model)
    token_count = 0

    for key, value in input_data.items():
        token_count += len(encoding.encode(key))
        if isinstance(value, str):
            token_count += len(encoding.encode(value))
        elif isinstance(value, dict):
            token_count += calculate_token_count(value, model)

    return token_count


def validate_and_truncate_input(input_data: dict, model: str = "gpt-4o-mini") -> dict:
    """
    Validate and truncate input to ensure it stays within the token limit.
    """
    encoding = tiktoken.encoding_for_model(model)
    token_count = calculate_token_count(input_data, model)
    if token_count > MAX_TOKENS:
        logger.warning(
            f"Input exceeds token limit ({token_count} tokens). Truncating input to fit within {MAX_TOKENS} tokens."
        )
        # Truncate the input content at the token level
        input_data["input"] = encoding.decode(encoding.encode(input_data["input"])[:MAX_TOKENS])
    return input_data


# Gmail toolkit setup
def setup_gmail_toolkit():
    credentials = get_gmail_credentials(
        token_file="token.json",
        scopes=["https://mail.google.com/"],
        client_secrets_file=credentials_path,
    )
    api_resource = build_resource_service(credentials=credentials)
    toolkit = GmailToolkit(api_resource=api_resource)

    tools = toolkit.get_tools()
    logger.info("Number of tools loaded: %d", len(tools))
    for tool in tools:
        logger.info("Tool: %s", tool.name)
        # Log tool names without trying to modify unsupported attributes

    return toolkit


def process_tool_output(output: str, max_length: int = 1000) -> str:
    """
    Truncate or process tool output to fit within the token limit.
    """
    return output[:max_length] if output else output


# Create agent executor
def get_agent_executor():
    toolkit = setup_gmail_toolkit()
    instructions = "You are an email assistant. Handle email-related tasks accurately."
    base_prompt = hub.pull("langchain-ai/openai-functions-template")
    prompt = base_prompt.partial(instructions=instructions)
    llm = ChatOpenAI(model_name=model_name, temperature=0, openai_api_key=api_key)

    agent = create_openai_functions_agent(llm, toolkit.get_tools(), prompt)

    # Add debugging logs for tool outputs
    for tool in toolkit.get_tools():
        logger.info("Inspecting tool: %s", tool.name)

    return AgentExecutor(agent=agent, tools=toolkit.get_tools(), verbose=False)


def truncate_messages(messages, max_tokens=4000):
    """
    Truncate messages to ensure they fit within the token limit.
    """
    encoding = tiktoken.encoding_for_model(model_name)
    total_tokens = 0
    truncated_messages = []

    for message in reversed(messages):  # Start with the most recent messages
        message_tokens = len(encoding.encode(message.get("content", "")))
        if total_tokens + message_tokens > max_tokens:
            break
        truncated_messages.insert(0, message)
        total_tokens += message_tokens

    logger.info("Truncated messages to fit within %d tokens.", max_tokens)
    return truncated_messages


@traceable(run_type="llm", name="Email Agent Execution")
def run_email_agent(input_command):
    """
    Run the email agent with token tracking, validation, and truncation.
    """
    input_command = validate_and_truncate_input(input_command)
    agent_executor = get_agent_executor()

    with get_openai_callback() as cb:
        try:
            # Execute the agent
            result = agent_executor.invoke(input_command)

            # Dynamically process tool outputs
            if isinstance(result, dict):  # Check if result is structured
                for key, value in result.items():
                    if isinstance(value, str):
                        result[key] = process_tool_output(value)
            elif isinstance(result, str):
                result = process_tool_output(result)

            logger.info("Total tokens used: %s", cb.total_tokens)
            logger.info("Prompt tokens used: %s", cb.prompt_tokens)
            logger.info("Completion tokens used: %s", cb.completion_tokens)
            logger.info("Total cost (USD): %s", cb.total_cost)
        except ValueError as e:
            logger.error("Input validation failed: %s", str(e))
            raise
        except Exception as e:
            logger.error("Agent execution failed: %s", str(e))
            raise

    return result


def safe_run_email_agent(input_command, retries=3, backoff=1.5):
    for attempt in range(retries):
        try:
            return run_email_agent(input_command)
        except Exception as e:
            if "rate_limit_exceeded" in str(e):
                wait_time = backoff ** attempt
                logger.warning(f"Rate limit exceeded. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise e
    raise RuntimeError("Exceeded maximum retries for rate limit errors.")


def format_email_summary(response: dict) -> str:
    """
    Format the email summary into a clean, readable text format.
    """
    output = response.get("output", "")
    if not output:
        return "No emails to summarize."

    # Split the output into lines and clean up formatting
    formatted_output = []
    for line in output.splitlines():
        line = line.strip()
        if line:
            # Add indentation for categories
            if line.startswith("###"):
                formatted_output.append(f"\n{line.replace('###', '').strip()}")  # Remove '###'
            else:
                formatted_output.append(f"  {line}")

    return "\n".join(formatted_output)


if __name__ == "__main__":
    input_command = {
        "input": "Summarize the emails I received the last 2 days in great detail. Provide comprehensive insights on all messages."
    }
    logger.info("Running email agent...")
    try:
        response = safe_run_email_agent(input_command)
        logger.info("Agent Response: %s", response)

        # Format and print the summary
        clean_output = format_email_summary(response)
        print("Cleaned Email Summary:\n", clean_output)
    except Exception as e:
        logger.error("Failed to execute email agent: %s", str(e))

