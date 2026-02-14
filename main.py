# main.py
import sys
import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from PyQt6 import QtWidgets, QtCore, QtGui

# ------------------ CONFIG ------------------
GENIE_MODEL = "openrouter/free"
API_KEY = "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"

genai.configure(api_key=API_KEY)

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
    cur.execute("INSERT INTO memory (category,key,value) VALUES (?,?,?)", (category, key, value))
    conn.commit()

def memory_recall(category: str, key: str):
    cur.execute("SELECT value, created_at FROM memory WHERE category=? AND key LIKE ? ORDER BY created_at DESC", (category, f"%{key}%"))
    return cur.fetchall()

def get_user_info():
    cur.execute("SELECT value FROM memory WHERE category='user_info' ORDER BY created_at DESC")
    rows = cur.fetchall()
    return "\n".join([r[0] for r in rows]) if rows else ""

# ------------------ WEB SEARCH ------------------
def web_search(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(f"https://www.google.com/search?q={query}", headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        snippet = soup.select_one('div.BNeawe.s3v9rd.AP7Wnd')
        return snippet.text if snippet else "I found no clear answer online."
    except Exception as e:
        return f"Error during web search: {str(e)}"

# ------------------ JARVIS RESPONSE HELPER ------------------
def get_jarvis_response(user_input, context_text="", conversation_history=[]):
    messages = []
    if context_text:
        messages.append({"role": "system", "content": context_text})
    for msg in conversation_history[-10:]:
        role = "user" if msg.startswith("User:") else "assistant"
        messages.append({"role": role, "content": msg.split(": ", 1)[1]})
    messages.append({"role": "user", "content": user_input})

    try:
        response = genai.chat.create(
            model=GENIE_MODEL,
            messages=messages
        )
        return response.last.content[0].text
    except Exception as e:
        return f"Error communicating with Gemini: {str(e)}"

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
            line-height: 1.5em;
        """)
        self.chat_area.setFontPointSize(13)
        self.chat_area.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)

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

    def handle_user_input(self):
        user_text = self.input_line.text().strip()
        if not user_text:
            return
        self.input_line.clear()
        self.add_chat_message("You", user_text)
        QtCore.QTimer.singleShot(50, lambda: self.get_jarvis_response(user_text))

    def add_chat_message(self, sender, message):
        message = message.replace("\n", "<p style='margin:4px 0;'>")
        color = "#ffffff" if sender == "You" else "#00ff99"
        self.chat_area.append(f"<b><span style='color:{color}'>{sender}:</span></b> {message}")
        self.chat_area.verticalScrollBar().setValue(self.chat_area.verticalScrollBar().maximum())

    def get_jarvis_response(self, user_input):
        # MEMORY COMMANDS
        if user_input.lower().startswith("remember "):
            info = user_input[len("remember "):].strip()
            memory_store("user_info", "auto", info)
            self.add_chat_message("Jarvis", "Got it, I’ll remember that.")
            return

        if user_input.lower().startswith("recall "):
            key = user_input[len("recall "):].strip()
            records = memory_recall("user_info", key)
            if not records:
                self.add_chat_message("Jarvis", "I don’t remember anything about that.")
            else:
                recall_text = "<br>".join([f"- {val} (added on {date})" for val, date in records])
                self.add_chat_message("Jarvis", recall_text)
            return

        # DATE & TIME COMMANDS
        if any(word in user_input.lower() for word in ["time", "date", "day"]):
            now = datetime.now()
            time_str = now.strftime("%A, %d %B %Y %H:%M:%S")
            self.add_chat_message("Jarvis", f"Current date & time: {time_str}")
            return

        # WEB SEARCH COMMAND
        if user_input.lower().startswith("search ") or "google" in user_input.lower():
            query = user_input.replace("search", "").strip()
            if not query:
                query = user_input
            result = web_search(query)
            self.add_chat_message("Jarvis", f"Search result: {result}")
            return

        # GENERATIVE AI RESPONSE
        context_text = get_user_info()
        jarvis_reply = get_jarvis_response(user_input, context_text, self.conversation_history)

        # Update conversation history and memory
        self.conversation_history.append(f"User: {user_input}")
        self.conversation_history.append(f"Jarvis: {jarvis_reply}")
        memory_store("conversation", "auto", f"User: {user_input}")
        memory_store("conversation", "auto", f"Jarvis: {jarvis_reply}")

        self.add_chat_message("Jarvis", jarvis_reply)

# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ChatWindow()
    window.show()

    sys.exit(app.exec())
