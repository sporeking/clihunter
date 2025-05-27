# CliHunter 🏹

**Find the shell commands you need, right when you need them.**

CliHunter is a command-line utility designed to help you quickly find shell commands by describing what you want to do in natural language. It leverages a local FTS5-powered search combined with LLM-enhanced history processing and a powerful `fzf`-driven live search interface for your terminal.

Stop memorizing obscure command flags or endlessly Googling – let CliHunter be your guide!

## ✨ Key Features

* **Natural Language Search:** Describe the task (e.g., "dotfiles add" -> "chezmoi add xxx") and CliHunter will try to find matching commands.
* **Interactive Live Search:** A widget powered by `fzf` allows you to type and see search results update in real-time, directly in your command line. 
* **Personal Command Database:** Add your own frequently used or hard-to-remember commands along with descriptions and tags.

## 🛠️ Installation

**Prerequisites:**
* Python 3.8+
* `pip`
* `fzf` (for live search functionality)
* Zsh (for live search ZLE widget integration)

   ```bash
   git clone https://github.com/sporeking/clihunter.git
   cd clihunter
   pip install -e .
   ```


## ⚙️ Configuration
**1. LLM API Keys (If applicable):**
If your llm_handler.py uses external LLM APIs (e.g., OpenAI, Google Gemini, Anthropic), you'll typically need to set environment variables for API keys. For example:

```Bash
export OPENAI_API_KEY="your_openai_api_key_here"
# Add this to your shell configuration file (e.g., ~/.zshrc or ~/.bashrc)
```
Refer to llm_handler.py or its documentation for specific environment variables required.

**2. CliHunter Configuration:**
CliHunter might use a configuration file (e.g., ~/.config/clihunter/config.ini or environment variables) for settings like DEFAULT_TOP_K_RESULTS, BM25_TOP_K, paths, etc. Please specify if this is the case.
(Currently, based on the Python snippet, config.DEFAULT_TOP_K_RESULTS and config.BM25_TOP_K are imported, suggesting a config.py or similar module).
After you configure the API of LLM, you can run:  
```
clihunter initdb
clihunter init-history
```
*For cheap init-history, you can use free models (e.g. THUDM/GLM-4-9B-0414) on [SiliconFlow](https://cloud.siliconflow.cn/).*


**3. Zsh Integration (for Live Search):**

An example config in your ~/.zshrc:
```
clihunter_live_fzf_search() {
  local initial_query="${LBUFFER}" 
  local selected_line
  local query_for_fzf_reload
  
  local reload_cmd="clihunter search --live-search-query {q} 2>/dev/null || echo 'ERROR: clihunter failed or no results'"

  selected_line=$( \
    FZF_DEFAULT_COMMAND="clihunter search --live-search-query {q} 2>/dev/null || echo 'ERROR: clihunter failed or no results'" \
    fzf --ansi --disabled --phony \
        --prompt="Clihunter Live > " \
        --header="Type to search commands dynamically. Ctrl-C to cancel." \
        --height="50%" --layout=reverse --border \
        --delimiter=$'\x1F' \
        --preview-window="right:50%:wrap" \
        --with-nth='{1}' \
        --query="$initial_query" \
        --bind="start:reload(clihunter search --live-search-query {q} 2>/dev/null || echo 'ERROR: clihunter failed or no results')" \
        --bind="change:reload(clihunter search --live-search-query {q} 2>/dev/null || echo 'ERROR: clihunter failed or no results')" \
        --bind="enter:accept" \
        --preview='printf "DESC: %s\nPROC: %s\nTAGS: %s\n" "{2}" "{3}" "{4}"' \
  )

  if [ -n "$selected_line" ]; then
    local selected_command=$(echo "$selected_line" | awk -F $'\x1F' '{print $1}' | tr -d '\n')
    if [ -n "$selected_command" ]; then
      LBUFFER="$selected_command" 
      RBUFFER=""          
      zle redisplay
    else
      zle send-break 
    fi
  else
    zle send-break 
  fi
}

zle -N clihunter_live_fzf_search

bindkey '^H' clihunter_live_fzf_search
```
Then source your ~/.zshrc or open a new terminal.

## 🚀 Usage

Live search: press Ctrl+H (in our example).

## TODO

- Make a better search. We need a search algo fast and intelligent. (Sparse search is not good enough for searching forgotten commands. )
- Make more useful for users. For example, users can keep their own commands' repo that is important and more customizable.
- Make a more easy way for enhancing history. Now, we simply use llm to summarize and rewrite the history to enhance. But it's too slow and expensive that many useless or similiar commands are also enhanced.
