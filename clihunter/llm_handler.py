# clihunter/llm_handler.py
import json
import requests
from typing import List, Optional, Dict, Any

from . import config
from . import models
from . import utils

# --- Prompt Templates (English preferred) ---
PROMPT_TEMPLATES = {
    "generate_description": """\
You are an assistant that explains Shell commands. Provide a concise, accurate, single-sentence description **in English** for the following Linux/macOS Shell command.
Use the provided context from `which`, `--help` output, and `man` page excerpts to inform your description, especially for aliases or less common commands. 
If the context is "N/A" or indicates an error, rely on your general knowledge.

Command: "{command_text}"

Context from 'which {base_command}':
"{which_info}"

Context from '{base_command} --help' (or similar flags): 
"{help_info}"

Context from 'man {base_command}':
"{man_info}"

Based on the command and all available context, provide the detailed and multiple explanatory English Description:
""",
    "generate_command_from_description": """\
You are an AI expert in Shell commands. Based on the following description of a command-line tool's functionality, generate a concise and common Shell command that achieves this.
Output only the command itself, without any additional explanations, markdown code blocks, or prefixes.

English Description: "{description_text}"
Command:
""",
    "enhance_query_for_sparse_search": """\
You are an AI assistant helping with command retrieval. The user's original query (already in English) is for finding a Shell command.
Analyze the user's **English query** below and enhance or rewrite it to be more effective for a keyword-based sparse retrieval system (like BM25/FTS5 using an English index).
The goal is to improve recall and precision by extracting core keywords, adding possible synonyms or relevant command names, and potentially forming a more effective search phrase.
Return only the enhanced English query string, keeping it concise and effective.

User's English Query: "{user_query}"
Enhanced English Query String:
""",
    "translate_text": """\
Translate the following text from {source_language} to {target_language}.
Return only the translated text, without any additional explanations or prefixes.

Source Text:
"{text_to_translate}"

Translated Text:
""",
    "generate_command_rag": """\
You are an intelligent Shell command generation assistant. The user wants to perform a task, and some potentially relevant command history (in English) is provided as context.
Carefully read the user's task description (assumed to be in English or translated to English) and the English reference commands.
Then, generate a Shell command (in English) that best fulfills the user's needs and is ready to be executed.
If the reference commands are not perfectly applicable, modify or combine them. If no suitable reference is available, try to generate a command independently based on the task description.
If you cannot generate a suitable command, briefly explain why. Output only the final command or the explanation.

User's Task Description (English): "{user_query}"

Potentially Relevant History Commands (English Context):
---
{retrieved_context_str}
---

Generate a Shell command to complete the user's task (or briefly explain if unable):
"""
}

def _call_llm_api(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 200,
    is_json_output: bool = False
) -> Optional[Any]:
    provider = config.LLM_PROVIDER.lower()
    response_text: Optional[str] = None
    # print(f"DEBUG: Calling LLM. Provider: {provider}, JSON output: {is_json_output}, Prompt: {prompt[:150]}...")
    try:
        if provider == "ollama":
            api_url = f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
            payload = {
                "model": config.OLLAMA_MODEL_NAME, "prompt": prompt, "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens}
            }
            if system_prompt: payload["system"] = system_prompt
            if is_json_output: payload["format"] = "json"
            response = requests.post(api_url, json=payload, timeout=60)
            response.raise_for_status()
            response_data = response.json()
            response_text = response_data.get("response", "").strip()

        elif provider == "openai":
            api_base = (config.LLM_API_BASE_URL or "https://api.openai.com/v1").rstrip('/')
            api_url = f"{api_base}/chat/completions"
            is_official_openai = "api.openai.com" in api_base
            headers = {"Content-Type": "application/json"}
            if config.LLM_API_KEY and config.LLM_API_KEY.lower() not in ["none", "na", "no_key", ""]:
                headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"
            elif is_official_openai:
                print("Error: OpenAI API key (CLIHUNTER_LLM_API_KEY) is not set or invalid.")
                return None
            messages = []
            if system_prompt: messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload = {
                "model": config.LLM_MODEL_NAME, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens,
            }
            if is_json_output: payload["response_format"] = {"type": "json_object"}
            response = requests.post(api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            response_data = response.json()
            choices = response_data.get("choices")
            if choices and isinstance(choices, list) and len(choices) > 0:
                message = choices[0].get("message")
                if message and isinstance(message, dict): response_text = message.get("content", "").strip()
                else: print(f"Warning: Unexpected 'message' structure in LLM response: {message}")
            else: print(f"Warning: Unexpected or empty 'choices' structure in LLM response: {choices}")
        else:
            print(f"Error: Unsupported LLM provider '{provider}'.")
            return None

        if response_text is None:
             print(f"Warning: LLM ({provider}) returned no valid content.")
             return None

        if is_json_output:
            try:
                if provider == "ollama" and response_text.startswith("```json"):
                    cleaned_json_text = response_text.split("```json\n", 1)[-1].rsplit("\n```", 1)[0]
                    return json.loads(cleaned_json_text)
                return json.loads(response_text)
            except json.JSONDecodeError as e:
                print(f"LLM API error: Expected JSON but parsing failed. Error: {e}\nRaw text: {response_text}")
                return None
        return response_text
    except requests.exceptions.Timeout:
        print(f"LLM API request timeout ({provider}).")
        return None
    except requests.exceptions.RequestException as e:
        print(f"LLM API request error ({provider}): {e}")
        if hasattr(e, 'response') and e.response is not None:
            try: print(f"LLM API error details: {e.response.json()}")
            except json.JSONDecodeError: print(f"LLM API error content (non-JSON): {e.response.text}")
        return None
    except Exception as e:
        print(f"Unknown error occurred while processing LLM response ({provider}): {e}")
        return None


def generate_description(
    command_text: str, 
    base_command_for_context: str = "command", 
    command_context: Optional[Dict[str, Optional[str]]] = None
) -> Optional[str]:
    """
    Use LLM to generate an **English** description for the given Shell command.
    Can accept additional command context (which, help, man) to assist generation.
    command_text: The command text to describe (e.g., ls -la).
    base_command_for_context: The base command to use for context (e.g., "ls").
    command_context: The additional context (which, help, man)
    """
    if not command_text.strip(): 
        return None
    
    context_data = command_context or {} 

    prompt = PROMPT_TEMPLATES["generate_description"].format(
        command_text=command_text,
        base_command=base_command_for_context, 
        which_info=context_data.get("which_info", "N/A"),
        help_info=context_data.get("help_info", "N/A"),
        man_info=context_data.get("man_info", "N/A")
    )
    description = _call_llm_api(prompt, max_tokens=1024, temperature=0.1) 
    return description

def generate_command_from_description(description_text: str) -> Optional[str]:
    """Use LLM to generate a Shell command based on an **English** command description."""
    if not description_text.strip(): return None
    prompt = PROMPT_TEMPLATES["generate_command_from_description"].format(description_text=description_text)
    command = _call_llm_api(prompt, max_tokens=100, temperature=0.3)
    if command: 
        command = command.strip()
        if command.startswith("`") and command.endswith("`"): command = command[1:-1]
        if command.startswith("```") and command.endswith("```"):
            lines = command.splitlines()
            if len(lines) > 1 and lines[0].lower().startswith("```"): lines = lines[1:]
            if len(lines) > 0 and lines[-1] == "```": lines = lines[:-1]
            command = "\n".join(cmd_line.strip() for cmd_line in lines).strip()
    return command if command and command.strip() else None

def enhance_query_for_sparse_search(english_user_query: str) -> Optional[str]:
    """Use LLM to enhance an **English** user query to optimize sparse retrieval."""
    if not english_user_query.strip(): return english_user_query
    prompt = PROMPT_TEMPLATES["enhance_query_for_sparse_search"].format(user_query=english_user_query)
    enhanced_query = _call_llm_api(prompt, max_tokens=100, temperature=0.3, is_json_output=False)
    return enhanced_query if enhanced_query and enhanced_query.strip() else english_user_query


def translate_text(
    text_to_translate: str,
    target_language: str, 
    source_language: Optional[str] = "auto"
) -> Optional[str]:
    """Use LLM to translate text from source language to target language."""
    if not text_to_translate.strip(): return ""
    source_lang_display = source_language
    if source_language == "auto": 
        if target_language.lower().startswith("en"): source_lang_display = "source language (e.g., Chinese)"
        elif target_language.lower().startswith("zh") or "chinese" in target_language.lower() or "中文" in target_language:
             source_lang_display = "source language (e.g., English)"
    prompt = PROMPT_TEMPLATES["translate_text"].format(
        text_to_translate=text_to_translate,
        source_language=source_lang_display,
        target_language=target_language
    )
    max_trans_tokens = max(100, int(len(text_to_translate) * 2.5) + 50)
    return _call_llm_api(prompt, max_tokens=max_trans_tokens, temperature=0.05)

def generate_command_via_rag(english_user_query: str, retrieved_entries: List[models.CommandEntry]) -> Optional[str]:
    """
    Use RAG approach to generate a new command based on **English** user query
    and retrieved **English** context commands.
    """
    if not english_user_query.strip(): return None
    context_parts = []
    for i, entry in enumerate(retrieved_entries[:3]): 
        context_parts.append(
            f"Reference Command {i+1}:\n"
            f"  Original Command: `{entry.raw_command}`\n" 
            f"  Description (English): {entry.description or 'N/A'}\n"
            f"  LLM-Generated Command from Description (English): `{entry.processed_command or 'N/A'}`\n"
        )
    retrieved_context_str = "\n".join(context_parts) if context_parts else "No relevant history commands found for reference."
    prompt = PROMPT_TEMPLATES["generate_command_rag"].format(
        user_query=english_user_query, retrieved_context_str=retrieved_context_str
    )
    return _call_llm_api(prompt, max_tokens=250, temperature=0.4)


# --- Test code when run as main module (English preferred) ---
if __name__ == "__main__":
    from . import utils 

    print("--- Testing LLM Handler (with command context) ---")

    test_raw_command_1 = "ls -lha" # A common command
    test_raw_command_2 = "clihunter search --help" # Assuming clihunter is installed and has help info
    test_raw_command_3 = "my_very_custom_script --verbose" # A custom script/alias (must exist in system to get context)

    for cmd_text_to_test in [test_raw_command_1, test_raw_command_2, test_raw_command_3]:
        print(f"\n--- Testing command: '{cmd_text_to_test}' ---")
        
        base_cmd = utils.get_base_command(cmd_text_to_test)
        print(f"  Extracted base command: {base_cmd}")

        context = None
        if base_cmd: 
            print(f"  Getting context info for '{base_cmd}'...")
            context = utils.get_command_context(cmd_text_to_test) 
            print(f"    'which' info: {(context.get('which_info') or 'N/A')[:70]}...")
            print(f"    'help' info: {(context.get('help_info') or 'N/A')[:70]}...")
            print(f"    'man' info: {(context.get('man_info') or 'N/A')[:70]}...")
        else:
            print("  Cannot extract base command, skipping context retrieval.")


        print(f"  1. Testing English description generation for: '{cmd_text_to_test}'")
        english_description = generate_description(
            cmd_text_to_test, 
            base_command_for_context=base_cmd or cmd_text_to_test, 
            command_context=context
        )
        
        if english_description:
            print(f"     LLM generated English description: {english_description}")

            print(f"  2. Testing command generation from English description for: '{english_description[:60]}...'")
            generated_cmd_from_desc = generate_command_from_description(english_description)
            if generated_cmd_from_desc:
                print(f"     LLM generated command from English description: `{generated_cmd_from_desc}`")
            else:
                print("     Failed to generate command from English description.")
        else:
            print("     Failed to generate English description.")

    print("\n--- LLM Handler testing completed ---")
