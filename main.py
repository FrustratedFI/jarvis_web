import sys
import os
import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from PyQt6 import QtWidgets, QtCore

# ------------------ CONFIG ------------------
API_KEY = os.getenv("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")

if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable not set.")

MODEL_NAME = "openrouter/auto"

# ------------------ MEMORY ------------------
conn = sqlite3.connect("jarvis_memory.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    key TEXT,
    value TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

def memory_store(category: str, key: str, value: str):
    cur.execute(
        "INSERT INTO memory (category,key,value) VALUES (?,?,?)",
        (category, key, value)
    )
    conn.commit()

def memory_recall(category: str, key: str):
    cur.execute(
        "SELECT value, created_at FROM memory 
         WHERE category=? AND key LIKE ? 
         ORDER BY created_at DESC",
        (category, f"%{key}%")
    )
    return cur.fetchall()

def get_user_info():
    cur.execute("SELECT value FROM memory WHERE category='user_info' ORDER BY created_at DESC")
    rows = cur.fetchall()
    return "\n".join([r[0] for r in rows]) if rows else ""

# ------------------ WEB SEARCH ------------------
def web_search(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(
            f"https://www.google.com/search?q={query}",
            headers=headers,
            timeout=5
        )
        soup = BeautifulSoup(res.text, "html.parser")
        snippet = soup.select_one('div.BNeawe.s3v9rd.AP7Wnd')
        return snippet.text if snippet else "I found no clear answer online."
    except Exception as e:
        return f"Web search error: {str(e)}"

# ------------------ AI RESPONSE ------------------
def get_jarvis_response(user_input, context_text="", conversation_history=None):
    if conversation_history is None:
        conversation_history = []

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Jarvis Web"
    }

    messages = []

    if context_text:
        messages.append({"role": "system", "content": context_text})

    for msg in conversation_history[-10:]:
        role = "user" if msg.startswith("User:") else "assistant"
        messages.append({
            "role": role,
            "content": msg.split(": ", 1)[1]
        })

    messages.append({"role": "user", "content": user_input})

    payload = {
        "model": MODEL_NAME,
        "messages": messages
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    except Exception as e:
        return f"AI Error: {str(e)}"

# ------------------ WORKER THREAD ------------------
class Worker(QtCore.QThread):
    finished = QtCore.pyqtSignal(str)

    def __init__(self, func, *args):
        super().__init__()
        self.func = func
        self.args = args

    def run(self):
        result = self.func(*self.args)
        self.finished.emit(result)

# ------------------ GUI ------------------
class ChatWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI")
        self.setGeometry(400, 100, 600, 700)
        self.setStyleSheet("background-color: #1e1e1e; color: white; font-size: 14px;")

        self.layout = QtWidgets.QVBoxLayout(self)

        self.chat_area = QtWidgets.QTextEdit(self)
        self.chat_area.setReadOnly(True)
        self.chat_area.setStyleSheet("""
            background-color: #121212;
            color: white;
            border-radius: 5px;
            padding: 10px;
        """)

        self.input_line = QtWidgets.QLineEdit(self)
        self.input_line.setPlaceholderText("Type a message...")
        self.input_line.setStyleSheet("""
            background-color: #252525;
            color: white;
            padding: 10px;
            border-radius: 5px;
        """)

        self.send_button = QtWidgets.QPushButton("Send")
        self.send_button.setStyleSheet("""
            background-color: #007ACC;
            color: white;
            padding: 10px;
            border-radius: 5px;
        """)

        input_layout = QtWidgets.QHBoxLayout()
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(self.send_button)

        self.layout.addWidget(self.chat_area)
        self.layout.addLayout(input_layout)

        self.send_button.clicked.connect(self.handle_user_input)
        self.input_line.returnPressed.connect(self.handle_user_input)

        self.conversation_history = []

    # ------------------ DISPLAY ------------------
    def add_chat_message(self, sender, message):
        color = "#ffffff" if sender == "You" else "#00ff99"
        formatted = message.replace("\n", "<br>")
        self.chat_area.append(
            f"<b><span style='color:{color}'>{sender}:</span></b> {formatted}"
        )
        self.chat_area.verticalScrollBar().setValue(
            self.chat_area.verticalScrollBar().maximum()
        )

    # ------------------ INPUT ------------------
    def handle_user_input(self):
        user_text = self.input_line.text().strip()
        if not user_text:
            return

        self.input_line.clear()
        self.add_chat_message("You", user_text)

        lower = user_text.lower()

        # MEMORY COMMANDS
        if lower.startswith("remember "):
            info = user_text[9:].strip()
            memory_store("user_info", "auto", info)
            self.add_chat_message("Jarvis", "Got it. I’ll remember that.")
            return

        if lower.startswith("recall "):
            key = user_text[7:].strip()
            records = memory_recall("user_info", key)
            if not records:
                self.add_chat_message("Jarvis", "I don’t remember anything about that.")
            else:
                recall_text = "\n".join(
                    [f"- {val} (added on {date})" for val, date in records]
                )
                self.add_chat_message("Jarvis", recall_text)
            return

        # TIME COMMANDS
        if lower in ["what time is it", "current time", "date today", "what is the date"]:
            now = datetime.now()
            time_str = now.strftime("%A, %d %B %Y %H:%M:%S")
            self.add_chat_message("Jarvis", f"Current date & time: {time_str}")
            return

        # WEB SEARCH
        if lower.startswith("search "):
            query = user_text[7:].strip()
            self.worker = Worker(web_search, query)
            self.worker.finished.connect(
                lambda result: self.add_chat_message("Jarvis", result)
            )
            self.worker.start()
            return

        # AI RESPONSE
        context_text = get_user_info()
        self.worker = Worker(
            get_jarvis_response,
            user_text,
            context_text,
            self.conversation_history
        )
        self.worker.finished.connect(
            lambda reply: self.handle_ai_response(user_text, reply)
        )
        self.worker.start()

    def handle_ai_response(self, user_input, reply):
        self.conversation_history.append(f"User: {user_input}")
        self.conversation_history.append(f"Jarvis: {reply}")
        memory_store("conversation", "auto", f"User: {user_input}")
        memory_store("conversation", "auto", f"Jarvis: {reply}")
        self.add_chat_message("Jarvis", reply)

# ------------------ RUN ------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ChatWindow()
    window.show()
    sys.exit(app.exec())
