from flask import Flask, render_template, request
from transformers import pipeline
from datetime import datetime

app = Flask(__name__)

# ---------------- LOAD AI MODEL ----------------
print("Loading AI model... (first run may take time)")
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

# temporary memory only (not saved anywhere)
alerts = []
chat_history = []   # clears when app restarts


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
        risk = "LOW"

    return risk, category


# ---------------- SAFETY NUDGES ----------------
def get_nudge(category, risk, sender):

    if sender == "child" and category == "self harm":
        return "You may be feeling overwhelmed. Talking to a trusted adult can help."

    if sender == "child" and category == "emotional distress":
        return "It seems like you're going through something difficult. Talking to someone you trust can help."

    if sender == "child" and category == "cyberbullying aggressive behavior":
        return "Some messages can hurt more than we realize. Take a moment before sending."

    if sender == "stranger" and category in ["online grooming", "sextortion"]:
        return "If someone asks for secrets or photos, please talk to a trusted adult."

    if sender == "stranger" and category == "cyberbullying victim":
        return "That message is not okay. Consider telling a trusted adult."

    if risk == "MEDIUM":
        return "If a conversation makes you uncomfortable, step away and seek help."

    return ""


# ---------------- CHILD PAGE ----------------
@app.route("/", methods=["GET", "POST"])
def child():

    nudge = ""
    risk = ""
    category = ""

    if request.method == "POST":

        message = request.form["message"]
        sender = request.form["sender"]

        # store temporary chat (for UI only)
        chat_history.append({
            "sender": sender,
            "text": message
        })

        # analyze message
        risk, category = analyze_text(message)
        nudge = get_nudge(category, risk, sender)

        # parent alerts (no message text stored)
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

    return render_template(
        "child.html",
        chat=chat_history,
        nudge=nudge,
        risk=risk,
        category=category
    )


# ---------------- PARENT DASHBOARD ----------------
@app.route("/parent")
def parent():
    return render_template("parent.html", alerts=alerts)


if __name__ == "__main__":
    app.run(debug=True)
