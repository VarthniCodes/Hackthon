# Neoclaw — AI Child Safety Monitoring Platform

## Overview

Neoclaw is an AI-powered child safety monitoring system that detects harmful interactions in digital conversations and provides real-time interventions.

The system monitors conversation text on a child’s device, detects risks like grooming, bullying, or self-harm, nudges the child with supportive messages, and alerts parents.

The platform is designed with privacy-first monitoring. It does NOT store full conversations — only risk events.

---

## Problem Statement

Children interact online through messaging apps, games, and social platforms where they may face:

- Online grooming
- Cyberbullying
- Sextortion
- Emotional distress
- Harmful influence

Parents currently lack real-time awareness of such risks.

---

## Solution

Neoclaw provides:

- Real-time risk detection
- AI safety nudges for children
- Parent alert dashboard
- Privacy-safe monitoring
- Behavior-aware intervention

---

## Key Features

- AI risk detection engine
- Typo-tolerant message analysis
- Context-aware intervention nudges
- Parent monitoring dashboard
- Event-based storage (no full chat storage)
- Parental consent system

---

## System Architecture

Neoclaw follows a privacy-first, event-based monitoring architecture designed for real-time safety detection and intervention.

### High Level Flow

Child Device → Risk Detection Engine → Alert Service → Parent Dashboard

---

### Architecture Components

#### 1. Child Device Interface
- Captures conversation text events
- Performs initial risk checks
- Displays real-time safety nudges
- Sends risk events to backend
- Does NOT store full conversations

#### 2. Risk Detection Engine
- Keyword detection
- Typo-tolerant fuzzy matching
- Context-aware risk scoring
- Behavior pattern analysis
- Generates intervention actions

#### 3. Alert Service
- Stores risk events only
- Triggers parent alerts
- Maintains monitoring settings
- Supports safety analytics

#### 4. Parent Dashboard
- Displays safety alerts
- Shows intervention actions
- Provides monitoring controls
- Displays detection statistics

---

### Data Flow

1. Message generated on child device
2. Text analyzed for safety risks
3. Risk score calculated
4. Child receives supportive nudge if needed
5. Risk event stored in database
6. Parent receives alert in dashboard

---

### Privacy Design

- No full conversation storage
- Event-based monitoring only
- Parental consent required
- Minimal data retention

---

## Tech Stack

### Backend
- Python
- Flask / FastAPI
- SQLite / PostgreSQL
- RapidFuzz

### Frontend
- HTML / JavaScript (MVP)

---

## Project Structure

backend/ — API and logic  
frontend/ — Parent dashboard UI  
device-agent/ — Device monitoring agent  
risk-engine/ — AI safety detection  
database/ — Schema and migrations  

---

## Privacy & Safety Principles

- No full conversation storage
- Parental consent required
- Event-based monitoring only
- Ethical AI interventions

---

## Application Access

### Child Device Interface
Used to simulate the child's device and monitor conversations.

Live Deployment:  
https://hackthon-czq3.onrender.com/

---

### Parent Dashboard
View safety alerts and intervention actions.

Live Deployment:  
https://hackthon-czq3.onrender.com/parent

---

### Monitoring Setup & Statistics
Configure monitoring settings and view detection statistics.

Live Deployment:  
https://hackthon-czq3.onrender.com/setup

---

## Demo Flow

1. Open child interface
2. Simulate conversation with stranger
3. Risk detected automatically
4. Child receives safety nudge
5. Parent dashboard updates with alert

---

## Local Development Setup

### 1. Clone repository
git clone https://github.com/VarthniCodes/Hackthon.git

### 2. Install dependencies
pip install -r requirements.txt

### 3. Run application
python app.py

### 4. Open browser
http://localhost:5000

---

## Future Roadmap

- Mobile monitoring agent
- AI behavior prediction
- Multi-parent support
- Production cloud deployment
- Compliance certification

---

## License

MIT License
