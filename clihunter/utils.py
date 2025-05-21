# clihunter/shell_utils.py
import subprocess
import shlex 
from typing import Dict, Optional, List

# Restrict the number of lines or tokens from "--help" or "man"
# This is to avoid overwhelming the user with too much information.
MAX_CONTEXT_LINES = 30
MAX_CONTEXT_CHARS = 1500 

def _run_shell_command(cmd_parts: List[str], timeout: int = 3) -> Optional[str]:
    """
    run a shell command and capture its stdout and stderr.
    Prefer stdout, if empty and command has error (usually help info will print to stderr), return stderr.
    :param cmd_parts: List of command parts to be executed.
    :param timeout: Timeout for the command execution in seconds.
    :return: The output of the command or None if no output.
    """
    try:
        process = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,        
            timeout=timeout,  
            check=False,      
            errors='replace'  
        )
        
        output = ""
        if process.stdout and process.stdout.strip():
            output = process.stdout.strip()
        elif process.stderr and process.stderr.strip():
            stderr_lower = process.stderr.lower()
            if "usage:" in stderr_lower or "help" in stderr_lower or "option" in stderr_lower or process.returncode != 0:
                output = process.stderr.strip()
        
        if not output:
            return None

        lines = output.splitlines()
        if len(lines) > MAX_CONTEXT_LINES:
            output = "\n".join(lines[:MAX_CONTEXT_LINES]) + f"\n... (Content has been truncated, total num of lines: {len(lines)})"
        
        if len(output) > MAX_CONTEXT_CHARS:
            output = output[:MAX_CONTEXT_CHARS] + "... (Content has been truncated)"
            
        return output

    except subprocess.TimeoutExpired:
        return f"Error: Command '{' '.join(cmd_parts)}' timeout ({timeout} seconds)."
    except FileNotFoundError: 
        return f"Error: Command '{cmd_parts[0]}' not found."
    except Exception as e:
        return f"Error: An unexpected error occurred while executing '{' '.join(cmd_parts)}': {e}"

def get_base_command(raw_command_text: str) -> Optional[str]:
    """
    get the base command from a raw command text.
    e.g. get 'ls' from 'ls -l --color=auto'
    """
    try:
        parts = shlex.split(raw_command_text)
        if not parts:
            return None
        
        for part in parts:
            if '=' not in part:
                if part.startswith('-') and part != parts[0]: 
                    continue 
                if part == "sudo":
                    continue
                return part 
        
        return parts[0] if parts else None

    except ValueError: 
        return raw_command_text.split(' ')[0] if raw_command_text else None
    except Exception: 
        return None


def get_command_context(raw_command_text: str) -> Dict[str, Optional[str]]:
    """
    get some context from (which, --help, man)。
    """
    context = {
        "which_info": "N/A", # Not Applicable / Not Available
        "help_info": "N/A",
        "man_info": "N/A",
    }
    base_command = get_base_command(raw_command_text)

    if not base_command:
        return context

    # 1. which <base_command>
    which_info = _run_shell_command(["which", base_command], timeout=1)
    if f"no {base_command} in" in which_info.lower():
        context["which_info"] = "N/A"
    else:
        context["which_info"] = which_info

    # 2. <base_command> --help
    help_flags_tried = ["--help", "-h", "help"] 
    for flag in help_flags_tried:
        cmd_to_run = [base_command, flag] if flag == "help" and base_command not in ["help"] else [base_command, flag]
        if base_command == "help" and flag == "help": 
            cmd_to_run = [base_command, "--help"] 

        help_output = _run_shell_command(cmd_to_run)
        if help_output and "error" not in help_output.lower() and \
           "invalid option" not in help_output.lower() and \
           "unknown command" not in help_output.lower() and \
           "not found" not in help_output.lower() and \
           len(help_output) > 20: 
            context["help_info"] = help_output
            break 

    # 3. man <base_command> | col -bx (col -bx to clean up the output)
    try:
        man_cmd = ["man", base_command]
        man_process = subprocess.Popen(man_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        col_process = subprocess.Popen(["col", "-bx"], stdin=man_process.stdout, 
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        man_process.stdout.close() 

        stdout_bytes, stderr_bytes = col_process.communicate(timeout=3) 
        man_output_cleaned = stdout_bytes.decode(errors='replace').strip()

        if col_process.returncode == 0 and man_output_cleaned:
            lines = man_output_cleaned.splitlines()
            if len(lines) > MAX_CONTEXT_LINES:
                man_output_cleaned = "\n".join(lines[:MAX_CONTEXT_LINES]) + f"\n... (Content has been truncated, total number of lines: {len(lines)})"
            if len(man_output_cleaned) > MAX_CONTEXT_CHARS:
                man_output_cleaned = man_output_cleaned[:MAX_CONTEXT_CHARS] + "... (Content has been truncated)"
            context["man_info"] = man_output_cleaned if man_output_cleaned.strip() else "N/A"
        else:
            # err_msg = stderr_bytes.decode(errors='replace').strip()
            # context["man_info"] = f"Man page not found or error processing: {err_msg[:100]}" if err_msg else "Man page not found or error."
            context["man_info"] = "N/A"


    except FileNotFoundError:  # 'man' or 'col' command doesn't exist
        context["man_info"] = "Error: 'man' or 'col' command not found in PATH."
    except subprocess.TimeoutExpired:
        context["man_info"] = f"Error: Timeout while fetching man page for '{base_command}'."
    except Exception as e:  # Other pipeline or subprocess errors
        context["man_info"] = f"Error: Unexpected error occurred while processing man page for '{base_command}': {e}"
        
    return context

if __name__ == '__main__':
    print("--- Testing get_base_command ---")
    print(f"'ls -l --color=auto': {get_base_command('ls -l --color=auto')}")
    print(f"'  sudo apt-get update  ': {get_base_command('  sudo apt-get update  ')}") 
    print(f"'VAR=1 LANG=C another-cmd --option value': {get_base_command('VAR=1 LANG=C another-cmd --option value')}")
    print(f"'my_alias_for_git_status': {get_base_command('my_alias_for_git_status')}")
    print(f"'(cd /tmp && echo hello)': {get_base_command('(cd /tmp && echo hello)')}") 

    print("\n--- Testing get_command_context ---")

    commands_to_test = ["ls", "git", "awk", "my_custom_alias_if_any", "non_existent_command_xyz"] 
    
    for cmd_text in commands_to_test:
        print(f"\n--- Context for: '{cmd_text}' (Base command: {get_base_command(cmd_text)}) ---")
        context = get_command_context(cmd_text)
        print(f"  Which: {context.get('which_info', 'N/A')[:100]}...")
        help_info_str = context.get('help_info', 'N/A') or 'N/A'
        man_info_str = context.get('man_info', 'N/A') or 'N/A'
        
        print(f"  Help: {help_info_str[:200].replace('\n', ' ')}...") 
        print(f"  Man: {man_info_str[:200].replace('\n', ' ')}...")
