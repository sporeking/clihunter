# clihunter/cli.py
import typer
import subprocess
import sys
import time
from typing import List, Optional, Dict, Any
from typing_extensions import Annotated

# Import other modules from the project
from . import config
from . import database
from . import models
from . import history_parser
from . import llm_handler
from . import utils
# from .search import sparse_search 
# from .search import dense_search 
# from .search import hybrid_search 

# app definition and _display_results_with_fzf function remain unchanged...
app = typer.Typer(
    name="clihunter",
    help="""🚀 **CLIHunter: Your Smart CLI Assistant!** 🚀

    Save, search and generate command line instructions you forgot.
    All core descriptions and processed commands are stored in English for optimal retrieval.
    """,
    no_args_is_help=True,
    rich_markup_mode="markdown"
)

# --- Helper function _display_results_with_fzf (remains unchanged) ---
def _display_results_with_fzf(results: List[models.CommandEntry]) -> Optional[models.CommandEntry]:
    if not results:
        typer.secho("🤷 No matching commands found.", fg=typer.colors.YELLOW)
        return None
    fzf_input_lines = []
    for entry in results:
        tags_str = ", ".join(entry.tags) if entry.tags else "No tags"
        # description and processed_command are now in English
        display_description = entry.description or "No English description"
        display_processed_command = entry.processed_command or entry.raw_command

        line = (
            f"{entry.id} ::: "
            f"{display_description} ::: "
            f"`{entry.raw_command}` (Processed: `{display_processed_command}`) ::: " 
            f"[{tags_str}]"
        )
        fzf_input_lines.append(line)
    
    fzf_input_str = "\n".join(fzf_input_lines)

    try:
        fzf_options_str = config.FZF_DEFAULT_OPTIONS + (
            " --print-query --expect=ctrl-c,ctrl-x "
            " --header 'Press Enter to select, Ctrl-C/Ctrl-X to cancel, Ctrl-P to toggle preview'"
            " --prompt 'Select command > ' "
            " --delimiter=' ::: ' --with-nth='2..'"
        )
        fzf_cmd_list = [config.FZF_EXECUTABLE] + [opt for opt in fzf_options_str.split(' ') if opt]

        process = subprocess.run(
            fzf_cmd_list,
            input=fzf_input_str,
            text=True,
            capture_output=True,
            check=False
        )

        if process.returncode == 0:
            selected_lines = process.stdout.strip().splitlines()
            if not selected_lines:
                 typer.echo("🤔 fzf did not return a selection.")
                 return None
            selected_line_content = selected_lines[-1]
            
            # (This is a workaround - better would be configuring fzf to return needed info in one call)
            fzf_get_id_options = (
                config.FZF_DEFAULT_OPTIONS.split() + 
                ["--print-query", "--select-1", "--height", "10%", "--prompt", "Confirm selection (Enter) >"] + 
                ["--delimiter= ::: ", "--nth", "1"] 
            )
            process_for_id = subprocess.run(
                [config.FZF_EXECUTABLE] + fzf_get_id_options,
                input=fzf_input_str, 
                text=True, capture_output=True, check=False
            )
            if process_for_id.returncode == 0 and process_for_id.stdout.strip():
                selected_id = process_for_id.stdout.strip().splitlines()[-1] 
                for entry in results:
                    if entry.id == selected_id:
                        return entry
            else: 
                typer.echo("🤔 Selection confirmation failed or canceled.")
                return None

        elif process.returncode == 1: typer.echo("🤔 No command selected.")
        elif process.returncode == 130: typer.echo("Operation canceled by user (Ctrl-C).")
        # fzf 1.43+ uses exit code 3 for Ctrl-X
        elif process.returncode == 3 and "--expect=ctrl-x" in fzf_options_str: typer.echo("Operation canceled by user (Ctrl-X).")
        else: typer.secho(f"fzf execution error (exit code {process.returncode}):\n{process.stderr}", fg=typer.colors.RED)
        return None
    except FileNotFoundError:
        typer.secho(f"Error: fzf executable not found at '{config.FZF_EXECUTABLE}'.", fg=typer.colors.RED)
        typer.echo("You can install fzf from https://github.com/junegunn/fzf")
        return None
    except Exception as e:
        typer.secho(f"Unknown error while interacting with fzf: {e}", fg=typer.colors.RED)
        return None

# --- CLI command ---
@app.command(name="initdb", help="Initialize database and table structure (if they don't exist).")
def init_db_command():
    try:
        typer.echo(f"Checking and initializing database at: {config.DATABASE_PATH} ...")
        database.create_tables() # Call function from database.py
        typer.secho("✅ Database initialized successfully!", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"❌ Database initialization failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command(name="init-history", help="Initialize command database from shell history (English preferred).")
def init_history_command(
    shell: Annotated[str, typer.Option(help="Specify shell type (e.g. 'bash', 'zsh', 'fish').")] = "zsh",
    limit: Annotated[Optional[int], typer.Option(help="Maximum number of history entries to process (starting from most recent).")] = None,
    force_reparse_all: Annotated[bool, typer.Option("--force-reparse", help="Force reparse all matching commands and update existing entries in database.")] = False,
    batch_size: Annotated[int, typer.Option(help="Batch size for LLM processing (currently processed one by one, this parameter unused).")] = 10, # Currently processed one by one
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Skip confirmation prompts.")] = False
):
    typer.echo(f"🚀 Starting database initialization from {shell} history...")
    typer.echo(f"Config -> Reading recent {limit or 'all'} entries, force reparse/update: {force_reparse_all}")

    raw_history_entries: List[history_parser.HistoryEntry] = history_parser.load_history(shell_type=shell, num_entries=limit)
    if not raw_history_entries:
        typer.secho("🤷 Failed to load any commands from history.", fg=typer.colors.YELLOW)
        return

    typer.echo(f"Raw history entries: {len(raw_history_entries)}")
    unique_history_commands_map: Dict[str, history_parser.HistoryEntry] = {}
    for entry in reversed(raw_history_entries):
        raw_cmd_text = entry.get("command", "").strip()
        if raw_cmd_text:
            if raw_cmd_text not in unique_history_commands_map or \
               (entry.get("timestamp") and (unique_history_commands_map[raw_cmd_text].get("timestamp") is None or \
                entry.get("timestamp", 0) > unique_history_commands_map[raw_cmd_text].get("timestamp", 0))):
                unique_history_commands_map[raw_cmd_text] = entry
    
    candidate_commands_from_history: List[history_parser.HistoryEntry] = list(unique_history_commands_map.values())
    typer.echo(f"Unique commands after deduplication: {len(candidate_commands_from_history)}")

    filtered_history_commands: List[history_parser.HistoryEntry] = []
    for entry in candidate_commands_from_history:
        cmd_text = entry.get("command", "")
        base_command = utils.get_base_command(cmd_text)
        if cmd_text and \
           len(cmd_text) >= config.MIN_COMMAND_LENGTH and \
           base_command not in config.DEFAULT_COMMAND_EXCLUSION_LIST and \
               "help" not in cmd_text:
            filtered_history_commands.append(entry)
    
    typer.echo(f"After excluding simple/short commands: {len(filtered_history_commands)}")
    if not filtered_history_commands:
        typer.secho("🤷 No eligible commands to process.", fg=typer.colors.YELLOW)
        return

    commands_to_process_final: List[Dict[str, Any]] = []
    db_raw_commands_set = set()
    if not force_reparse_all:
        db_raw_commands_set = set(database.get_all_raw_commands())
        typer.echo(f"Database already contains {len(db_raw_commands_set)} raw commands.")

    for hist_entry in filtered_history_commands:
        raw_cmd = hist_entry.get("command", "")
        timestamp = hist_entry.get("timestamp")
        if force_reparse_all:
            existing_db_entry = database.get_command_by_raw_command(raw_cmd)
            op_type = "UPDATE" if existing_db_entry else "ADD"
            existing_id = existing_db_entry.id if existing_db_entry else None
            commands_to_process_final.append({"raw_command": raw_cmd, "timestamp": timestamp, "operation": op_type, "existing_id": existing_id})
        elif raw_cmd not in db_raw_commands_set:
            commands_to_process_final.append({"raw_command": raw_cmd, "timestamp": timestamp, "operation": "ADD", "existing_id": None})
    
    num_to_add = sum(1 for cmd in commands_to_process_final if cmd['operation'] == 'ADD')
    num_to_update = sum(1 for cmd in commands_to_process_final if cmd['operation'] == 'UPDATE')

    if not commands_to_process_final:
        typer.secho("🤷 No new commands or commands requiring forced update to process.", fg=typer.colors.YELLOW)
        return

    typer.echo(f"Ready to process commands -> New: {num_to_add}, Update: {num_to_update}")
    if not yes and not typer.confirm(f"About to process {len(commands_to_process_final)} commands with LLM (New:{num_to_add}, Update:{num_to_update}). Continue?"):
        typer.echo("Operation cancelled.")
        raise typer.Exit()

    processed_count = 0; llm_errors = 0; db_success_add = 0; db_success_update = 0
    with typer.progressbar(commands_to_process_final, label="Processing commands...", length=len(commands_to_process_final)) as progress:
        for cmd_info in progress:
            raw_cmd = cmd_info["raw_command"]

            base_cmd_for_context = utils.get_base_command(raw_cmd)
            command_context_data = {"which_info": "N/A", "help_info": "N/A", "man_info": "N/A"}
            if base_cmd_for_context:
                command_context_data = utils.get_command_context(raw_cmd) 

            english_description = llm_handler.generate_description(
                raw_cmd,
                base_command_for_context=(base_cmd_for_context or raw_cmd),
                command_context=command_context_data
            )
            if not english_description:
                typer.secho(f"  Can't generate English description for '{raw_cmd[:30]}...', skipping.", fg=typer.colors.YELLOW)
                llm_errors += 1
                continue

            english_processed_command = llm_handler.generate_command_from_description(english_description)
            # Default None if not generated
            if not english_processed_command:
                 typer.secho(f"  Failed to generate English command from description for '{raw_cmd[:30]}...', processed_command will be empty.", fg=typer.colors.YELLOW)


            entry_data = {
                "id": cmd_info["existing_id"] or str(models.uuid.uuid4()), 
                "raw_command": raw_cmd,
                "processed_command": english_processed_command, 
                "description": english_description, 
                "tags": [], 
                "source": f"{shell}_history",
                "history_timestamp": cmd_info["timestamp"],
                "added_timestamp": int(time.time()), #
                "which_info": command_context_data["which_info"],
                "help_info": command_context_data["help_info"], 
                "man_info": command_context_data["man_info"]
            }
            command_to_store = models.CommandEntry(**entry_data)

            if cmd_info["operation"] == "ADD":
                added_id = database.add_command(command_to_store)
                if added_id: db_success_add += 1
                else: typer.secho(f"  Failed to store in database (ADD): {raw_cmd[:30]}...", fg=typer.colors.RED)
            elif cmd_info["operation"] == "UPDATE":
                success = database.update_command(command_to_store.id, command_to_store)
                if success: db_success_update += 1
                else: typer.secho(f"  Failed to update database (UPDATE): {raw_cmd[:30]}...", fg=typer.colors.RED)
            
            processed_count +=1

    typer.echo("\n--- Initialization/Update Summary ---")
    typer.secho(f"Total commands analyzed: {len(filtered_history_commands)}", fg=typer.colors.BLUE)
    typer.secho(f"Planned to process (add or update): {len(commands_to_process_final)}", fg=typer.colors.BLUE)
    typer.secho(f"Actually processed by LLM and attempted to store: {processed_count}", fg=typer.colors.BLUE)
    if llm_errors > 0: typer.secho(f"LLM processing failed (e.g. couldn't generate description): {llm_errors}", fg=typer.colors.YELLOW)
    typer.secho(f"Successfully added to database: {db_success_add}", fg=typer.colors.GREEN)
    typer.secho(f"Successfully updated in database: {db_success_update}", fg=typer.colors.GREEN)
    # Other failures = total attempts - added - updated - LLM errors (may include database errors)
    other_failures = processed_count - db_success_add - db_success_update
    if other_failures > 0:
         typer.secho(f"Failed for other reasons (e.g. database errors or empty LLM response): {other_failures}", fg=typer.colors.YELLOW)


@app.command(name="sync", help="Sync recent shell history to database (English preferred).")
def sync_command(
    shell: Annotated[str, typer.Option(help="Specify shell type (e.g. 'bash', 'zsh', 'fish').")] = "zsh",
    recent_n: Annotated[int, typer.Option(help="Only check and process the most recent N history entries.")] = 200,
    # batch_size: Annotated[int, typer.Option(help="Batch size for LLM processing.")] = 5 # Currently processed one by one
):
    typer.echo(f"🔄 Syncing last {recent_n} entries from {shell} history (English preferred)...")
    
    # The core logic of sync command is very similar to init-history, but excludes force_reparse_all option,
    # and only processes new commands. Could refactor the core processing loop from init-history into a helper function.
    # For demonstration purposes, we'll copy and simplify the logic here.

    raw_history_entries: List[history_parser.HistoryEntry] = history_parser.load_history(shell_type=shell, num_entries=recent_n)
    if not raw_history_entries:
        typer.secho("🤷 Failed to load any commands from history.", fg=typer.colors.YELLOW)
        return

    unique_history_commands_map: Dict[str, history_parser.HistoryEntry] = {}
    for entry in reversed(raw_history_entries): # Keep the newest timestamp
        raw_cmd_text = entry.get("command", "").strip()
        if raw_cmd_text:
             if raw_cmd_text not in unique_history_commands_map or \
               (entry.get("timestamp") and (unique_history_commands_map[raw_cmd_text].get("timestamp") is None or \
                entry.get("timestamp", 0) > unique_history_commands_map[raw_cmd_text].get("timestamp", 0))):
                unique_history_commands_map[raw_cmd_text] = entry
    
    candidate_commands_from_history = list(unique_history_commands_map.values())
    filtered_history_commands: List[history_parser.HistoryEntry] = []
    for entry in candidate_commands_from_history:
        cmd_text = entry.get("command", "")
        first_word = cmd_text.split(" ")[0] if cmd_text else ""
        if cmd_text and \
           len(cmd_text) >= config.MIN_COMMAND_LENGTH and \
           cmd_text not in config.DEFAULT_COMMAND_EXCLUSION_LIST and \
           first_word not in config.DEFAULT_COMMAND_EXCLUSION_LIST:
            filtered_history_commands.append(entry)

    if not filtered_history_commands:
        typer.secho("🤷 No eligible commands in recent history to sync.", fg=typer.colors.YELLOW)
        return
        
    db_raw_commands_set = set(database.get_all_raw_commands())
    commands_to_add: List[history_parser.HistoryEntry] = []
    for hist_entry in filtered_history_commands:
        if hist_entry.get("command", "") not in db_raw_commands_set:
            commands_to_add.append(hist_entry)

    if not commands_to_add:
        typer.secho("No new eligible commands to sync.", fg=typer.colors.BLUE)
        return

    typer.echo(f"Found {len(commands_to_add)} new commands to process and sync.")

    processed_count = 0; llm_errors = 0; db_success_add = 0
    with typer.progressbar(commands_to_add, label="Syncing commands", length=len(commands_to_add)) as progress:
        for hist_entry in progress:
            raw_cmd = hist_entry.get("command", "")
            typer.echo(f"\nSyncing: {raw_cmd[:70]}...")

            english_description = llm_handler.generate_description(raw_cmd)
            if not english_description:
                typer.secho(f"  Failed to generate English description for '{raw_cmd[:30]}...', skipping.", fg=typer.colors.YELLOW)
                llm_errors += 1
                continue
            english_processed_command = llm_handler.generate_command_from_description(english_description)

            entry_data = {
                "raw_command": raw_cmd,
                "processed_command": english_processed_command,
                "description": english_description,
                "tags": [],
                "source": f"{shell}_history_sync",
                "history_timestamp": hist_entry.get("timestamp"),
            }
            command_to_store = models.CommandEntry(**entry_data)
            added_id = database.add_command(command_to_store)
            if added_id: db_success_add += 1
            else: typer.secho(f"  Failed to sync command to database: {raw_cmd[:30]}...", fg=typer.colors.RED)
            processed_count += 1
            # time.sleep(0.05)

    typer.echo("\n--- Sync Summary ---")
    typer.secho(f"Attempted to process new commands: {len(commands_to_add)}", fg=typer.colors.BLUE)
    if llm_errors > 0: typer.secho(f"LLM processing failed: {llm_errors}", fg=typer.colors.YELLOW)
    typer.secho(f"Successfully synced to database: {db_success_add}", fg=typer.colors.GREEN)


@app.command(name="search", help="Search commands by natural language description (English preferred).")
def search_command(
    query: Annotated[Optional[str], typer.Argument(help="Your natural language query (can be in Chinese, will be translated to English for search). If using --live-search mode, this initial query can be empty.")] = None,
    top_k: Annotated[int, typer.Option("-k", help="Return at most K results.")] = config.DEFAULT_TOP_K_RESULTS,
    translate_query: Annotated[bool, typer.Option("--translate/--no-translate", help="Whether to automatically translate non-English queries to English.")] = True,
    enhance_query: Annotated[bool, typer.Option("--enhance/--no-enhance", help="Whether to use LLM to enhance (translated) English queries.")] = True,
    raw_output: Annotated[bool, typer.Option("--raw-output", help="[Non-live mode] Only output selected raw command string to stdout.")] = False,
    live_search_query: Annotated[Optional[str], typer.Option("--live-search-query", help="[Internal use] Query provided by fzf's reload binding for dynamic results. Implies skipping LLM processing and internal fzf calls.")] = None
):
    # --- Mode 1: Live Search (fzf reload) ---
    if live_search_query is not None:
        current_fzf_query = live_search_query
        
        query_terms = current_fzf_query.split()
        if query_terms and len(query_terms[-1]) >= 1: 
            query_terms[-1] = query_terms[-1] + "*"
            current_fzf_query = " ".join(query_terms)
            # For simplicity, users can type `*` in fzf input if they want wildcards

        fts_results = database.search_commands_fts(current_fzf_query, top_k=config.BM25_TOP_K) 
        
        db_results: List[models.CommandEntry] = []
        for cmd_id, _ in fts_results:
            entry = database.get_command_by_id(cmd_id)
            if entry:
                db_results.append(entry)
        
        # Here output is accepted by fzf (printing to stdout)
        for entry in db_results:
            tags_str = ", ".join(entry.tags) if entry.tags else ""
            # Here, the "`" character will run directly, so we must replace it with "\\`"
            safe_output = f"{entry.raw_command}\x1F{entry.description or ''}\x1F{entry.processed_command or entry.raw_command}\x1F[{tags_str}]".replace('`', '\\`')
            print(safe_output.replace("\n", "\\n")) # fzf may handle newlines, so we escape them with \n
        raise typer.Exit(0) 

    # --- Mode 2: Formal search --- ()
    # TODO: Not implemented yet, something is not useful (e.g. translate, llm enhanced query -- because it's slow)
    if query is None: 
        typer.secho("Error: Query parameter is required in non-live-search mode.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # (The logic here is essentially the same as the previous version of search_command)
    if not raw_output:
        typer.echo(f"🔍 Searching: \"{query}\" (Top-K: {top_k}, Translate: {translate_query}, Enhance: {enhance_query})")

    english_query_for_search = query
    if translate_query:
        # ... (Translation logic, same as previous version)
        if not raw_output: typer.echo("🔄 Attempting to translate query to English...")
        translated = llm_handler.translate_text(query, target_language="English")
        if translated and translated.lower() != query.lower():
            english_query_for_search = translated
            if not raw_output: typer.echo(f"   Translated English query: \"{english_query_for_search}\"")
        elif translated:
            if not raw_output: typer.echo("   Query appears to already be in English or translation made no significant changes.")
            # english_query_for_search = query 
        else:
            if not raw_output: typer.secho("   ⚠️ Query translation failed, will use original query.", fg=typer.colors.YELLOW)
            # english_query_for_search = query 

    if enhance_query:
        # ... (Enhancement logic, same as previous version)
        if not raw_output: typer.echo(f"🧠 Attempting to enhance English query: \"{english_query_for_search}\"...")
        enhanced = llm_handler.enhance_query_for_sparse_search(english_query_for_search)
        if enhanced and enhanced != english_query_for_search:
            english_query_for_search = enhanced
            if not raw_output: typer.echo(f"   Enhanced English query: \"{english_query_for_search}\"")
        else:
            if not raw_output: typer.secho("   ℹ️ LLM did not significantly enhance the query or enhancement failed.", fg=typer.colors.YELLOW)
    
    if not raw_output: typer.echo(f"⚡️ Executing sparse search (FTS5) with query: \"{english_query_for_search}\"")
    fts_results_with_scores = database.search_commands_fts(english_query_for_search, top_k=top_k)

    if not fts_results_with_scores:
        if not raw_output: typer.secho("🤷 (FTS5) No commands matching your query were found.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    results: List[models.CommandEntry] = []
    for cmd_id, score in fts_results_with_scores:
        entry = database.get_command_by_id(cmd_id)
        if entry:
            results.append(entry)
    
    if not results:
        if not raw_output: typer.secho("🤷 FTS found matches but couldn't retrieve command details.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not raw_output: typer.echo(f"✅ (FTS5) Found {len(results)} potentially relevant commands, displaying via fzf...")
    
    selected_entry = _display_results_with_fzf(results) 

    if selected_entry:
        if raw_output:
            print(selected_entry.raw_command)
            raise typer.Exit(0)
        else:
            # ... (Detailed print logic, same as previous version)
            typer.secho("\n✨ You selected:", bold=True)
            typer.echo(f"   ID                : {selected_entry.id}")
            typer.echo(f"   Raw command       : `{selected_entry.raw_command}`", fg=typer.colors.CYAN, bold=True)
            typer.echo(f"   English description: {selected_entry.description or 'N/A'}")
            typer.echo(f"   LLM-generated (EN) command: `{selected_entry.processed_command or 'N/A'}`")
            if selected_entry.tags:
                typer.echo(f"   Tags               : {', '.join(selected_entry.tags)}")
            try:
                import pyperclip
                pyperclip.copy(selected_entry.raw_command)
                typer.secho("\n📋 Command copied to clipboard!", fg=typer.colors.GREEN)
            except Exception:
                 typer.secho("\n⚠️ Failed to copy to clipboard.", fg=typer.colors.YELLOW)


    elif raw_output: 
        raise typer.Exit(code=1)

# ... (initdb, init-history, sync, add等命令，以及callback和if __name__块保持不变) ...

    # ... (Other commands and main_callback, if __name__ == "__main__": app() remain unchanged) ...


@app.command(name="add", help="Manually add a command to the database.")
def add_command_manual(
    command: Annotated[str, typer.Option("--command", "-c", prompt="Enter command to save (raw_command)", help="Actual command line instruction.")],
    description_input: Annotated[Optional[str], typer.Option("--description", "-d", help="Description of this command (can be in Chinese, will attempt translation to English).")] = None,
    tags_input: Annotated[Optional[str], typer.Option("--tags", "-t", help="Comma-separated list of tags (English recommended).")] = None,
    # processed_command_input: Annotated[Optional[str], typer.Option("--proc-cmd", help="(Optional) Processed/normalized/LLM-generated English command. If empty, will attempt to generate from description.")] = None
):
    if description_input is None:
        description_input = typer.prompt("Enter command description (can be in Chinese, will attempt English translation, optional)", default="", show_default=False)

    base_cmd_for_context = utils.get_base_command(command)
    command_context_data = {"which_info": "N/A", "help_info": "N/A", "man_info": "N/A"}
    if base_cmd_for_context:
        typer.echo(f"Fetching context info for '{base_cmd_for_context}'...")
        command_context_data = utils.get_command_context(command)

    english_description = description_input 
    if description_input and description_input.strip():
        # Simple check if translation is needed (e.g., contains Chinese characters)
            # More complex language detection like langdetect could be used but adds dependencies
        # Here we assume if user input is Chinese, translate it; if English, translation has minimal impact
        # Alternatively could add a --lang option for user to specify input language
        translated_desc = llm_handler.translate_text(description_input, target_language="English")
        if translated_desc:
            english_description = translated_desc
            if description_input != english_description:
                 typer.echo(f"Description translated to English: \"{english_description}\"")
        else:
            typer.secho("⚠️ Description translation failed, will use original input as English description (no effect if original was English).", fg=typer.colors.YELLOW)
    
    # if not english_description or not english_description.strip(): 
    english_description += llm_handler.generate_description(
        command,
        base_cmd_for_context,
        command_context_data) 
    if english_description:
        typer.echo(f"English description generated from command: \"{english_description}\"")
    else:
        typer.secho("⚠️ Failed to generate English description from command, description will be empty.", fg=typer.colors.YELLOW)
        english_description = None #

    english_processed_command = None
    if english_description: 
        english_processed_command = llm_handler.generate_command_from_description(english_description)
        if english_processed_command:
            typer.echo(f"Processed command generated from English description: `{english_processed_command}`")
    
    tag_list = [tag.strip() for tag in tags_input.split(',')] if tags_input else []

    entry_data = {
        "raw_command": command,
        "processed_command": english_processed_command or command, #
        "description": english_description, 
        "tags": tag_list, 
        "source": "manual_add",
        "which_info": command_context_data["which_info"],
        "help_info": command_context_data["help_info"],
        "man_info": command_context_data["man_info"]
    }
    
    command_to_store = models.CommandEntry(**entry_data)
    command_id = database.add_command(command_to_store)

    if command_id:
        typer.secho(f"✅ Command '{command_to_store.raw_command[:50]}...' successfully added, ID: {command_id}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"❌ Failed to add command (may already exist or database error).", fg=typer.colors.RED)


@app.callback()
def main_callback():
    """
    CLIHunter: Your smart CLI assistant! (English content preferred)
    """
    pass

if __name__ == "__main__":
    app()
