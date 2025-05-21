# clihunter/config.py
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, List

# Load environment variables from .env file if it exists
# Useful for local development to store API keys etc.
dotenv_path = Path('.') / '.env'
load_dotenv(dotenv_path=dotenv_path)

# XDG Base Directory Specification
XDG_CONFIG_HOME = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
XDG_DATA_HOME = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
XDG_STATE_HOME = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local' / 'state')) # For logs if any

APP_NAME = "clihunter"
APP_CONFIG_DIR = XDG_CONFIG_HOME / APP_NAME
APP_DATA_DIR = XDG_DATA_HOME / APP_NAME
APP_STATE_DIR = XDG_STATE_HOME / APP_NAME # For future logs or cache
USER_ENV_FILE_PATH = APP_CONFIG_DIR / "clihunter.env" # 或 "user.env"


# Ensure directories exist
APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
APP_STATE_DIR.mkdir(parents=True, exist_ok=True)

user_config_loaded = False
if USER_ENV_FILE_PATH.is_file():
    # load_dotenv default override=False
    # This means if the variable is already set in the environment, it won't be overridden by the .env file.
    if load_dotenv(dotenv_path=USER_ENV_FILE_PATH):
        user_config_loaded = True
    else:
        pass
else:
    pass

# --- Database Configuration ---
DEFAULT_DB_FILENAME = "commands.db"
DATABASE_PATH = APP_DATA_DIR / DEFAULT_DB_FILENAME

# --- LLM Configuration ---
# For OpenAI, Anthropic, Google Gemini, or other cloud LLMs
LLM_API_KEY: Optional[str] = os.environ.get("CLIHUNTER_LLM_API_KEY") # e.g., sk-xxxx
LLM_API_BASE_URL: Optional[str] = os.environ.get("CLIHUNTER_LLM_API_BASE_URL") # For self-hosted or proxy
LLM_MODEL_NAME: str = os.environ.get("CLIHUNTER_LLM_MODEL_NAME", "gpt-3.5-turbo") # Default model

# For local Ollama
OLLAMA_BASE_URL: str = os.environ.get("CLIHUNTER_OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL_NAME: str = os.environ.get("CLIHUNTER_OLLAMA_LLM_MODEL_NAME", "llama3:8b-instruct-q5_K_M") # A reasonable default
OLLAMA_EMBEDDING_MODEL_NAME: str = os.environ.get("CLIHUNTER_OLLAMA_EMBEDDING_MODEL_NAME", "mxbai-embed-large") # For Ollama embeddings

# Determine which LLM provider to use (simple logic, can be expanded)
LLM_PROVIDER: str = os.environ.get("CLIHUNTER_LLM_PROVIDER", "openai").lower() # "openai", "ollama", etc.

# --- Embedding Model Configuration ---
# If not using Ollama for embeddings, specify a sentence-transformer model
SENTENCE_TRANSFORMER_MODEL: str = os.environ.get(
    "CLIHUNTER_SENTENCE_TRANSFORMER_MODEL",
    "shibing624/text2vec-base-chinese" # Example for Chinese, or use a multilingual one
    # "all-MiniLM-L6-v2" # A good multilingual default
)

# --- History Parsing Configuration ---
DEFAULT_SHELL_HISTORY_FILES = {
    "bash": Path.home() / ".bash_history",
    "zsh": Path(os.environ.get("HISTFILE", Path.home() / ".zsh_history")),
    "fish": Path.home() / ".local" / "share" / "fish" / "fish_history",
}
# Simple exclusion list (can be loaded from a user config file later)
DEFAULT_COMMAND_EXCLUSION_LIST: List[str] = [
    "ls", "cd", "pwd", "clear", "exit", "history", "man", "top", "htop", "vim", "vi", "nano", "code",  "source", "echo", "clihunter", "which", "export" 
    # Add more as needed
]
# Filter commands shorter than this length
MIN_COMMAND_LENGTH = 5

# --- FZF Configuration ---
FZF_EXECUTABLE: str = os.environ.get("CLIHUNTER_FZF_EXECUTABLE", "fzf")
FZF_DEFAULT_OPTIONS: str = (
    "--height 40% --layout=reverse --border "
    "--preview 'echo {} | cut -d \"::\" -f 3- ' " # Show full command in preview
    "--preview-window right:60%:wrap"
)


# --- Search Configuration ---
DEFAULT_TOP_K_RESULTS = 10 # Default number of results to show/process
BM25_TOP_K = 20 # Number of candidates to fetch for BM25
DENSE_TOP_K = 20 # Number of candidates to fetch for dense search
HYBRID_SEARCH_ALPHA = 0.5 # Weight for dense search in hybrid (1-alpha for sparse)

# You can add more configuration options as needed (e.g., logging level)

# Example of how to load a user-editable exclusion list (future enhancement)
# USER_EXCLUSION_LIST_PATH = APP_CONFIG_DIR / "exclusion_list.txt"
# if USER_EXCLUSION_LIST_PATH.exists():
#     with open(USER_EXCLUSION_LIST_PATH, "r") as f:
#         user_exclusions = [line.strip() for line in f if line.strip()]
#         DEFAULT_COMMAND_EXCLUSION_LIST.extend(user_exclusions)


if __name__ == "__main__":
    # For testing the config module
    print(f"App Name: {APP_NAME}")
    print(f"Config Dir: {APP_CONFIG_DIR}")
    print(f"Data Dir: {APP_DATA_DIR}")
    print(f"Database Path: {DATABASE_PATH}")
    print(f"LLM Provider: {LLM_PROVIDER}")
    if LLM_PROVIDER == "openai":
        print(f"LLM API Key (loaded): {'******' if LLM_API_KEY else 'Not set'}")
        print(f"LLM Model: {LLM_MODEL_NAME}")
    elif LLM_PROVIDER == "ollama":
        print(f"Ollama Base URL: {OLLAMA_BASE_URL}")
        print(f"Ollama LLM Model: {OLLAMA_MODEL_NAME}")
        print(f"Ollama Embedding Model: {OLLAMA_EMBEDDING_MODEL_NAME}")
    print(f"Sentence Transformer Model (fallback): {SENTENCE_TRANSFORMER_MODEL}")
    print(f"Default Exclusions: {DEFAULT_COMMAND_EXCLUSION_LIST[:5]}...")
    print(f"FZF Executable: {FZF_EXECUTABLE}")