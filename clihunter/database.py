# clihunter/database.py
import sqlite3
import time
import json # Used to store lists (like tags) in TEXT fields
# import numpy as np 
from pathlib import Path
from typing import List, Optional, Tuple, Any

# Import config and data models from our own project
from . import config # Get DATABASE_PATH and other configurations
from . import models # Get CommandEntry model

def get_db_connection() -> sqlite3.Connection:
    """
    Create and return a connection to SQLite database.
    Database path is obtained from config.py.
    """
    conn = sqlite3.connect(str(config.DATABASE_PATH))
    conn.row_factory = sqlite3.Row # Access data by column name
    return conn

def create_tables(conn: Optional[sqlite3.Connection] = None) -> None:
    """
    Create required tables in database if they don't exist.
    MVP version: Removed embedding column from saved_commands table.
    """
    close_conn_here = False
    if conn is None:
        conn = get_db_connection()
        close_conn_here = True

    cursor = conn.cursor()

    # saved_commands table: stores core command information
    # Removed embedding BLOB column
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS saved_commands (
        id TEXT PRIMARY KEY,
        raw_command TEXT NOT NULL UNIQUE,
        processed_command TEXT,
        description TEXT,
        tags TEXT, 
        source TEXT,
        history_timestamp INTEGER,
        added_timestamp INTEGER DEFAULT (STRFTIME('%s', 'now')),
        which_info TEXT,
        help_info TEXT,
        man_info TEXT
    )
    """)

    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS commands_fts USING fts5(
        command_id UNINDEXED,       -- saved_commands.id
        search_text,
        tokenize = 'porter unicode61' 
    )
    """)
    
    conn.commit()
    if close_conn_here:
        conn.close()
    print("Database tables created successfully or already exist (MVP schema).")


# --- CRUD ---

def add_command(entry: models.CommandEntry) -> Optional[str]:
    """
    Add a new command record to database (MVP version, no embedding).
    If raw_command already exists, insertion will be ignored due to UNIQUE constraint.
    On successful insertion, related text is also added to FTS5 table for searching.
    """
    # list in Pydantic model (like tags) needs to be serialized to JSON string
    tags_json = json.dumps(entry.tags or []) 

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            sql = """
                INSERT OR IGNORE INTO saved_commands 
                (id, raw_command, processed_command, description, tags, source, history_timestamp, added_timestamp, which_info, help_info, man_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                entry.id, 
                entry.raw_command, 
                entry.processed_command,
                entry.description,
                tags_json,
                entry.source,
                entry.history_timestamp,
                entry.added_timestamp,
                entry.which_info,
                entry.help_info,
                entry.man_info
            )
            cursor.execute(sql, params)

            if cursor.rowcount == 0:
                return None

            command_id = entry.id

            searchable_text = entry.get_searchable_text() 
            cursor.execute(
                "INSERT INTO commands_fts (command_id, search_text) VALUES (?, ?)",
                (command_id, searchable_text)
            )
            return command_id
            
    except sqlite3.Error as e:
        print(f"Database error occurred when adding command: {e}")
        return None
    
def clear_all_commands() -> bool:
    """
    Clear all data from saved_commands and commands_fts tables.
    Returns: True if operation succeeded, False if failed.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM saved_commands")
            deleted_saved = cursor.rowcount
            
            cursor.execute("DELETE FROM commands_fts")
            deleted_fts = cursor.rowcount
            
            # cursor.execute("INSERT INTO commands_fts(commands_fts) VALUES('vacuum')")

            conn.commit() 
            return True
    except sqlite3.Error as e:
        raise sqlite3.Error(f"Database error occurred when clearing commands: {e}")
    except Exception as ex: 
        raise ex


def _row_to_command_entry(row: sqlite3.Row) -> Optional[models.CommandEntry]:
    """Helper function: Convert sqlite3.Row to CommandEntry Pydantic model instance (MVP version)."""
    if row is None:
        return None
    
    data = dict(row)
    
    tags_json = data.get('tags')
    data['tags'] = json.loads(tags_json) if tags_json else []
    
    try:
        return models.CommandEntry(**data)
    except Exception as e:
        print(f"Error creating CommandEntry model from DB row: {e}, data: {dict(row)}")
        return None

def get_command_by_id(command_id: str) -> Optional[models.CommandEntry]:
    """Retrieve single command record from database by ID."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM saved_commands WHERE id = ?", (command_id,))
            row = cursor.fetchone()
            return _row_to_command_entry(row)
    except sqlite3.Error as e:
        print(f"Database error occurred when getting command by ID: {e}")
        return None

def get_command_by_raw_command(raw_command: str) -> Optional[models.CommandEntry]:
    """Retrieve single command record from database by raw command string."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM saved_commands WHERE raw_command = ?", (raw_command,))
            row = cursor.fetchone()
            return _row_to_command_entry(row)
    except sqlite3.Error as e:
        print(f"Database error occurred when getting command by raw command: {e}")
        return None

def get_all_commands(limit: Optional[int] = None, offset: int = 0) -> List[models.CommandEntry]:
    # """Retrieve all command records from database with pagination support."""
    """
    get all commands from the database.
    """
    commands = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            sql = "SELECT * FROM saved_commands ORDER BY added_timestamp DESC"
            params = []
            if limit is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            for row in rows:
                entry = _row_to_command_entry(row)
                if entry:
                    commands.append(entry)
        return commands
    except sqlite3.Error as e:
        print(f"An error occured when getting commands from DB: {e}")
        return []

def get_all_raw_commands() -> List[str]:
    raw_commands = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT raw_command FROM saved_commands")
            rows = cursor.fetchall()
            for row in rows:
                raw_commands.append(row['raw_command'])
        return raw_commands
    except sqlite3.Error as e:
        print(f"An error occured when get commands from DB: {e}")
        return []

def update_command(command_id: str, updated_entry_data: models.CommandEntry) -> bool:
    """
    Update a command in the database by its ID.
    No embedding now (MVP version).
    """
    tags_json = json.dumps(updated_entry_data.tags or [])

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            sql = """
                UPDATE saved_commands SET
                    raw_command = ?,
                    processed_command = ?,
                    description = ?,
                    tags = ?,
                    source = ?,
                    history_timestamp = ? ,
                    which_info = ?,
                    help_info = ?,
                    man_info = ?
                    /* added_timestamp always created when the table created */
                WHERE id = ?
            """
            params = (
                updated_entry_data.raw_command,
                updated_entry_data.processed_command,
                updated_entry_data.description,
                tags_json,
                updated_entry_data.source,
                updated_entry_data.history_timestamp,
                updated_entry_data.which_info,   
                updated_entry_data.help_info,  
                updated_entry_data.man_info, 
                command_id
            )
            cursor.execute(sql, params)

            if cursor.rowcount == 0:
                print(f"Update failed: No command found with ID {command_id}.")
                return False

            cursor.execute("DELETE FROM commands_fts WHERE command_id = ?", (command_id,))
            searchable_text = updated_entry_data.get_searchable_text()
            cursor.execute(
                "INSERT INTO commands_fts (command_id, search_text) VALUES (?, ?)",
                (command_id, searchable_text)
            )
            print(f"Successfully updated command with ID: {command_id}")
            return True
    except sqlite3.Error as e:
        print(f"An error occurred when updating the DB: {e}")
        return False


def delete_command(command_id: str) -> bool:
    """delete a command from the database by its ID."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM saved_commands WHERE id = ?", (command_id,))
            if cursor.rowcount == 0:
                print(f"Delete failed: No command found with ID {command_id}.")
                return False

            cursor.execute("DELETE FROM commands_fts WHERE command_id = ?", (command_id,))
            print(f"{command_id} deleted")
            return True
    except sqlite3.Error as e:
        print(f"An error occured when deleting the DB: {e}")
        return False

# --- FTS5 ---
def search_commands_fts(query_text: str, top_k: int = config.DEFAULT_TOP_K_RESULTS) -> List[Tuple[str, float]]:
    """
    use FTS5 to search for command_id and rank_score
    :param query_text: The text to search for.
    :param top_k: The number of top results to return.
    :return: A list of tuples containing command_id and rank_score.
    """
    results = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            sql = """
                SELECT command_id, rank 
                FROM commands_fts 
                WHERE search_text MATCH ? 
                ORDER BY rank 
                LIMIT ?
            """
            cursor.execute(sql, (query_text, top_k))
            rows = cursor.fetchall()
            for row in rows:
                results.append((row['command_id'], row['rank'])) 
        return results
    except sqlite3.Error as e:
        # print(f"{e}")
        return []


# --- Test MVP ---
if __name__ == "__main__":
    print("Initializing database and tables (MVP schema)...")
    # test_db_path_mvp = Path("./test_clihunter_mvp.db")
    # original_db_path = config.DATABASE_PATH 
    # config.DATABASE_PATH = test_db_path_mvp
    # if test_db_path_mvp.exists():
    #     test_db_path_mvp.unlink()

    create_tables() 
    commands = get_all_commands()
    for cmd in commands:
        print(f"ID: {cmd.id}, Raw: {cmd.raw_command[:30]}..., Desc: {cmd.description[:40]}...")

    print("\n--- Testing command addition (MVP) ---")
    test_cmd_1_data_mvp = {
        "raw_command": "grep -ril 'TODO' ./src --exclude-dir=node_modules",
        "processed_command": "grep recursive case-insensitive list-files 'TODO' in ./src exclude node_modules", 
        "description": "search for 'TODO' in files within ./src, case-insensitive, excluding node_modules directory.",
        "tags": ["search", "grep", "todo", "source_code"],
        "source": "manual_test_mvp",
        "history_timestamp": int(time.time()) - 3600,
    }
    test_cmd_1 = models.CommandEntry(**test_cmd_1_data_mvp)
    cmd1_id = add_command(test_cmd_1)

    test_cmd_2_data_mvp = {
        "raw_command": "tar -czvf backup.tar.gz /my/data",
        "processed_command": "create compressed tar archive of /my/data to backup.tar.gz", 
        "description": "Create a compressed tar archive of /my/data to backup.tar.gz.",
        "tags": ["backup", "archive", "tar"],
        "source": "manual_test_mvp_2",
    }
    test_cmd_2 = models.CommandEntry(**test_cmd_2_data_mvp)
    cmd2_id = add_command(test_cmd_2)

    commands = get_all_commands()
    for cmd in commands:
        print(f"ID: {cmd.id}, Raw: {cmd.raw_command[:30]}..., Desc: {cmd.description[:40]}...")

    print("\n--- Testing duplicate command addition (MVP, should be ignored) ---")
    add_command(test_cmd_2) 

    if cmd1_id:
        print(f"\n--- Testing get command by ID ({cmd1_id}) (MVP) ---")
        retrieved_cmd1 = get_command_by_id(cmd1_id)
        if retrieved_cmd1:
            print(retrieved_cmd1.model_dump_json(indent=2))

    print("\n--- Testing get all commands (MVP) ---")
    all_cmds = get_all_commands(limit=5)
    print(f"get {len(all_cmds)} commands:")
    for cmd in all_cmds:
        print(f"  ID: {cmd.id}, Raw: {cmd.raw_command[:30]}..., Desc: {cmd.description[:40]}...")

    print("\n--- Testing FTS full-text search (query 'backup data') (MVP) ---")
    fts_results = search_commands_fts("backup data", top_k=5)
    if fts_results:
        print(f"FTS results for 'backup data':")
        for cid, rank in fts_results:
            cmd_detail = get_command_by_id(cid)
            print(f"  ID: {cid}, Rank: {rank:.4f}, Command: {cmd_detail.raw_command if cmd_detail else 'N/A'}")

    if cmd1_id:
        print(f"\n--- Testing update command ({cmd1_id}) (MVP) ---")
        cmd_to_update = get_command_by_id(cmd1_id)
        if cmd_to_update:
            cmd_to_update.description = "Updated description for testing."
            cmd_to_update.tags.append("updated_mvp")
            
            update_command(cmd1_id, cmd_to_update)
            verified_cmd = get_command_by_id(cmd1_id)
            if verified_cmd:
                print("Description after updated:", verified_cmd.description)
                print("Tags after updated:", verified_cmd.tags)

    if cmd2_id:
        print(f"\n--- Testing delete command ({cmd2_id}) (MVP) ---")
        delete_command(cmd2_id)
        deleted_cmd_check = get_command_by_id(cmd2_id)
        print(f"ID {cmd2_id} deleted or not: {not deleted_cmd_check}")

    print("\nDatabase operations testing completed (MVP).")
    
