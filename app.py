from flask import Flask, render_template, request, jsonify
from datetime import datetime
import sqlite3
from rapidfuzz import fuzz
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

DB_NAME = "safety.db"


# =========================
# DATABASE
# =========================

def get_db():
    return sqlite3.connect(DB_NAME)


def init_db():
    with get_db() as conn:
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            content TEXT,
            risk_type TEXT,
            risk_level TEXT,
            risk_score REAL,
            context TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            parent_consent INTEGER,
            monitoring_enabled INTEGER,
            alert_threshold REAL
        )
        """)

        c.execute("SELECT * FROM settings WHERE id=1")
        if not c.fetchone():
            c.execute(
                "INSERT INTO settings VALUES (1, 0, 0, 0.6)"
            )

init_db()


# =========================
# RISK ANALYSIS ENGINE
# =========================

PATTERNS = {
    "self_harm": {
        "keywords": [
            "suicide", "suicidal", "kill myself", "end my life",
            "take my life", "self harm", "self injury", "cut myself",
            "hurt myself", "harm myself", "burn myself",
            "want to die", "wish i was dead", "better off dead",
            "no reason to live", "nothing to live for",
            "tired of living", "done with life",
            "hang myself", "overdose", "jump off"
        ],
        "score_base": 0.9,
        "fuzzy_threshold": 88
    },
    "grooming": {
        "keywords": [
            "dont tell", "our secret", "special friend",
            "mature for your age", "meet up", "send photo",
            "trust me", "come over", "pick you up"
        ],
        "score_base": 0.8,
        "fuzzy_threshold": 85
    },
    "cyberbullying": {
        "keywords": [
            "kill yourself", "kys", "loser", "worthless",
            "nobody likes you", "everyone hates you",
            "ugly", "pathetic", "go die"
        ],
        "score_base": 0.7,
        "fuzzy_threshold": 85
    },
    "drugs": {
        "keywords": [
            "buy weed", "get high", "drug dealer",
            "cocaine", "heroin", "mdma", "meth", "lsd"
        ],
        "score_base": 0.75,
        "fuzzy_threshold": 85
    },
    "sextortion": {
        "keywords": [
            "send nudes", "naked pic", "blackmail",
            "expose you", "leak your pics"
        ],
        "score_base": 0.85,
        "fuzzy_threshold": 85
    },
    "scam": {
        "keywords": [
            "send money", "bitcoin", "gift card",
            "wire transfer", "urgent payment"
        ],
        "score_base": 0.6,
        "fuzzy_threshold": 85
    }
}


def normalize_score(base, matches, text_length):
    """Reduce false positives from long text."""
    density = matches / max(text_length / 20, 1)
    score = base + (density * 0.25)
    return min(score, 1.0)


def match_keyword(keyword, text_lower, words, threshold):
    """Single keyword match (no over-counting)."""

    if keyword in text_lower:
        return True, keyword

    # check words
    for word in words:
        if len(word) >= 3 and fuzz.ratio(keyword, word) >= threshold:
            return True, f"{keyword} (~{word})"

    # check phrase window
    kw_len = len(keyword.split())
    for i in range(len(words) - kw_len + 1):
        phrase = " ".join(words[i:i + kw_len])
        if fuzz.partial_ratio(keyword, phrase) >= threshold:
            return True, f"{keyword} (~{phrase})"

    return False, None


def analyze_risk(text):
    text_lower = text.lower()
    words = text_lower.split()

    detected = []

    for risk_type, data in PATTERNS.items():
        matches = 0
        matched_keywords = set()

        for keyword in data["keywords"]:
            found, match_text = match_keyword(
                keyword,
                text_lower,
                words,
                data["fuzzy_threshold"]
            )

            if found:
                matches += 1
                matched_keywords.add(match_text)

        if matches:
            score = normalize_score(
                data["score_base"],
                matches,
                len(words)
            )

            detected.append({
                "risk_type": risk_type,
                "risk_score": score,
                "matches": matches,
                "keywords": list(matched_keywords)[:3]
            })

    if not detected:
        return {
            "risk_type": "none",
            "risk_level": "safe",
            "risk_score": 0.0,
            "explanation": "No concerning content detected."
        }

    highest = max(detected, key=lambda x: x["risk_score"])
    score = highest["risk_score"]

    if score >= 0.8:
        level = "critical"
    elif score >= 0.6:
        level = "high"
    elif score >= 0.4:
        level = "medium"
    else:
        level = "low"

    explanations = {
        "self_harm": "URGENT: Self-harm indicators detected.",
        "grooming": "Potential grooming behavior detected.",
        "cyberbullying": "Harmful language detected.",
        "drugs": "Drug-related content detected.",
        "sextortion": "Potential sextortion detected.",
        "scam": "Potential financial scam detected."
    }

    return {
        "risk_type": highest["risk_type"],
        "risk_level": level,
        "risk_score": score,
        "explanation": explanations.get(highest["risk_type"], "Risk detected."),
        "matched_keywords": highest["keywords"]
    }


# =========================
# ROUTES
# =========================

@app.route("/")
def index():
    return render_template("setup.html")


@app.route("/child")
def child():
    return render_template("child.html")


@app.route("/parent")
def parent():
    return render_template("parent.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    analysis = analyze_risk(text)

    try:
        with get_db() as conn:
            c = conn.cursor()

            c.execute(
                "SELECT monitoring_enabled, alert_threshold FROM settings WHERE id=1"
            )
            settings = c.fetchone() or (0, 0.6)
            monitoring_enabled, alert_threshold = settings

            if monitoring_enabled and analysis["risk_score"] >= alert_threshold:
                c.execute(
                    """INSERT INTO alerts
                    (timestamp, content, risk_type, risk_level, risk_score, context)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        datetime.now().isoformat(),
                        text[:500],
                        analysis["risk_type"],
                        analysis["risk_level"],
                        analysis["risk_score"],
                        analysis["explanation"]
                    )
                )
    except Exception as e:
        logging.error(f"Database error: {e}")

    return jsonify(analysis)


@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 50")
        rows = c.fetchall()

    alerts = [
        {
            "id": r[0],
            "timestamp": r[1],
            "content": r[2],
            "risk_type": r[3],
            "risk_level": r[4],
            "risk_score": r[5],
            "context": r[6],
        }
        for r in rows
    ]

    return jsonify(alerts)


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    with get_db() as conn:
        c = conn.cursor()

        if request.method == "POST":
            data = request.get_json(silent=True) or {}

            c.execute(
                """UPDATE settings
                   SET parent_consent=?, monitoring_enabled=?, alert_threshold=?
                   WHERE id=1""",
                (
                    data.get("parent_consent", 0),
                    data.get("monitoring_enabled", 0),
                    data.get("alert_threshold", 0.6),
                ),
            )
            return jsonify({"success": True})

        c.execute("SELECT * FROM settings WHERE id=1")
        row = c.fetchone()

    if not row:
        return jsonify({"error": "Settings not found"}), 404

    return jsonify({
        "parent_consent": row[1],
        "monitoring_enabled": row[2],
        "alert_threshold": row[3],
    })


@app.route("/api/stats", methods=["GET"])
def stats():
    with get_db() as conn:
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM alerts")
        total = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM alerts WHERE risk_level='critical'")
        critical = c.fetchone()[0]

        c.execute("SELECT risk_type, COUNT(*) FROM alerts GROUP BY risk_type")
        breakdown = dict(c.fetchall())

    return jsonify({
        "total_alerts": total,
        "critical_alerts": critical,
        "risk_breakdown": breakdown
    })


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
