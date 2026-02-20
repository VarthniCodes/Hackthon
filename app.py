from flask import Flask, render_template, request, jsonify
from datetime import datetime
import sqlite3

app = Flask(__name__)
DB_NAME = "safety.db"


# =========================
# DATABASE
# =========================

def get_db():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_db()
    c = conn.cursor()

    # alerts table
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

    # settings table
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
        c.execute("INSERT INTO settings VALUES (1,0,0,0.6)")

    conn.commit()
    conn.close()


init_db()


# =========================
# INTERVENTION NUDGES
# =========================

NUDGE_MESSAGES = {

    "self_harm": {
        "critical": "It sounds like you're going through something very painful. Please talk to a trusted adult immediately. You matter more than you know.",
        "high": "I noticed you might be feeling overwhelmed. Talking to a trusted adult can really help."
    },

    # stranger bullying child
    "cyberbullying_victim": {
        "high": "The way someone is speaking to you isn’t okay. You deserve respect. Consider telling a trusted adult."
    },

    # child bullying others
    "cyberbullying_aggressor": {
        "high": "Some messages can hurt others. Taking a moment before sending can help. If you're upset, talking to someone you trust may help more."
    },

    "grooming": {
        "high": "When someone asks you to keep secrets or share personal photos, that's a warning sign. Please talk to a trusted adult."
    },

    "sextortion": {
        "high": "You should never feel pressured to share personal photos. Please talk to a trusted adult immediately."
    },

    "soft": "If any conversation makes you uncomfortable, it's always okay to talk to a trusted adult."
}


def get_nudge(risk_type, risk_level, sender=None):

    # special cyberbullying logic
    if risk_type == "cyberbullying":
        if sender == "stranger":
            return NUDGE_MESSAGES["cyberbullying_victim"].get(risk_level)
        if sender == "child":
            return NUDGE_MESSAGES["cyberbullying_aggressor"].get(risk_level)

    if risk_type in NUDGE_MESSAGES:
        return NUDGE_MESSAGES[risk_type].get(risk_level)

    if risk_level in ["medium", "low"]:
        return NUDGE_MESSAGES["soft"]

    return None


# =========================
# RISK DETECTION
# =========================

PATTERNS = {
    "self_harm": ["suicide","kill myself","end my life","cut myself","want to die","better off dead"],
    "grooming": ["dont tell","our secret","keep this secret","send photo","meet alone","mature for your age"],
    "cyberbullying": ["kill yourself","loser","worthless","ugly","nobody likes you"],
    "sextortion": ["send nudes","naked pic","blackmail","leak your pics"],
    "drugs": ["buy weed","cocaine","heroin","mdma"],
    "scam": ["send money","bitcoin","gift card"]
}


def analyze_risk(text):
    text_lower = text.lower()

    detected = []

    for risk_type, keywords in PATTERNS.items():
        matches = sum(1 for k in keywords if k in text_lower)

        if matches:
            score = min(0.5 + matches * 0.1, 1.0)
            detected.append({"risk_type": risk_type, "score": score})

    if not detected:
        return {
            "risk_type": "none",
            "risk_level": "safe",
            "risk_score": 0,
            "explanation": "No concerning content detected."
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

    return {
        "risk_type": highest["risk_type"],
        "risk_level": level,
        "risk_score": score,
        "explanation": f"{highest['risk_type']} risk detected"
    }


# =========================
# ROUTES
# =========================

@app.route("/")
def index():
    # show consent first
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT parent_consent FROM settings WHERE id=1")
    row = c.fetchone()
    conn.close()

    consent = row[0] if row else 0

    if not consent:
        return render_template("consent.html")

    return render_template("child.html")


@app.route("/parent")
def parent_dashboard():
    return render_template("parent.html")


@app.route("/setup")
def setup_page():
    return render_template("setup.html")


@app.route("/api/consent", methods=["POST"])
def give_consent():
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE settings SET parent_consent=1, monitoring_enabled=1 WHERE id=1")
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.json
    text = data.get("text", "")
    sender = data.get("sender", "unknown")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    analysis = analyze_risk(text)

    # choose correct nudge based on sender
    nudge = get_nudge(analysis["risk_type"], analysis["risk_level"], sender)
    analysis["nudge"] = nudge
    analysis["sender"] = sender

    HIGH_RISK = ["grooming","sextortion","self_harm","cyberbullying"]

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT monitoring_enabled, alert_threshold FROM settings WHERE id=1")
    settings = c.fetchone() or (1, 0.6)
    monitoring_enabled, threshold = settings

    if analysis["risk_type"] in HIGH_RISK or (monitoring_enabled and analysis["risk_score"] >= threshold):
        c.execute("""
            INSERT INTO alerts
            (timestamp, content, sender, risk_type, risk_level, risk_score, context, nudge)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            text[:500],
            sender,
            analysis["risk_type"],
            analysis["risk_level"],
            analysis["risk_score"],
            analysis["explanation"],
            analysis["nudge"]
        ))
        conn.commit()

    conn.close()
    return jsonify(analysis)


@app.route("/api/alerts")
def get_alerts():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()

    alerts = [{
        "id": r[0],
        "timestamp": r[1],
        "content": r[2],
        "sender": r[3],
        "risk_type": r[4],
        "risk_level": r[5],
        "risk_score": r[6],
        "context": r[7],
        "nudge": r[8]
    } for r in rows]

    return jsonify(alerts)


@app.route("/api/settings", methods=["GET","POST"])
def settings():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        data = request.json
        c.execute("""
        UPDATE settings SET parent_consent=?, monitoring_enabled=?, alert_threshold=? WHERE id=1
        """, (
            data.get("parent_consent",1),
            data.get("monitoring_enabled",1),
            data.get("alert_threshold",0.6)
        ))
        conn.commit()
        conn.close()
        return jsonify({"success":True})

    c.execute("SELECT * FROM settings WHERE id=1")
    row = c.fetchone()
    conn.close()

    return jsonify({
        "parent_consent":row[1],
        "monitoring_enabled":row[2],
        "alert_threshold":row[3]
    })


@app.route("/api/stats")
def stats():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM alerts")
    total = c.fetchone()[0]

    c.execute("SELECT risk_type, COUNT(*) FROM alerts GROUP BY risk_type")
    breakdown = dict(c.fetchall())

    conn.close()

    return jsonify({
        "total_alerts": total,
        "risk_breakdown": breakdown
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
