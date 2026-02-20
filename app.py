from flask import Flask, render_template, request, jsonify
from datetime import datetime
import sqlite3
import json
import re

app = Flask(__name__)

# Initialize database
def init_db():
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  content TEXT,
                  risk_type TEXT,
                  risk_level TEXT,
                  risk_score REAL,
                  context TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (id INTEGER PRIMARY KEY,
                  parent_consent INTEGER,
                  monitoring_enabled INTEGER,
                  alert_threshold REAL)''')
    c.execute('SELECT * FROM settings WHERE id=1')
    if not c.fetchone():
        c.execute('INSERT INTO settings VALUES (1, 0, 0, 0.6)')
    conn.commit()
    conn.close()

init_db()

def analyze_risk(text):
    text_lower = text.lower()
    patterns = {
        'grooming': {
            'keywords': ['secret', 'dont tell', 'special friend', 'meet up', 'send photo', 'video call alone', 
                        'age', 'how old', 'mature for your age', 'trust me', 'our secret'],
            'score_base': 0.8
        },
        'cyberbullying': {
            'keywords': ['kill yourself', 'nobody likes you', 'loser', 'fat', 'ugly', 'worthless', 
                        'die', 'hate you', 'stupid', 'dumb', 'pathetic', 'freak'],
            'score_base': 0.7
        },
        'self_harm': {
            'keywords': ['cut myself', 'want to die', 'suicide', 'kill myself', 'end it all', 
                        'hurting myself', 'self harm', 'not worth living', 'better off dead'],
            'score_base': 0.9
        },
        'drugs': {
            'keywords': ['buy weed', 'get high', 'want pills', 'drug dealer', 'cocaine', 'heroin',
                        'where to buy', 'how much for', 'mdma', 'vape', 'cigarettes'],
            'score_base': 0.75
        },
        'sextortion': {
            'keywords': ['send nudes', 'naked pic', 'ill share', 'expose you', 'blackmail',
                        'nude photo', 'threaten', 'post online', 'embarrassing photo'],
            'score_base': 0.85
        },
        'scam': {
            'keywords': ['send money', 'paypal', 'venmo', 'cash app', 'gift card', 'bitcoin',
                        'wire transfer', 'bank account', 'urgent payment', 'limited time'],
            'score_base': 0.6
        }
    }
    
    detected_risks = []
    for risk_type, data in patterns.items():
        matches = sum(1 for keyword in data['keywords'] if keyword in text_lower)
        if matches > 0:
            risk_score = min(data['score_base'] + (matches * 0.05), 1.0)
            detected_risks.append({'risk_type': risk_type, 'risk_score': risk_score, 'matches': matches})
    
    if not detected_risks:
        return {'risk_type': 'none', 'risk_level': 'safe', 'risk_score': 0.0, 'explanation': 'No concerning content detected.'}
    
    highest_risk = max(detected_risks, key=lambda x: x['risk_score'])
    score = highest_risk['risk_score']
    if score >= 0.8:
        risk_level = 'critical'
    elif score >= 0.6:
        risk_level = 'high'
    elif score >= 0.4:
        risk_level = 'medium'
    else:
        risk_level = 'low'
    
    explanations = {
        'grooming': 'Potential grooming behavior detected.',
        'cyberbullying': 'Harmful language detected.',
        'self_harm': 'URGENT: Self-harm detected.',
        'drugs': 'Drug-related content detected.',
        'sextortion': 'Potential sextortion detected.',
        'scam': 'Potential scam detected.'
    }
    
    return {
        'risk_type': highest_risk['risk_type'],
        'risk_level': risk_level,
        'risk_score': highest_risk['risk_score'],
        'explanation': explanations.get(highest_risk['risk_type'], 'Risk detected.')
    }

@app.route('/')
def index():
    return render_template('setup.html')

@app.route('/child')
def child():
    return render_template('child.html')

@app.route('/parent')
def parent():
    return render_template('parent.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.json
    text = data.get('text', '')
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    analysis = analyze_risk(text)
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    c.execute('SELECT monitoring_enabled, alert_threshold FROM settings WHERE id=1')
    settings = c.fetchone()
    monitoring_enabled, alert_threshold = settings if settings else (0, 0.6)
    if monitoring_enabled and analysis['risk_score'] >= alert_threshold:
        timestamp = datetime.now().isoformat()
        c.execute('''INSERT INTO alerts (timestamp, content, risk_type, risk_level, risk_score, context)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (timestamp, text[:500], analysis['risk_type'], analysis['risk_level'], 
                   analysis['risk_score'], analysis['explanation']))
        conn.commit()
    conn.close()
    return jsonify(analysis)

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    c.execute('SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 50')
    rows = c.fetchall()
    conn.close()
    alerts = []
    for row in rows:
        alerts.append({'id': row[0], 'timestamp': row[1], 'content': row[2], 'risk_type': row[3], 'risk_level': row[4], 'risk_score': row[5], 'context': row[6]})
    return jsonify(alerts)

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute('''UPDATE settings SET parent_consent=?, monitoring_enabled=?, alert_threshold=? WHERE id=1''',
                  (data.get('parent_consent', 0), data.get('monitoring_enabled', 0), data.get('alert_threshold', 0.6)))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    else:
        c.execute('SELECT * FROM settings WHERE id=1')
        row = c.fetchone()
        conn.close()
        if row:
            return jsonify({'parent_consent': row[1], 'monitoring_enabled': row[2], 'alert_threshold': row[3]})
        return jsonify({'error': 'Settings not found'}), 404

@app.route('/api/stats', methods=['GET'])
def stats():
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM alerts')
    total_alerts = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM alerts WHERE risk_level="critical"')
    critical_alerts = c.fetchone()[0]
    c.execute('SELECT risk_type, COUNT(*) FROM alerts GROUP BY risk_type')
    risk_breakdown = dict(c.fetchall())
    conn.close()
    return jsonify({'total_alerts': total_alerts, 'critical_alerts': critical_alerts, 'risk_breakdown': risk_breakdown})

if __name__ == '__main__':
    app.run(debug=True, port=5000)