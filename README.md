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


