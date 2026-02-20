from flask import Flask, request, jsonify, render_template
from rapidfuzz import fuzz
from textblob import TextBlob
import sqlite3
from datetime import datetime

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
    
    c.execute('SELECT * FROM settings WHERE id=1')
    if not c.fetchone():
        c.execute('INSERT INTO settings VALUES (1, 0, 0, 0.6)')
    
    conn.commit()
    conn.close()

init_db()

# =====================================================
# KEYWORD PATTERNS
# =====================================================

PATTERNS = {
    "self_harm": [
        "suicide", "suicidal", "kill myself", "want to die", "wanna die",
        "end my life", "take my life", "cut myself", "hurt myself", 
        "harm myself", "self harm", "self-harm", "selfharm",
        "self injury", "self-injury", "selfinjury",
        "self inflict", "self-inflict", "selfinflict",
        "self mutilat", "self-mutilat", "selfmutilat",
        "self destruct", "self-destruct", "selfdestruct",
        "better off dead", "not worth living", "no reason to live",
        "cant go on", "can't go on", "cant take it", "can't take it",
        "tired of living", "done with life", "nobody will miss me",
        "overdose", "pills to die", "jump off", "hang myself"
    ],
    "grooming": [
        "dont tell", "don't tell", "our secret", "keep this secret",
        "keep this between us", "meet alone", "send photo",
        "mature for your age", "special friend", "trust me",
        "come over", "pick you up", "video call alone"
    ],
    "cyberbullying": [
        "worthless", "loser", "ugly", "kill yourself", "kys",
        "you are nothing", "stupid", "idiot", "nobody likes you",
        "die", "hate you", "pathetic", "freak", "waste of space"
    ],
    "sextortion": [
        "send nudes", "naked pic", "leak your pics", "expose you",
        "blackmail", "nude photo", "threaten", "post online"
    ],
    "drugs": [
        "buy weed", "get high", "want pills", "drug dealer",
        "cocaine", "heroin", "mdma", "smoke weed", "get drugs"
    ],
    "scam": [
        "send money", "bitcoin", "gift card", "paypal", "venmo",
        "cash app", "wire transfer", "urgent payment", "limited time"
    ]
}

# =====================================================
# SENTIMENT ANALYSIS (AI LAYER)
# =====================================================

def sentiment_analysis(text):
    """
    Analyze emotional tone using TextBlob.
    Returns a boost score based on negativity.
    """
    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity  # Range: -1 (negative) to +1 (positive)
        subjectivity = blob.sentiment.subjectivity  # Range: 0 (objective) to 1 (subjective)
        
        # Very negative + highly subjective = potential distress
        if polarity < -0.5 and subjectivity > 0.5:
            return 0.3  # High boost
        elif polarity < -0.3:
            return 0.2  # Medium boost
        elif polarity < 0:
            return 0.1  # Small boost
        
        return 0
    except:
        return 0

# =====================================================
# DETECTION ENGINE (Hybrid: Keywords + Fuzzy + AI)
# =====================================================

def analyze_risk(text):
    text_lower = text.lower()
    detected_risks = []
    
    # Get sentiment boost
    sentiment_boost = sentiment_analysis(text)
    
    for risk_type, keywords in PATTERNS.items():
        matches = 0
        matched_keywords = []
        
        for keyword in keywords:
            # Method 1: Exact match
            if keyword in text_lower:
                matches += 1
                matched_keywords.append(keyword)
            else:
                # Method 2: Fuzzy match
                words = text_lower.split()
                for word in words:
                    if len(word) >= 3 and fuzz.ratio(keyword, word) >= 85:
                        matches += 0.8
                        matched_keywords.append(f"{keyword} (~{word})")
                        break
        
        if matches > 0:
            base_scores = {
                "self_harm": 0.9,
                "grooming": 0.8,
                "sextortion": 0.85,
                "cyberbullying": 0.7,
                "drugs": 0.75,
                "scam": 0.6
            }
            
            # Calculate base score + sentiment boost
            score = min(
                base_scores.get(risk_type, 0.6) + (matches * 0.03) + sentiment_boost,
                1.0
            )
            
            detected_risks.append({
                "risk_type": risk_type,
                "risk_score": score,
                "matched_keywords": matched_keywords[:3],
                "sentiment_boost": sentiment_boost
            })
    
    # If no keyword match but strong negative sentiment, flag as potential distress
    if not detected_risks and sentiment_boost >= 0.2:
        detected_risks.append({
            "risk_type": "self_harm",
            "risk_score": 0.5 + sentiment_boost,
            "matched_keywords": ["emotional distress detected"],
            "sentiment_boost": sentiment_boost
        })
    
    if not detected_risks:
        return {
            "risk_type": "none",
            "risk_score": 0.0,
            "risk_level": "safe",
            "explanation": "No concerning content detected."
        }
    
    best = max(detected_risks, key=lambda x: x["risk_score"])
    score = best["risk_score"]
    
    if score >= 0.8:
        risk_level = "critical"
    elif score >= 0.6:
        risk_level = "high"
    elif score >= 0.4:
        risk_level = "medium"
    else:
        risk_level = "safe"
    
    explanations = {
        "grooming": "Potential grooming behavior detected.",
        "cyberbullying": "Harmful language detected.",
        "self_harm": "URGENT: Self-harm indicators detected.",
        "drugs": "Drug-related content detected.",
        "sextortion": "Potential sextortion detected.",
        "scam": "Potential scam detected."
    }
    
    explanation = explanations.get(best["risk_type"], "Risk detected.")
    if best.get("sentiment_boost", 0) > 0.1:
        explanation += f" (Negative emotional tone detected)"
    
    return {
        "risk_type": best["risk_type"],
        "risk_score": score,
        "risk_level": risk_level,
        "explanation": explanation
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
            "It sounds like you're going through something difficult. "
            "You don't have to handle this alone. Please talk to a trusted adult."
        )
        action["parent_alert"] = True
    
    elif sender == "stranger" and risk_type == "cyberbullying":
        action["child_nudge"] = (
            "The way someone is speaking to you isn't okay. "
            "You deserve respect. Consider telling a trusted adult."
        )
        action["parent_alert"] = True
    
    elif sender == "child" and risk_type == "cyberbullying":
        action["child_nudge"] = (
            "Some messages can hurt more than we realize. "
            "Take a moment before sending messages."
        )
    
    elif sender == "stranger" and risk_type in ["grooming", "sextortion"]:
        action["child_nudge"] = (
            "You should never keep secrets from trusted adults. "
            "Please talk to a parent immediately."
        )
        action["parent_alert"] = True
    
    elif sender == "child" and level == "medium":
        action["child_nudge"] = (
            "It seems you might be feeling upset. Talking to someone you trust can help."
        )
    
    return action

# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def home():
    return render_template("setup.html")

@app.route("/child")
def child():
    return render_template("child.html")

@app.route("/parent")
def parent():
    return render_template("parent.html")

@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.json
    text = data.get("text", "")
    sender = data.get("sender", "child")
    
    if not text:
        return jsonify({"error": "No text provided"}), 400
    
    risk = analyze_risk(text)
    action = decide_action(risk, sender)
    
    if action["parent_alert"] or risk["risk_score"] >= 0.6:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO alerts (timestamp, content, sender, risk_type, risk_score, context)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            text[:500],
            sender,
            risk["risk_type"],
            risk["risk_score"],
            risk["explanation"]
        ))
        conn.commit()
        conn.close()
    
    return jsonify({
        **risk,
        **action
    })

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
            "risk_score": r[5],
            "context": r[6] if len(r) > 6 else ""
        }
        for r in rows
    ])

@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    conn = get_db()
    c = conn.cursor()
    if request.method == "POST":
        data = request.json
        c.execute("""
            UPDATE settings 
            SET parent_consent=?, monitoring_enabled=?, alert_threshold=? 
            WHERE id=1
        """, (
            data.get("parent_consent", 0),
            data.get("monitoring_enabled", 0),
            data.get("alert_threshold", 0.6)
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    c.execute("SELECT * FROM settings WHERE id=1")
    row = c.fetchone()
    conn.close()
    return jsonify({
        "parent_consent": row[1],
        "monitoring_enabled": row[2],
        "alert_threshold": row[3]
    }) if row else jsonify({"error": "Not found"}), 404

@app.route("/api/stats")
def stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM alerts")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM alerts WHERE risk_score >= 0.8")
    critical = c.fetchone()[0]
    c.execute("SELECT risk_type, COUNT(*) FROM alerts GROUP BY risk_type")
    breakdown = dict(c.fetchall())
    conn.close()
    return jsonify({
        "total_alerts": total,
        "critical_alerts": critical,
        "risk_breakdown": breakdown
    })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
