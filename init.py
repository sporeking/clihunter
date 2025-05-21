import sqlite3
import uuid
import time
import os
from pathlib import Path
# from your_llm_module import get_llm_client # 你需要实现这个

# --- 配置 ---
DB_PATH = Path.home() / ".clihunter" / "commands.db"
DEFAULT_EXCLUDE_COMMANDS = {'ls', 'cd', 'pwd', 'clear', 'exit', 'history'} # 简化版
LLM_BATCH_SIZE = 10

# --- 数据库操作 ---
def get_db_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # 创建表 (如果还没创建)
    # ... (执行上面的 CREATE TABLE 语句)
    return conn

def insert_command_batch(conn, commands_data):
    # commands_data is a list of tuples:
    # (id, raw_cmd, processed_cmd, desc, src, hist_ts)
    try:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR IGNORE INTO saved_commands
            (id, raw_command, processed_command, description, source, history_timestamp, added_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, STRFTIME('%s', 'now'))
        """, commands_data)
        conn.commit()
        return cursor.rowcount # 返回实际插入的行数
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return 0

# --- History 解析 ---
def parse_bash_history(file_path):
    commands = []
    try:
        with open(file_path, 'r', errors='ignore') as f:
            for line in f:
                cmd_text = line.strip()
                if cmd_text: # 忽略空行
                    commands.append({'text': cmd_text, 'timestamp': None}) # Bash history 默认不带时间戳
    except FileNotFoundError:
        print(f"History file not found: {file_path}")
    return commands

def parse_zsh_history(file_path):
    commands = []
    try:
        with open(file_path, 'r', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(';', 1)
                cmd_text = parts[-1]
                timestamp = None
                if len(parts) > 1 and parts[0].startswith(': '):
                    try:
                        ts_duration = parts[0][2:].split(':')
                        timestamp = int(ts_duration[0])
                    except (ValueError, IndexError):
                        pass #无法解析时间戳
                if cmd_text:
                    commands.append({'text': cmd_text, 'timestamp': timestamp})
    except FileNotFoundError:
        print(f"History file not found: {file_path}")
    return commands

# --- LLM 处理 ---
# 假设你有一个 LLM 客户端 llm_client
# llm_client = get_llm_client()

def llm_generate_description(command_text):
    # prompt = f"..." (如上文设计)
    # response = llm_client.generate(prompt)
    # return response.text
    # 模拟LLM调用
    print(f"LLM: Generating description for '{command_text[:30]}...'")
    time.sleep(0.1) # 模拟网络延迟
    return f"This is a generated description for: {command_text}"

def llm_rewrite_command(command_text):
    # prompt = f"..." (如上文设计)
    # response = llm_client.generate(prompt)
    # return response.text
    # 模拟LLM调用
    print(f"LLM: Rewriting command for '{command_text[:30]}...'")
    time.sleep(0.1)
    return command_text # 简单返回原始命令

# --- 主初始化逻辑 (可以放在 Typer 命令中) ---
def initialize_from_history(shell_type: str = "bash"):
    if shell_type == "bash":
        hist_file = Path.home() / ".bash_history"
        parsed_commands = parse_bash_history(hist_file)
        source_name = "bash_history"
    elif shell_type == "zsh":
        hist_file_env = os.getenv("HISTFILE")
        hist_file = Path(hist_file_env) if hist_file_env else Path.home() / ".zsh_history"
        parsed_commands = parse_zsh_history(hist_file)
        source_name = "zsh_history"
    else:
        print(f"Unsupported shell type: {shell_type}")
        return

    if not parsed_commands:
        print("No commands found in history.")
        return

    print(f"Found {len(parsed_commands)} commands in {shell_type} history.")

    # 预过滤和初步去重 (基于原始文本)
    unique_raw_commands = {} # {cmd_text: earliest_timestamp}
    for cmd_info in parsed_commands:
        cmd_text = cmd_info['text']
        # 排除逻辑
        first_word = cmd_text.split(' ')[0]
        if cmd_text in DEFAULT_EXCLUDE_COMMANDS or \
           first_word in DEFAULT_EXCLUDE_COMMANDS or \
           len(cmd_text) < 5: # 简单长度过滤
            continue
        
        # 保留最早的时间戳
        if cmd_text not in unique_raw_commands or \
           (cmd_info['timestamp'] and (unique_raw_commands[cmd_text] is None or cmd_info['timestamp'] < unique_raw_commands[cmd_text])):
            unique_raw_commands[cmd_text] = cmd_info['timestamp']

    commands_to_process = list(unique_raw_commands.items())
    print(f"After pre-filtering and deduplication, {len(commands_to_process)} commands to process.")

    conn = get_db_connection()
    llm_processed_batch = []
    total_actually_inserted = 0

    for i, (raw_cmd, hist_ts) in enumerate(commands_to_process):
        print(f"Processing command {i+1}/{len(commands_to_process)}: {raw_cmd[:50]}...")
        
        # 模拟LLM处理（实际中应有错误处理和重试）
        description = llm_generate_description(raw_cmd)
        processed_cmd = llm_rewrite_command(raw_cmd)

        llm_processed_batch.append((
            str(uuid.uuid4()),
            raw_cmd,
            processed_cmd,
            description,
            source_name,
            hist_ts
        ))

        if len(llm_processed_batch) >= LLM_BATCH_SIZE or (i + 1) == len(commands_to_process):
            print(f"Inserting batch of {len(llm_processed_batch)} commands into database...")
            inserted_count = insert_command_batch(conn, llm_processed_batch)
            total_actually_inserted += inserted_count
            print(f"Actually inserted {inserted_count} new commands from this batch.")
            llm_processed_batch = []
            time.sleep(0.5) # 避免过于频繁的DB写入或API调用

    conn.close()
    print(f"Initialization complete. Total new commands added to database: {total_actually_inserted}")

# if __name__ == "__main__":
#     # 这是一个简化的测试调用，实际中会通过 Typer CLI 调用
#     # conn = get_db_connection()
#     # create_tables(conn) # 确保表已创建
#     # conn.close()
#     initialize_from_history(shell_type="zsh") # 或 "bash"