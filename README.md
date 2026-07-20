**Project Name:** OptiFlow — Communication Network Optimization & Monitoring Tool.


* **Short Summary:** A lightweight, automated Linux network traffic shaping system that prioritizes mission-critical emergency traffic (e.g., distress signals, VoIP calls) over best-effort normal traffic on unreliable, low-bandwidth links (such as satellite or maritime connections).


* **Key Highlights:** Built using native Linux tools (`nftables` and `tc`/HTB), Scapy packet sniffing, a Flask API, Firebase cloud telemetry, and a visual Chart.js dashboard wrapped in `pywebview`.



---

### 1. **System Architecture & Key Components**

Include a high-level summary (or diagram) explaining the four core layers:

1. **Networking Backend ("The Engine"):**
* `nftables`: Marks packets arriving on port `9999` with Mark `1` (Emergency) and port `8888` with Mark `2` (Normal).


* `tc`/HTB: Classifies traffic into HTB class `1:10` (Emergency: 7–10 Mbit, Prio 1) and class `1:20` (Normal: 1–3 Mbit baseline, throttled to 512 kbit/1 Mbit during emergencies, Prio 2).




2. **Automation Layer ("The Brain"):**
* `optiflow_automation.py`: A root-privileged Python service using Scapy to monitor live packets, manage state transitions (`THROTTLE` / `RESTORE`), enforce a 3-second emergency timeout, and send 1 Hz telemetry updates.




3. **Data & Cloud Layer:**
* `firebaseService.py` & Firebase Realtime Database: Serves as the system of record storing live telemetry, per-port throughput, and client application signatures.




4. **Presentation Layer ("The Control Room"):**
* `app.py` & `templates/index.html`: A Flask REST API and responsive Chart.js dark-mode dashboard showing system state, active alerts, and live packet/bitrate metrics.


* `gui_launcher.py`: Desktop wrapper using `pywebview` for single-click operation.


* `app.js`: Node.js client-side application signature simulator.





---

### 2. **Prerequisites & Dependencies**

#### System & Linux Utilities

* **OS Requirements:** Ubuntu / Linux environment (or WSL2 with WSLg enabled).


* **Networking Tools:** `iperf3`, `nftables`, `iproute2` (`tc`).



#### Python & System GUI Libraries

```bash
# System dependencies for GTK/pywebview GUI rendering
sudo apt update
sudo apt install -y iperf3 python3-scapy libcairo2-dev libgirepository1.0-dev \
                    python3-dev python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
                    libwebkit2gtk-4.1-dev python3.12-venv
```[cite: 1]

#### Python Packages (`requirements.txt`)
*   `flask`[cite: 1]
*   `pywebview`[cite: 1]
*   `firebase-admin`[cite: 1]
*   `scapy`[cite: 1]

---

### 4. **Installation & Setup Guide**

#### Step 1: Clone Repository & Virtual Environment
```bash
git clone <repository-url>
cd OptiFlow
python3 -m venv venv
source venv/bin/activate
pip install flask pywebview firebase-admin scapy
```[cite: 1]

#### Step 2: Configure System GTK Access (For Desktop GUI)
Edit `venv/pyvenv.cfg` to allow the virtual environment to access system-installed GTK bindings[cite: 1]:
```ini
include-system-site-packages = true
```[cite: 1]

#### Step 3: Firebase Credentials
*   Obtain a `serviceAccountKey.json` from the Firebase Console[cite: 1].
*   Place `serviceAccountKey.json` in the root project directory[cite: 1]. *(Note: Ensure this file is listed in `.gitignore` to prevent credential exposure)*[cite: 1].

---

### 5. **Execution & Usage Instructions**

Detail the key scripts and commands depending on the test configuration (e.g., Stage 3 Demonstration Setup)[cite: 1]:

#### Running the Backend Automation Engine (Server / Operator Side)
Must be run as `root` to apply `nftables` and `tc` kernel hooks[cite: 1]:
```bash
ssh root@68.183.238.154
sudo python3 optiflow_automation.py
```[cite:1]

#### Running the Web Dashboard / Desktop GUI
```bash
# Web Dashboard View
python3 app.py
# Access at http://127.0.0.1:5000 in browser

# Standalone Desktop App (pywebview)
python3 gui_launcher.py
```[cite: 1]

#### Running Client Traffic Generator (Node.js App / iperf3)
```bash
# Node.js Application Signature Simulator (Client Laptop)
node app.js

# Manual Baseline Verification via iperf3
iperf3 -c <server-ip> -p 8888 -t 40                     # Normal lane
iperf3 -c <server-ip> -p 9999 -b 50k -i 3 -t 15          # Emergency burst
```[cite: 1]

---

### 6. **Traffic Mapping & Port Convention**

Include a clear table defining the core traffic classification anchors used across all layers[cite: 1]:

| Port | Traffic Type | HTB Class | Baseline Rate / Ceil | Throttled Rate / Ceil | Scheduling Priority |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **9999** | Emergency Traffic (VoIP, Distress Calls) | `1:10` | 7 Mbit / 10 Mbit | Unchanged (Constant) | Priority 1 (Highest) |
| **8888** | Normal Traffic (Browsing, Streaming) | `1:20` | 1 Mbit / 3 Mbit | 512 kbit / 1 Mbit | Priority 2 |

[cite: 1]

---

### 7. **Known Limitations & WSL2 Considerations**

*   **WSL2 Adapter Isolation:** Virtual adapters in WSL2 isolate `tc` queue shaping from physical host NICs[cite: 1]. Full physical deployment testing requires genuine Linux hosts/cloud servers with public NICs[cite: 1].
*   **Port-Based Classification:** Current identification relies on ports `9999`/`8888` rather than Deep Packet Inspection (DPI) or cryptographic flow signatures[cite: 1].
*   **Read-Only Dashboard:** The web dashboard provides real-time state tracking and statistics but currently lacks direct remote control buttons for manual queue override[cite: 1].

---

### 8. **Repository Directory Layout**
```text
├── app.py                   # Flask Web Server & REST API
├── firebaseService.py       # Firebase Data Retrieval & 30s Caching Layer
├── gui_launcher.py          # Native Desktop Window Wrapper (pywebview)
├── optiflow_automation.py   # Core Backend Engine (Scapy + nftables + tc/HTB)
├── app.js                   # Node.js Client Traffic Simulator
├── templates/
│   └── index.html           # Main Control Dashboard (Chart.js + Bootstrap)
├── serviceAccountKey.json   # Firebase Admin SDK Key (User Provided)
└── README.md                # Documentation File
```[cite: 1]

```
