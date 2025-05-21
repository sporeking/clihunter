# clihunter/history_parser.py
import os
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable

# Import config from project, we'll use SHELL_HISTORY_FILES
from . import config

# Type alias for return data structure
HistoryEntry = Dict[str, Any] # Typically contains 'command': str and 'timestamp': Optional[int]

# --- Zsh History Parsing (supports extended format) ---
# Zsh extended history format is typically: ": <timestamp>:<duration>;<command>"
# Example: ": 1678886400:0;ls -l"
ZSH_EXTENDED_HISTORY_REGEX = re.compile(r":\s*(\d+):(\d+);(.*)")

def _parse_zsh_history(file_path: Path, num_entries: Optional[int] = None) -> List[HistoryEntry]:
    """Parse Zsh history file."""
    entries: List[HistoryEntry] = []
    if not file_path.exists():
        print(f"Zsh history file not found: {file_path}")
        return entries

    lines: List[str] = []
    try:
        # Read all lines, then take last N if needed
        with open(file_path, 'r', errors='ignore') as f: # errors='ignore' to handle potential encoding issues
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading Zsh history file ({file_path}): {e}")
        return entries
        
    if num_entries is not None and num_entries > 0:
        lines = lines[-num_entries:]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        match = ZSH_EXTENDED_HISTORY_REGEX.match(line)
        if match:
            timestamp_str, _, command = match.groups()
            try:
                timestamp = int(timestamp_str)
                entries.append({"command": command, "timestamp": timestamp})
            except ValueError:
                # If timestamp can't be parsed, still record command with None timestamp
                entries.append({"command": command, "timestamp": None})
        else:
            # If not extended format, treat as normal command (may have no timestamp)
            # Zsh may also have multi-line commands, usually connected with backslash `\`,
            # but in history files they may be merged or recorded specially.
            # Here we simply treat as single line.
            # If command starts with ": " but isn't standard extended format,
            # it may be written by some plugin/config, we try to remove it.
            if line.startswith(": ") and len(line) > 2 and line[2].isdigit(): # Avoid false positives
                pass # Already handled by ZSH_EXTENDED_HISTORY_REGEX or doesn't match
            
            # Simple multi-line command handling: if line ends with '\', it usually means continuation
            # But in history files they may already be merged
            # Here we assume lines in history file are already complete commands
            entries.append({"command": line, "timestamp": None})
            
    return entries


# --- Bash History Parsing ---
# Bash's HISTTIMEFORMAT environment variable, if set, writes timestamps as comments before commands
# Example:
# #1678886400
# ls -l
BASH_TIMESTAMP_REGEX = re.compile(r"#(\d+)")

def _parse_bash_history(file_path: Path, num_entries: Optional[int] = None) -> List[HistoryEntry]:
    """Parse Bash history file."""
    entries: List[HistoryEntry] = []
    if not file_path.exists():
        print(f"Bash history file not found: {file_path}")
        return entries

    lines: List[str] = []
    try:
        with open(file_path, 'r', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading Bash history file ({file_path}): {e}")
        return entries

    # If num_entries is specified, we need a way to get last N commands with their timestamps
    # Bash timestamps are on the line before commands, making this more complex than Zsh
    # For simplicity, if num_entries is specified, we parse fully then take last N
    # A more optimized approach would be reading file backwards, but that adds complexity

    current_timestamp: Optional[int] = None
    parsed_entries_temp: List[HistoryEntry] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        timestamp_match = BASH_TIMESTAMP_REGEX.match(line)
        if timestamp_match:
            try:
                current_timestamp = int(timestamp_match.group(1))
            except ValueError:
                current_timestamp = None # Reset if parsing fails
        else:
            # This line is a command
            # Bash multi-line commands are usually merged into one line in history,
            # or only first line is recorded.
            # If HISTCONTROL contains ignorespace, commands starting with space aren't recorded.
            parsed_entries_temp.append({"command": line, "timestamp": current_timestamp})
            current_timestamp = None # Timestamp only applies to next command

    if num_entries is not None and num_entries > 0:
        entries = parsed_entries_temp[-num_entries:]
    else:
        entries = parsed_entries_temp
        
    return entries


# --- Fish History Parsing ---
# Fish history format is similar to YAML:
# - cmd: git status --short
#   when: 1678886400
# - cmd: |
#     echo hello
#     echo world
#   when: 1678886401

def _parse_fish_history(file_path: Path, num_entries: Optional[int] = None) -> List[HistoryEntry]:
    """Parse Fish Shell history file."""
    entries: List[HistoryEntry] = []
    if not file_path.exists():
        print(f"Fish history file not found: {file_path}")
        return entries

    # Fish history files are UTF-8 encoded and have a specific structure
    # We use simple line matching here, but for very complex Fish history
    # (like multi-line command representations), a more robust YAML parser
    # or more complex regex might be needed.
    
    # Read all lines
    all_lines: List[str] = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
    except Exception as e:
        print(f"Error reading Fish history file ({file_path}): {e}")
        return entries
        
    current_cmd: Optional[str] = None
    is_multiline_cmd = False
    
    parsed_entries_temp: List[HistoryEntry] = []

    for line_raw in all_lines:
        line = line_raw.strip() # Handle line endings
        line_unstripped_indent = len(line_raw) - len(line_raw.lstrip()) # Preserve original indentation

        if line.startswith("- cmd:"):
            if current_cmd is not None: # Previous command ended without 'when' (unlikely but protected)
                parsed_entries_temp.append({"command": current_cmd.strip(), "timestamp": None})
                current_cmd = None
                is_multiline_cmd = False

            cmd_part = line[len("- cmd:"):].strip()
            if cmd_part == "|": # Start multi-line command
                current_cmd = ""
                is_multiline_cmd = True
            else:
                current_cmd = cmd_part
                is_multiline_cmd = False
        elif line.startswith("when:") and current_cmd is not None:
            try:
                timestamp_str = line[len("when:"):].strip()
                timestamp = int(timestamp_str)
                parsed_entries_temp.append({"command": current_cmd.strip(), "timestamp": timestamp})
            except ValueError:
                parsed_entries_temp.append({"command": current_cmd.strip(), "timestamp": None})
            current_cmd = None # Command processing complete
            is_multiline_cmd = False
        elif is_multiline_cmd and current_cmd is not None:
            # Handle multi-line command content, respecting indentation
            # Fish multi-line commands typically have extra indentation
            # We assume continuation lines have at least 2 spaces of indentation
            if line_unstripped_indent >= 2: # Heuristic rule
                 current_cmd += line_raw.lstrip() # Keep relative indentation, remove alignment spaces
            else: # Incorrect indentation, likely end of multi-line command
                is_multiline_cmd = False 
                # If current_cmd exists without 'when', could decide to save it here
                # But standard Fish format should have 'when', so we can ignore this case
                
    # If file ends with a command but no accompanying 'when' (unlikely)
    if current_cmd is not None:
        parsed_entries_temp.append({"command": current_cmd.strip(), "timestamp": None})

    if num_entries is not None and num_entries > 0:
        entries = parsed_entries_temp[-num_entries:]
    else:
        entries = parsed_entries_temp
        
    return entries

# --- Main loader function ---
# Map shell types to their corresponding parser functions
SHELL_PARSERS: Dict[str, Callable[[Path, Optional[int]], List[HistoryEntry]]] = {
    "bash": _parse_bash_history,
    "zsh": _parse_zsh_history,
    "fish": _parse_fish_history,
}

def load_history(
    shell_type: str, 
    num_entries: Optional[int] = None, 
    custom_hist_file: Optional[str] = None
) -> List[HistoryEntry]:
    """
    Load history for specified shell type.

    Args:
        shell_type (str): Shell type, e.g. 'bash', 'zsh', 'fish'.
        num_entries (Optional[int]): Number of recent history entries to load. If None, load all.
        custom_hist_file (Optional[str]): Optional custom history file path. If provided, ignores default path.

    Returns:
        List[HistoryEntry]: List of history entry dictionaries.
                           Each dict contains 'command' (str) and 'timestamp' (Optional[int]).
    """
    shell_type = shell_type.lower()
    
    if custom_hist_file:
        hist_file_path = Path(custom_hist_file).expanduser()
    else:
        hist_file_path = config.DEFAULT_SHELL_HISTORY_FILES.get(shell_type)

    if not hist_file_path:
        print(f"Error: Unsupported shell type '{shell_type}' or default history file path not found.")
        return []

    if not hist_file_path.exists():
        print(f"Error: History file '{hist_file_path}' does not exist.")
        return []

    parser_func = SHELL_PARSERS.get(shell_type)
    if not parser_func:
        print(f"Error: No parser configured for shell type '{shell_type}'.")
        return []

    print(f"Loading history from {hist_file_path} for {shell_type} (last {num_entries or 'all'} entries)...")
    start_time = time.time()
    entries = parser_func(hist_file_path, num_entries)
    duration = time.time() - start_time
    print(f"Loaded {len(entries)} commands from {shell_type} history in {duration:.2f} seconds.")
    
    # Simple post-processing: remove completely empty commands (if parser might produce them)
    valid_entries = [e for e in entries if e.get("command", "").strip()]
    if len(valid_entries) != len(entries):
        print(f"Removed {len(entries) - len(valid_entries)} empty commands.")

    return valid_entries


# --- Test code when run as main module ---
if __name__ == "__main__":
    # For testing, you can create fake history files or point to your own
    # To avoid affecting user data, it's recommended to create temporary test files

    # Create temporary test history files
    test_dir = Path("./temp_test_histories")
    test_dir.mkdir(exist_ok=True)

    # Zsh test file
    zsh_test_file = test_dir / "test_zsh_history.txt"
    with open(zsh_test_file, "w", encoding="utf-8") as f:
        f.write(": 1609459200:0;echo hello zsh\n")
        f.write("ls -l\n") # Normal line
        f.write(": 1609459260:0;git status\n")
        f.write(": 1609459320:0;command with spaces\n") # Contains spaces
        f.write("  \n") # Empty line
        f.write("echo $PATH\n") # Another normal command
    
    print("--- Testing Zsh parser ---")
    zsh_entries = load_history("zsh", custom_hist_file=str(zsh_test_file))
    for entry in zsh_entries:
        print(entry)
    print(f"Zsh total entries: {len(zsh_entries)}\n")

    print("--- Testing Zsh parser (last 2 entries) ---")
    zsh_entries_limited = load_history("zsh", num_entries=2, custom_hist_file=str(zsh_test_file))
    for entry in zsh_entries_limited:
        print(entry)
    print(f"Zsh (last 2 entries) total: {len(zsh_entries_limited)}\n")

    # Bash test file
    bash_test_file = test_dir / "test_bash_history.txt"
    with open(bash_test_file, "w", encoding="utf-8") as f:
        f.write("#1500000000\n")
        f.write("echo hello bash\n")
        f.write("pwd\n") # No timestamp
        f.write("#1500000060\n")
        f.write("export VAR=value\n")
        f.write("#1500000000\n") # Duplicate timestamp, only affects next command
        f.write("#1500000120\n") # New timestamp overwrites previous
        f.write("another command\n")
    
    print("--- Testing Bash parser ---")
    bash_entries = load_history("bash", custom_hist_file=str(bash_test_file))
    for entry in bash_entries:
        print(entry)
    print(f"Bash total entries: {len(bash_entries)}\n")

    # Fish test file
    fish_test_file = test_dir / "test_fish_history.txt"
    with open(fish_test_file, "w", encoding="utf-8") as f:
        f.write("- cmd: echo hello fish\n")
        f.write("  when: 1400000000\n")
        f.write("- cmd: cd /tmp\n")
        f.write("  when: 1400000001\n")
        f.write("- cmd: |\n")
        f.write("    echo line1\n")
        f.write("    echo line2\n")
        f.write("  when: 1400000002\n")
        f.write("- cmd: fish_command_without_when\n") # Simulate missing when

    print("--- Testing Fish parser ---")
    fish_entries = load_history("fish", custom_hist_file=str(fish_test_file))
    for entry in fish_entries:
        print(entry)
    print(f"Fish total entries: {len(fish_entries)}\n")
    
    # Clean up test files
    # zsh_test_file.unlink(missing_ok=True)
    # bash_test_file.unlink(missing_ok=True)
    # fish_test_file.unlink(missing_ok=True)
    # test_dir.rmdir()
    print(f"\nTest files kept in {test_dir} for inspection.")
