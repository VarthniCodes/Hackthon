from flask import Flask, render_template, request, jsonify
from datetime import datetime
import sqlite3
from rapidfuzz import fuzz

app = Flask(__name__)

DB_NAME = "safety.db"


# =========================
# DATABASE
# =========================

def get_db():
    return sqlite3.connect(DB_NAME)


def init_db():
    with get_db() as conn:
        c = conn.cursor()

        # Alerts table (parent receives alert + nudge)
        c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            content TEXT,
            sender TEXT,
            risk_type TEXT,
            risk_level TEXT,
            risk_score REAL,
            context TEXT,
            nudge TEXT
        )
        """)

        # Settings table
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            parent_consent INTEGER,
            monitoring_enabled INTEGER,
            alert_threshold REAL
        )
        """)

        # Default settings
        c.execute("SELECT * FROM settings WHERE id=1")
        if not c.fetchone():
            # consent OFF initially, monitoring OFF
            c.execute("INSERT INTO settings VALUES (1,0,0,0.6)")


init_db()


# =========================
# INTERVENTION NUDGES
# =========================

NUDGE_MESSAGES = {
    "self_harm": {
        "critical": "It sounds like you're going through something really painful. You don’t have to handle this alone. Please talk to a trusted adult immediately. You matter more than you know.",
        "high": "I noticed you might be feeling overwhelmed. Talking to a trusted adult can really help. You don’t have to deal with this alone."
    },
    "cyberbullying": {
        "high": "The way someone is speaking to you isn’t okay. You deserve respect. Consider saving the messages and telling a trusted adult."
    },
    "grooming": {
        "high": "When someone asks you to keep secrets or share personal photos, that’s a warning sign. Please talk to a trusted adult right away."
    },
    "sextortion": {
        "high": "You should never feel pressured to share personal photos. Please talk to a trusted adult immediately."
    },
    "soft": "If any conversation makes you uncomfortable, it's always okay to talk to a trusted adult."
}


def get_nudge(risk_type, risk_level):
    if risk_type in NUDGE_MESSAGES:
        return NUDGE_MESSAGES[risk_type].get(risk_level)

    if risk_level in ["medium", "low"]:
        return NUDGE_MESSAGES["soft"]

    return None


# =========================
# RISK DETECTION ENGINE
# =========================

PATTERNS = {
    "self_harm": [
        "suicide", "kill myself", "end my life",
        "cut myself", "want to die", "i want to die",
        "better off dead"
    ],
    "grooming": [
        "dont tell", "our secret", "keep this secret",
        "promise you wont tell", "send photo",
        "meet alone", "mature for your age"
    ],
    "cyberbullying": [
        "kill yourself", "loser", "worthless",
        "ugly", "nobody likes you"
    ],
    "drugs": [
        "buy weed", "cocaine", "heroin", "mdma", "meth"
    ],
    "sextortion": [
        "send nudes", "naked pic", "blackmail",
        "leak your pics", "share your photos"
    ],
    "scam": [
        "send money", "bitcoin", "gift card", "wire transfer"
    ]
}


def analyze_risk(text):
    text_lower = text.lower()
    words = text_lower.split()

    detected = []

    for risk_type, keywords in PATTERNS.items():
        matches = 0

        for keyword in keywords:
            if keyword in text_lower:
                matches += 1
            else:
                for word in words:
                    if fuzz.ratio(keyword, word) > 85:
                        matches += 1
                        break

        if matches:
            score = min(0.5 + matches * 0.1, 1.0)
            detected.append({"risk_type": risk_type, "score": score})

    if not detected:
        return {
            "risk_type": "none",
            "risk_level": "safe",
            "risk_score": 0,
            "explanation": "No concerning content detected.",
            "nudge": None
        }

    highest = max(detected, key=lambda x: x["score"])
    score = highest["score"]

    if score >= 0.8:
        level = "critical"
    elif score >= 0.6:
        level = "high"
    elif score >= 0.4:
        level = "medium"
    else:
        level = "low"

    explanations = {
        "self_harm": "Self-harm indicators detected.",
        "grooming": "Possible grooming behavior detected.",
        "cyberbullying": "Harmful language detected.",
        "drugs": "Drug-related content detected.",
        "sextortion": "Possible sextortion detected.",
        "scam": "Possible scam detected."
    }

    nudge = get_nudge(highest["risk_type"], level)

    return {
        "risk_type": highest["risk_type"],
        "risk_level": level,
        "risk_score": score,
        "explanation": explanations.get(highest["risk_type"]),
        "nudge": nudge
    }


# =========================
# ROUTES
# =========================

@app.route("/")
def index():
    """Show consent page first, then child device UI."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT parent_consent FROM settings WHERE id=1")
        row = c.fetchone()

    consent_given = row[0] if row else 0

    if not consent_given:
        return render_template("consent.html")

    return render_template("child.html")


@app.route("/api/consent", methods=["POST"])
def give_consent():
    """Parent gives consent → enable monitoring."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE settings
            SET parent_consent=1, monitoring_enabled=1
            WHERE id=1
        """)
    return jsonify({"success": True})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    # Check consent before monitoring
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT parent_consent FROM settings WHERE id=1")
        consent = c.fetchone()[0]

    if not consent:
        return jsonify({"error": "Monitoring not enabled"}), 403

    text = data.get("text", "").strip()
    sender = data.get("sender", "unknown")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    analysis = analyze_risk(text)
    analysis["sender"] = sender

    # High-risk categories always alert parent
    HIGH_RISK_TYPES = ["grooming", "sextortion", "self_harm", "cyberbullying"]

    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT monitoring_enabled, alert_threshold FROM settings WHERE id=1"
        )
        monitoring_enabled, threshold = c.fetchone()

        if (
            analysis["risk_type"] in HIGH_RISK_TYPES or
            (monitoring_enabled and analysis["risk_score"] >= threshold)
        ):
            c.execute("""
                INSERT INTO alerts
                (timestamp, content, sender, risk_type, risk_level, risk_score, context, nudge)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                datetime.now().isoformat(),
                text,
                sender,
                analysis["risk_type"],
                analysis["risk_level"],
                analysis["risk_score"],
                analysis["explanation"],
                analysis["nudge"]
            ))

    return jsonify(analysis)


@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    """Parent dashboard alerts."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 50")
        rows = c.fetchall()

    alerts = [
        {
            "id": r[0],
            "timestamp": r[1],
            "content": r[2],
            "sender": r[3],
            "risk_type": r[4],
            "risk_level": r[5],
            "risk_score": r[6],
            "context": r[7],
            "nudge": r[8],
        }
        for r in rows
    ]

    return jsonify(alerts)


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
