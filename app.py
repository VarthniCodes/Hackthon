from flask import Flask, request, jsonify, render_template
from transformers import pipeline
from datetime import datetime

app = Flask(__name__)

# ---------------- LOAD AI MODEL ----------------
print("Loading AI model...")
classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli"
)

labels = [
    "online grooming",
    "cyberbullying victim",
    "cyberbullying aggressive behavior",
    "sextortion",
    "self harm",
    "emotional distress",
    "safe conversation"
]

# store only alert metadata (privacy safe)
alerts = []


# ---------------- AI DETECTION ----------------
def analyze_text(text):
    result = classifier(text, labels)

    category = result["labels"][0]
    score = result["scores"][0]

    if score > 0.75:
        risk = "HIGH"
    elif score > 0.5:
        risk = "MEDIUM"
    else:
        risk = "SAFE"

    return risk, category


# ---------------- SAFETY NUDGES ----------------
def get_nudge(category, risk, sender):

    if sender == "child" and category == "self harm":
        return "You may be feeling overwhelmed. Please talk to a trusted adult."

    if sender == "child" and category == "emotional distress":
        return "It seems like you're going through something difficult. Talking to someone you trust can help."

    if sender == "child" and category == "cyberbullying aggressive behavior":
        return "Some messages can hurt more than we realize. Take a moment before sending."

    if sender == "stranger" and category in ["online grooming", "sextortion"]:
        return "If someone asks for secrets or photos, talk to a trusted adult."

    if sender == "stranger" and category == "cyberbullying victim":
        return "That message is not okay. Consider telling a trusted adult."

    if risk == "MEDIUM":
        return "If a conversation makes you uncomfortable, step away and seek help."

    return ""


# ---------------- CHILD DEVICE PAGE ----------------
@app.route("/")
def home():
    return render_template("child.html")


# ---------------- API FOR YOUR UI ----------------
@app.route("/api/analyze", methods=["POST"])
def api_analyze():

    data = request.json
    text = data.get("text", "")
    sender = data.get("sender", "")

    risk, category = analyze_text(text)
    nudge = get_nudge(category, risk, sender)

    # privacy-safe parent alerts (no message stored)
    if sender == "stranger" and risk == "HIGH":
        alerts.append({
            "sender": sender,
            "category": category,
            "risk": risk,
            "time": datetime.now().strftime("%H:%M:%S")
        })

    if sender == "child" and category == "self harm":
        alerts.append({
            "sender": sender,
            "category": category,
            "risk": risk,
            "time": datetime.now().strftime("%H:%M:%S")
        })

    return jsonify({
        "risk_level": risk,
        "category": category,
        "nudge": nudge,
        "explanation": f"{category} detected"
    })


# ---------------- PARENT DASHBOARD ----------------
@app.route("/parent")
def parent():
    return render_template("parent.html", alerts=alerts)


if __name__ == "__main__":
    app.run(debug=True)
