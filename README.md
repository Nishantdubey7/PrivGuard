## PrivGuard
Overview:

PrivGuard is an AI-powered data redaction and anonymization platform designed to detect and protect Personally Identifiable Information (PII) across text documents, PDFs, images, videos, and audio recordings.

The platform combines Natural Language Processing (NLP), speech processing, and document analysis techniques to automate privacy-preserving workflows while maintaining data utility. It is designed to support privacy compliance requirements such as GDPR and HIPAA.

## Key Features
---
## Text Anonymization
- Automated detection and anonymization of sensitive entities.
- Supports names, email addresses, phone numbers, Aadhaar numbers, PAN numbers, and custom entity types.
## PDF Redaction
- Coordinate-based identification and redaction of sensitive content.
- Preserves document structure and formatting.
## Audio Anonymization
- Speech-to-text processing using WhisperX.
- Timestamp-level identification and redaction of sensitive information.
## Image and Video Privacy Protection
- Detection and anonymization of sensitive information from visual content.
- Utility-Preserving Pseudonymization
- Entity replacement techniques that maintain contextual meaning while protecting privacy.

## 🚀 Running the Project

Follow the steps below to start all modules of **PrivGuard**.

---

### 🎧 Audio Module
```bash
python -m uvicorn app:app --port 5000 --reload
```
- Runs the audio redaction service  
- Accessible at: http://localhost:5000

---

### 🖼️ Image & 🎥 Video Module
```bash
python -m uvicorn fastapiwrapper:app --port 7000 --reload
```
- Handles image and video anonymization  
- Accessible at: http://localhost:7000

---

### 📄 PDF Module
```bash
python -m uvicorn fastapiwrapper:app --port 4000 --reload
```
- Processes and redacts PDF documents  
- Accessible at: http://localhost:4000

---

### 🖥️ Backend (Node.js)
```bash
npm run dev
```
- Runs the main API server  
- Default port: http://localhost:8000

---

### 🌐 Frontend (Next.js)
```bash
npm run dev
```
- Launches the web interface  
- Default port: http://localhost:3000

---

![Python](https://img.shields.io/badge/Python-3.10-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![React](https://img.shields.io/badge/React-Frontend-blue)
![MongoDB](https://img.shields.io/badge/MongoDB-Database-green)


