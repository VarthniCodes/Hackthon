from flask import Flask, request, jsonify, render_template
from rapidfuzz import fuzz
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
DB_NAME = "safety.db"

# =====================================================
# DATABASE
# =====================================================

def get_db():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        content TEXT,
        sender TEXT,
        risk_type TEXT,
        risk_score REAL
    )
    """)

    conn.commit()
    conn.close()

init_db()

# =====================================================
# KEYWORD PATTERNS
# =====================================================

PATTERNS = {
    "self_harm": [
        "suicide", "kill myself", "want to die",
        "end my life", "cut myself", "i cant go on"
    ],
    "grooming": [
        "dont tell", "our secret", "keep this secret",
        "keep this between us", "meet alone", "send photo"
    ],
    "cyberbullying": [
        "worthless", "loser", "ugly", "kill yourself",
        "stupid", "idiot", "you are nothing"
    ],
    "sextortion": [
        "send nudes", "naked pic", "leak your pics"
    ],
    "drugs": ["buy weed", "cocaine", "heroin"],
    "scam": ["send money", "bitcoin", "gift card"]
}

NEGATIVE_EMOTION_WORDS = [
    "sad", "hopeless", "alone", "depressed", "empty",
    "worthless", "angry", "hurt", "crying"
]

# =====================================================
# KEYWORD DETECTION
# =====================================================

def keyword_detection(text):
    text_lower = text.lower()

    for risk, words in PATTERNS.items():
        for word in words:
            if word in text_lower:
                return {"risk_type": risk, "score": 0.75}

    return {"risk_type": "none", "score": 0}

# =====================================================
# FUZZY DETECTION (TYPO HANDLING)
# =====================================================

def fuzzy_detection(text):
    text_lower = text.lower()
    words = text_lower.split()

    for risk, keywords in PATTERNS.items():
        for keyword in keywords:
            for word in words:
                if fuzz.partial_ratio(keyword, word) > 85:
                    return {"risk_type": risk, "score": 0.65}

    return {"risk_type": "none", "score": 0}

# =====================================================
# LIGHTWEIGHT "AI" MEANING DETECTION
# =====================================================

def intent_detection(text):
    text_lower = text.lower()

    for word in NEGATIVE_EMOTION_WORDS:
        if word in text_lower:
            return {"risk_type": "emotional_distress", "score": 0.5}

    return {"risk_type": "none", "score": 0}

# =====================================================
# HYBRID RISK ENGINE
# =====================================================

def analyze_risk(text):

    results = [
        keyword_detection(text),
        fuzzy_detection(text),
        intent_detection(text)
    ]

    best = max(results, key=lambda x: x["score"])
    score = best["score"]

    if score >= 0.8:
        level = "critical"
    elif score >= 0.6:
        level = "high"
    elif score >= 0.4:
        level = "medium"
    else:
        level = "safe"

    return {
        "risk_type": best["risk_type"],
        "risk_score": score,
        "risk_level": level
    }

# =====================================================
# INTERVENTION ENGINE
# =====================================================

def decide_action(risk, sender):

    risk_type = risk["risk_type"]
    level = risk["risk_level"]

    action = {
        "child_nudge": None,
        "parent_alert": False
    }

    if sender == "child" and risk_type == "self_harm":
        action["child_nudge"] = (
            "You don’t have to handle this alone. "
            "Please talk to a trusted adult."
        )
        action["parent_alert"] = True

    elif sender == "stranger" and risk_type == "cyberbullying":
        action["child_nudge"] = (
            "The way someone is speaking to you isn’t okay. "
            "You deserve respect."
        )
        action["parent_alert"] = True

    elif sender == "child" and risk_type == "cyberbullying":
        action["child_nudge"] = (
            "Some messages can hurt more than we realize. "
            "Take a moment before sending messages."
        )

    elif sender == "stranger" and risk_type in ["grooming", "sextortion"]:
        action["child_nudge"] = (
            "You should never keep secrets or share personal information. "
            "Please talk to a trusted adult."
        )
        action["parent_alert"] = True

    elif sender == "child" and level == "medium":
        action["child_nudge"] = (
            "It seems you might be upset. Talking to someone you trust can help."
        )

    return action

# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def home():
    return render_template("child.html")

@app.route("/parent")
def parent():
    return render_template("parent.html")

@app.route("/api/analyze", methods=["POST"])
def analyze():

    data = request.json
    text = data.get("text", "")
    sender = data.get("sender", "unknown")

    risk = analyze_risk(text)
    action = decide_action(risk, sender)

    if action["parent_alert"]:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO alerts (timestamp, content, sender, risk_type, risk_score)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            text,
            sender,
            risk["risk_type"],
            risk["risk_score"]
        ))
        conn.commit()
        conn.close()

    return jsonify({**risk, **action})

@app.route("/api/alerts")
def get_alerts():

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "timestamp": r[1],
            "content": r[2],
            "sender": r[3],
            "risk_type": r[4],
            "risk_score": r[5]
        } for r in rows
    ])

# =====================================================
# RUN (Render compatible)
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
