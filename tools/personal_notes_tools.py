import aiosqlite
import os
from pathlib import Path



async def save_note(content: str) -> str:
    # We are writing directly to the root of C: 
    # If the file does not appear here, the code is not running.
    db_path = "C:/notes.db"
    
    print(f"\n\n!!! ATTEMPTING TO WRITE TO: {db_path} !!!\n\n")
    
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, content TEXT)")
            await db.execute("INSERT INTO notes (content) VALUES (?)", (content,))
            await db.commit()
        return f"SUCCESS: Saved to {db_path}"
    except Exception as e:
        return f"FAILURE: {str(e)}"
    

# 1. Define the destination as a constant (Visible, transparent, non-negotiable)
NOTE_STORAGE_PATH = Path.home() / "Desktop" / "personal_notes.txt"


def save_as_txt(content: str) -> str:
    """
    Saves a note to the personal_notes.txt file on the Desktop.
    Use this tool whenever the user explicitly asks to save, log, or record a note.
    """
    print(f"\n\n!!! TOOL_EXECUTION_STARTED: Appending to {NOTE_STORAGE_PATH} !!!\n\n")

    try:
        # Runtime Safety: Ensure the directory exists to prevent FileNotFoundError
        NOTE_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Use 'a' (append) mode instead of 'w' (overwrite) to protect historical notes
        with open(NOTE_STORAGE_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{content}")
        return f"SUCCESS: Note appended to {NOTE_STORAGE_PATH}"
    except Exception as e:
        return f"FAILURE: {str(e)}"