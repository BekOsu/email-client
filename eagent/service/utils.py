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


def validate_and_truncate_input(input_data: dict, model: str = "gpt-3.5-turbo") -> dict:
    """
    Validate and truncate input to ensure it stays within the token limit.
    """
    token_count = calculate_token_count(input_data, model)
    if token_count > MAX_TOKENS:
        logger.warning(
            f"Input exceeds token limit ({token_count} tokens). Truncating input to fit within {MAX_TOKENS} tokens."
        )
        # Simplify or truncate the input as needed
        input_data["input"] = input_data["input"][:MAX_TOKENS]  # Example truncation
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
    return toolkit


# Create agent executor
def get_agent_executor():
    toolkit = setup_gmail_toolkit()
    instructions = "You are an email assistant. Handle email-related tasks accurately."
    base_prompt = hub.pull("langchain-ai/openai-functions-template")
    prompt = base_prompt.partial(instructions=instructions)
    llm = ChatOpenAI(model_name=model_name, temperature=0, openai_api_key=api_key)
    agent = create_openai_functions_agent(llm, toolkit.get_tools(), prompt)
    return AgentExecutor(agent=agent, tools=toolkit.get_tools(), verbose=False)


@traceable(run_type="llm", name="Email Agent Execution")
def run_email_agent(input_command):
    """
    Run the email agent with token tracking and validation.
    """
    # Validate and truncate input to prevent long tokens
    input_command = validate_and_truncate_input(input_command)

    agent_executor = get_agent_executor()
    with get_openai_callback() as cb:
        result = agent_executor.invoke(input_command)
        logger.info("Total tokens used: %s", cb.total_tokens)
        logger.info("Prompt tokens used: %s", cb.prompt_tokens)
        logger.info("Completion tokens used: %s", cb.completion_tokens)
        logger.info("Total cost (USD): %s", cb.total_cost)

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


if __name__ == "__main__":
    input_command = {"input": "Summarize the emails I received the last 20 days in great detail. Provide comprehensive insights on all messages."}
    logger.info("Running email agent...")
    try:
        response = safe_run_email_agent(input_command)
        logger.info("Agent Response: %s", response)
        print("Agent Response:", response)
    except Exception as e:
        logger.error("Failed to execute email agent: %s", str(e))
