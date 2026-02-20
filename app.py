from flask import Flask, render_template, request, jsonify
from datetime import datetime
import sqlite3
from fuzzywuzzy import fuzz

app = Flask(__name__)

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
    
    # Enhanced patterns with comprehensive keyword lists
    patterns = {
        'self_harm': {
            'keywords': [
                # Direct self-harm terms
                'suicide', 'suicidal', 'kill myself', 'killing myself',
                'end my life', 'take my life', 'taking my life',
                
                # Self-injury terms
                'self harm', 'self-harm', 'selfharm',
                'self injury', 'self-injury', 'selfinjury',
                'self inflict', 'self-inflict', 'selfinflict',
                'self mutilat', 'self-mutilat', 'selfmutilat',
                'self destruct', 'self-destruct', 'selfdestruct',
                
                # Desire to die
                'want to die', 'wanna die', 'want death', 
                'wish i was dead', 'wish i were dead', 'wish i died',
                'hope i die', 'better off dead', 'world without me',
                
                # Hopelessness phrases
                'no reason to live', 'not worth living', 'life is not worth',
                'nothing to live for', "can't go on", 'cant go on',
                "can't take it", 'cant take it', "can't do this",
                'give up on life', 'giving up on life',
                
                # Self-harm actions
                'cut myself', 'cutting myself', 'cut my',
                'hurt myself', 'hurting myself', 'hurt my',
                'harm myself', 'harming myself', 'harm my',
                'burn myself', 'burning myself',
                'hit myself', 'hitting myself',
                'scratch myself', 'scratching myself',
                
                # Ending life phrases
                'end it all', 'end things', 'end everything',
                'end my life', 'ending my life',
                'finish it', 'finish everything',
                
                # Methods (specific but important)
                'hang myself', 'hanging myself',
                'jump off', 'jumping off',
                'overdose', 'overdosing',
                'slit my wrist', 'cut my wrist',
                'pills to die', 'take pills',
                
                # Indirect expressions
                'goodbye world', 'goodbye cruel world',
                'nobody will miss me', 'better without me',
                'tired of living', 'done with life'
            ],
            'score_base': 0.9,
            'fuzzy_threshold': 85  # 85% similarity required
        },
        'grooming': {
            'keywords': ['secret', 'dont tell', "don't tell", 'special friend', 'meet up', 
                        'send photo', 'video call alone', 'age', 'how old', 
                        'mature for your age', 'trust me', 'our secret', 'our little secret',
                        'come over', 'pick you up', 'special relationship'],
            'score_base': 0.8,
            'fuzzy_threshold': 85
        },
        'cyberbullying': {
            'keywords': ['kill yourself', 'kys', 'nobody likes you', 'loser', 'fat', 'ugly', 
                        'worthless', 'die', 'hate you', 'stupid', 'dumb', 'pathetic', 'freak',
                        'waste of space', 'go die', 'nobody cares', 'everyone hates you'],
            'score_base': 0.7,
            'fuzzy_threshold': 80
        },
        'drugs': {
            'keywords': ['buy weed', 'get high', 'want pills', 'drug dealer', 'cocaine', 'heroin',
                        'where to buy', 'how much for', 'mdma', 'vape', 'cigarettes', 'smoke weed',
                        'get drugs', 'selling drugs', 'marijuana', 'meth', 'acid', 'lsd'],
            'score_base': 0.75,
            'fuzzy_threshold': 85
        },
        'sextortion': {
            'keywords': ['send nudes', 'naked pic', "i'll share", 'ill share', 'expose you', 'blackmail',
                        'nude photo', 'threaten', 'post online', 'embarrassing photo', 'explicit photo',
                        'share your photos', 'leak your pics'],
            'score_base': 0.85,
            'fuzzy_threshold': 85
        },
        'scam': {
            'keywords': ['send money', 'paypal', 'venmo', 'cash app', 'gift card', 'bitcoin',
                        'wire transfer', 'bank account', 'urgent payment', 'limited time',
                        'act now', 'exclusive offer', 'send cash', 'credit card'],
            'score_base': 0.6,
            'fuzzy_threshold': 85
        }
    }
    
    detected_risks = []
    
    for risk_type, data in patterns.items():
        matches = 0
        matched_keywords = []
        fuzzy_threshold = data.get('fuzzy_threshold', 85)
        
        for keyword in data['keywords']:
            # Method 1: Exact substring match (fastest)
            if keyword in text_lower:
                matches += 1
                matched_keywords.append(keyword)
            else:
                # Method 2: Fuzzy matching for variations
                # Split text into words and phrases to check against keyword
                words = text_lower.split()
                
                # Check individual words
                for word in words:
                    if len(word) >= 3 and fuzz.ratio(keyword, word) >= fuzzy_threshold:
                        matches += 0.8  # Slightly lower weight for fuzzy matches
                        matched_keywords.append(f"{keyword} (~{word})")
                        break
                
                # Check phrases (sliding window)
                keyword_word_count = len(keyword.split())
                for i in range(len(words) - keyword_word_count + 1):
                    phrase = ' '.join(words[i:i + keyword_word_count])
                    if fuzz.partial_ratio(keyword, phrase) >= fuzzy_threshold:
                        matches += 0.9  # Higher weight for phrase matches
                        matched_keywords.append(f"{keyword} (~{phrase})")
                        break
        
        if matches > 0:
            # Calculate risk score (higher for multiple matches)
            risk_score = min(data['score_base'] + (matches * 0.03), 1.0)
            detected_risks.append({
                'risk_type': risk_type, 
                'risk_score': risk_score, 
                'matches': matches,
                'keywords': matched_keywords[:3]  # Store first 3 matched keywords
            })
    
    if not detected_risks:
        return {
            'risk_type': 'none', 
            'risk_level': 'safe', 
            'risk_score': 0.0, 
            'explanation': 'No concerning content detected.'
        }
    
    # Get highest risk
    highest_risk = max(detected_risks, key=lambda x: x['risk_score'])
    score = highest_risk['risk_score']
    
    # Determine risk level
    if score >= 0.8:
        risk_level = 'critical'
    elif score >= 0.6:
        risk_level = 'high'
    elif score >= 0.4:
        risk_level = 'medium'
    else:
        risk_level = 'low'
    
    # Enhanced explanations
    explanations = {
        'grooming': 'Potential grooming behavior detected. This conversation may contain predatory language.',
        'cyberbullying': 'Harmful language detected. This message contains bullying or threatening content.',
        'self_harm': 'URGENT: Self-harm indicators detected. Immediate attention recommended.',
        'drugs': 'Drug-related content detected. Conversation may involve illegal substances.',
        'sextortion': 'Potential sextortion detected. This appears to involve coercion or blackmail.',
        'scam': 'Potential scam detected. This message shows signs of financial fraud.'
    }
    
    return {
        'risk_type': highest_risk['risk_type'],
        'risk_level': risk_level,
        'risk_score': highest_risk['risk_score'],
        'explanation': explanations.get(highest_risk['risk_type'], 'Risk detected.'),
        'matched_keywords': highest_risk.get('keywords', [])
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
    alerts = [{'id': r[0], 'timestamp': r[1], 'content': r[2], 'risk_type': r[3], 'risk_level': r[4], 'risk_score': r[5], 'context': r[6]} for r in rows]
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
    c.execute('SELECT * FROM settings WHERE id=1')
    row = c.fetchone()
    conn.close()
    return jsonify({'parent_consent': row[1], 'monitoring_enabled': row[2], 'alert_threshold': row[3]}) if row else jsonify({'error': 'Settings not found'}), 404

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
    app.run(host='0.0.0.0', port=5000)
