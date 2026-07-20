#!/usr/bin/env python3
"""
================================================================================
                OPTIFLOW AUTOMATION LAYER WITH FIREBASE (MEMBER 3)
================================================================================
Target Environment : WSL2 Ubuntu Network Namespaces (router-ns)
Monitored Interface: veth-r2
Emergency Target   : UDP/TCP Port 9999 → nftables mark 1 → TC Class 1:10
Normal/Capped Target: UDP/TCP Port 8888 → nftables mark 2 → TC Class 1:20

Mark-Based Architecture:
  - classify chain stamps mark 1 or mark 2 at prerouting
  - forward chain uses marks (not ports) to allow/drop
  - TC filters use marks to route into class 1:10 or 1:20
  - Python reads marks via port detection and drives TC dynamically
================================================================================
"""

import os
import sys
import time
import subprocess
import threading
import requests
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from scapy.all import sniff, IP, UDP, TCP

# ==============================================================================
# 1. NETWORK TOPOLOGY CONFIGURATION
# ==============================================================================
TARGET_INTERFACE   = "eth0"
EMERGENCY_PORT     = 9999          # Port 9999 → nftables mark 1 → class 1:10
NORMAL_PORT        = 8888          # Port 8888 → nftables mark 2 → class 1:20
CLASS_ID_EMERGENCY = "1:10"        # Emergency lane TC class
CLASS_ID_NORMAL    = "1:20"        # Normal lane TC class

# Emergency class rates (never changed by script — always guaranteed)
EMERGENCY_RATE     = "7mbit"
EMERGENCY_CEIL     = "10mbit"

# Normal class rates — dynamic, changed by script on emergency detection
BASELINE_RATE      = "1mbit"       # ✅ guaranteed rate for 1:20
BASELINE_CEIL      = "3mbit"       # ✅ max ceiling for 1:20
THROTTLED_RATE     = "512kbit"     # emergency active: squeeze 1:20
THROTTLED_CEIL     = "1mbit"       # strict upper ceil during emergency

# Local Dashboard API (Member 4 Integration)
FLASK_METRICS_URL  = "http://127.0.0.1:5000"

# ==============================================================================
# 2. FIREBASE CLOUD INITIALIZATION
# ==============================================================================
FIREBASE_KEY_PATH     = "serviceAccountKey.json"
FIREBASE_DATABASE_URL = 'https://itpproject-2026-default-rtdb.asia-southeast1.firebasedatabase.app/'

try:
    if os.path.exists(FIREBASE_KEY_PATH):
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})
        db_root = db.reference('/')
        firebase_online = True
        print("[+] Firebase Cloud SDK successfully initialized.")
    else:
        firebase_online = False
        print(f"[-] Warning: '{FIREBASE_KEY_PATH}' not found. Cloud logging disabled.",
              file=sys.stderr)
except Exception as e:
    firebase_online = False
    print(f"[-] Firebase Initialization Failed: {e}", file=sys.stderr)

# ==============================================================================
# 3. RUNTIME STATE & METRIC TRACKING
# ==============================================================================
is_emergency_active = False
total_packets       = 0
emergency_packets   = 0
normal_packets      = 0
total_bytes         = 0
dropped_packets     = 0   # tracked via nftables log counter

metrics_lock = threading.Lock()

# Watchdog timeout tracking variables
last_emergency_seen = 0.0
EMERGENCY_TIMEOUT   = 3.0  # Seconds to wait for silence before unthrottling

# ==============================================================================
# 4. NFTABLES MARK-BASED FIREWALL SETUP (UPDATED FOR HOST LAYER ENTRY)
# ==============================================================================
def setup_nftables():
    """
    Builds the full nftables ruleset using marks as the single source of truth.

    classify chain (prerouting):
      - port 9999 → mark 1  (emergency)
      - port 8888 → mark 2  (normal)

    input chain:
      - mark 1 → accept     (emergency packets allowed)
      - mark 2 → accept     (normal packets allowed)
      - established/related → accept  (return traffic)
      - rate-limited log + drop everything else
    """
    print("[*] Setting up nftables mark-based firewall...")

    commands = [
        # Create table
        "sudo nft add table ip optiflow",

        # ── classify chain: stamp marks at prerouting ──
        "sudo nft add chain ip optiflow classify '{ type filter hook prerouting priority 0; }'",

        # Mark emergency packets (port 9999) → mark 1
        f"sudo nft add rule ip optiflow classify tcp dport {EMERGENCY_PORT} meta mark set 1",

        # Mark normal packets (port 8888) → mark 2
        f"sudo nft add rule ip optiflow classify tcp dport {NORMAL_PORT} meta mark set 2",

        # ── input chain: mark drives allow/drop decisions for local delivery ──
        "sudo nft add chain ip optiflow input '{ type filter hook input priority 0; policy drop; }'",

        # Allow emergency marked packets (mark 1)
        "sudo nft add rule ip optiflow input meta mark 1 accept",

        # Allow normal marked packets (mark 2)
        "sudo nft add rule ip optiflow input meta mark 2 accept",

        # Allow established return traffic
        "sudo nft add rule ip optiflow input ct state established,related accept",

        # Block ICMP flood — allow max 5 pings/sec, drop the rest
        "sudo nft add rule ip optiflow input icmp type echo-request limit rate 5/second accept",
        "sudo nft add rule ip optiflow input icmp type echo-request drop",

        # Rate limit new TCP connections — max 10/sec per source IP
        "sudo nft add rule ip optiflow input tcp flags syn ct state new limit rate 10/second burst 20 packets accept",

        # Log and drop everything else
        "sudo nft add rule ip optiflow input limit rate 5/minute log prefix \"OPTIFLOW-DROP: \" drop",
    ]

    for cmd in commands:
        try:
            subprocess.run(cmd, shell=True, check=True)
        except subprocess.CalledProcessError:
            pass

    print("[+] nftables mark-based firewall rules active.")
    print("    mark 1 (port 9999) → accept → TC class 1:10")
    print("    mark 2 (port 8888) → accept → TC class 1:20")
    print("    everything else    → log + drop")


def verify_nftables():
    """Print the full nftables ruleset so you can confirm marks are set."""
    print("\n[*] Current nftables ruleset:")
    subprocess.run("sudo nft list ruleset", shell=True)

# ==============================================================================
# 5. TC CLASS SETUP (MARK-BASED FILTERS) (UPDATED FOR HOST LAYER ENTRY)
# ==============================================================================
def setup_tc():
    """
    Rebuilds TC qdisc, classes, and mark-based filters on the server's public interface.
    Uses nftables marks (fwmark) instead of port matching so TC and
    nftables share the same classification source.
    """
    print("[*] Setting up TC HTB qdisc and mark-based filters...")

    commands = [
        # Clear existing qdisc
        f"sudo tc qdisc del dev {TARGET_INTERFACE} root 2>/dev/null || true",

        # Root HTB qdisc
        f"sudo tc qdisc add dev {TARGET_INTERFACE} root handle 1: htb default 20",

        # Class 1:10 — emergency lane (7mbit guaranteed, 10mbit ceiling, prio 1)
        f"sudo tc class add dev {TARGET_INTERFACE} parent 1: classid 1:10 htb "
        f"rate {EMERGENCY_RATE} ceil {EMERGENCY_CEIL} "
        f"burst 1600b cburst 1600b prio 1",

        # Class 1:20 — normal lane (1mbit guaranteed, 3mbit ceiling, prio 2)
        f"sudo tc class add dev {TARGET_INTERFACE} parent 1: classid 1:20 htb "
        f"rate {BASELINE_RATE} ceil {BASELINE_CEIL} "
        f"burst 1600b cburst 1600b prio 2",

        # Filter: fwmark 1 → class 1:10 (emergency)
        f"sudo tc filter add dev {TARGET_INTERFACE} protocol ip parent 1: prio 1 handle 1 fw flowid 1:10",

        # Filter: fwmark 2 → class 1:20 (normal)
        f"sudo tc filter add dev {TARGET_INTERFACE} protocol ip parent 1: prio 2 handle 2 fw flowid 1:20",
    ]

    for cmd in commands:
        try:
            subprocess.run(cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[-] TC setup warning: {e}", file=sys.stderr)

    print("[+] TC HTB classes and mark-based filters active.")
    print(f"    fwmark 1 → class 1:10 → {EMERGENCY_RATE} rate / {EMERGENCY_CEIL} ceil / prio 1")
    print(f"    fwmark 2 → class 1:20 → {BASELINE_RATE} rate / {BASELINE_CEIL} ceil / prio 2")

# ==============================================================================
# 6. AUTOMATED KERNEL HOOKS (DYNAMIC TC THROTTLING) (UPDATED FOR HOST LAYER ENTRY)
# ==============================================================================
def execute_kernel_qos(mode):
    """
    Dynamically changes class 1:20 rate using tc class change.
    Always explicitly sets prio 2 to prevent it defaulting to 0.

    THROTTLE: squeeze 1:20 to 512kbit when emergency detected
    RESTORE:  bring 1:20 back to 1mbit/3mbit baseline when emergency clears
    """
    global is_emergency_active

    if mode == "THROTTLE" and not is_emergency_active:
        print("\n[!] EMERGENCY DETECTED — throttling class 1:20...")

        cmd = (
            f"sudo tc class change dev {TARGET_INTERFACE} "
            f"classid {CLASS_ID_NORMAL} htb "
            f"rate {THROTTLED_RATE} ceil {THROTTLED_CEIL} "
            f"burst 1600b cburst 1600b "
            f"prio 2"
        )
        try:
            subprocess.run(cmd, shell=True, check=True)
            is_emergency_active = True
            print(f"[+] Class 1:20 throttled → {THROTTLED_RATE} rate / {THROTTLED_CEIL} ceil / prio 2")
        except subprocess.CalledProcessError as e:
            print(f"[-] TC throttle failed: {e}", file=sys.stderr)

    elif mode == "RESTORE" and is_emergency_active:
        print("\n[*] EMERGENCY CLEARED — restoring class 1:20 baseline...")

        cmd = (
            f"sudo tc class change dev {TARGET_INTERFACE} "
            f"classid {CLASS_ID_NORMAL} htb "
            f"rate {BASELINE_RATE} ceil {BASELINE_CEIL} "
            f"burst 1600b cburst 1600b "
            f"prio 2"
        )
        try:
            subprocess.run(cmd, shell=True, check=True)
            is_emergency_active = False
            print(f"[+] Class 1:20 restored → {BASELINE_RATE} rate / {BASELINE_CEIL} ceil / prio 2")
        except subprocess.CalledProcessError as e:
            print(f"[-] TC restore failed: {e}", file=sys.stderr)


# ==============================================================================
# 7. DUAL TELEMETRY REPORTING PIPELINE (LOCAL FLASK + FIREBASE)
# ==============================================================================
def telemetry_reporter():
    """
    Background thread streaming metric payloads to Flask dashboard
    and Firebase Realtime Database at 1Hz.
    """
    global is_emergency_active, total_packets, emergency_packets
    global normal_packets, total_bytes

    while True:
        time.sleep(1.0)

        with metrics_lock:
            payload = {
                "status":             "EMERGENCY" if is_emergency_active else "NORMAL",
                "total_packets":      total_packets,
                "emergency_packets":  emergency_packets,
                "normal_packets":     normal_packets,
                "bytes_processed":    total_bytes,
                "class_1_20_rate":    THROTTLED_RATE if is_emergency_active else BASELINE_RATE,
                "class_1_20_ceil":    THROTTLED_CEIL if is_emergency_active else BASELINE_CEIL,
                "class_1_10_rate":    EMERGENCY_RATE,
                "class_1_10_ceil":    EMERGENCY_CEIL,
                "mark_emergency":     1,
                "mark_normal":        2,
                "timestamp":          int(time.time())
            }

        # Pipeline A — local Flask dashboard (Member 4)
        try:
            requests.post(FLASK_METRICS_URL, json=payload, timeout=0.3)
        except requests.exceptions.RequestException:
            pass

        # Pipeline B — Firebase Realtime Database
        if firebase_online:
            try:
                db_root.child('optiflow_live').set(payload)
            except Exception:
                pass


# ==============================================================================
# 8. FIREBASE CLOUD STATE LISTENER & WATCHDOG (CLIENT-SYNC BRIDGE)
# ==============================================================================
def firebase_state_listener():
    """
    Listens to client app.js pushes on Firebase. Handles concurrent traffic feeds
    by locking in the emergency throttle and utilizing a 3-second watchdog timer
    to restore baseline bandwidth safely when emergency apps close.
    """
    global last_emergency_seen

    def handle_emergency_update(event):
        global last_emergency_seen
        if event.data:
            with metrics_lock:
                global emergency_packets
                emergency_packets += 1
                last_emergency_seen = time.time()  # Refresh clock on active sync
            execute_kernel_qos("THROTTLE")

    def handle_normal_update(event):
        if event.data:
            with metrics_lock:
                global normal_packets
                normal_packets += 1
            if isinstance(event.data, dict):
                print(f"[BACKGROUND NORMAL] App: {event.data.get('activeApplication', 'Unknown')} | Status: {event.data.get('bandwidth', 'N/A')}")

    def emergency_watchdog():
        global is_emergency_active, last_emergency_seen
        while True:
            time.sleep(1.0)
            with metrics_lock:
                if is_emergency_active and (time.time() - last_emergency_seen > EMERGENCY_TIMEOUT):
                    print(f"\n[+] {EMERGENCY_TIMEOUT}s timeout reached. Emergency app closed. Restoring baseline.")
                    execute_kernel_qos("RESTORE")

    if firebase_online:
        try:
            db_root.child('emergency').listen(handle_emergency_update)
            db_root.child('normal').listen(handle_normal_update)

            # Start background watchdog thread
            threading.Thread(target=emergency_watchdog, daemon=True).start()

            print("[+] Firebase concurrent state listeners & watchdog active.")
        except Exception as e:
            print(f"[-] Failed to bind Firebase listeners: {e}", file=sys.stderr)


# ==============================================================================
# 9. PACKET PARSING & MARK-AWARE DISSECTOR (UPDATED WITH TIMEOUT LOGIC)
# ==============================================================================
def packet_analyzer(packet):
    """
    Dissects frames from the main server interface.
    Uses port to identify mark value (same logic as nftables classify chain).
    Drives TC throttle/restore safely using a timeout window.
    """
    global total_packets, emergency_packets, normal_packets, total_bytes
    global last_emergency_seen

    if packet.haslayer(IP):
        sport, dport = None, None
        if packet.haslayer(TCP):
            sport, dport = packet[TCP].sport, packet[TCP].dport
        elif packet.haslayer(UDP):
            sport, dport = packet[UDP].sport, packet[UDP].dport

        packet_len = len(packet)
        current_time = time.time()

        with metrics_lock:
            total_packets += 1
            total_bytes   += packet_len

            # Port 9999 → mark 1 → emergency → throttle 1:20
            if dport == EMERGENCY_PORT or sport == EMERGENCY_PORT:
                emergency_packets += 1
                last_emergency_seen = current_time  # Reset the activity clock
                print(f"► [mark 1 | EMERGENCY] port 9999 | {packet_len}B "
                      f"→ class 1:10 | {EMERGENCY_RATE}/{EMERGENCY_CEIL}")
                execute_kernel_qos("THROTTLE")

            # Port 8888 → mark 2 → normal → evaluation window
            elif dport == NORMAL_PORT or sport == NORMAL_PORT:
                normal_packets += 1

                # Dynamic check: Has the emergency stream gone silent?
                if is_emergency_active and (current_time - last_emergency_seen > EMERGENCY_TIMEOUT):
                    print(f"\n[+] {EMERGENCY_TIMEOUT}s emergency timeout reached with no port 9999 traffic.")
                    execute_kernel_qos("RESTORE")

                print(f"  [mark 2 | NORMAL]     port 8888 | {packet_len}B "
                      f"→ class 1:20 | "
                      f"{'throttled' if is_emergency_active else BASELINE_RATE + '/' + BASELINE_CEIL}")

# ==============================================================================
# 10. ENGINE MAIN APPLICATION LOOP (UPDATED WITH SYSTEM CLEANUP FLUSH)
# ==============================================================================
def main():
    if os.getuid() != 0:
        print("[-] Error: must run as root (sudo).", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("      OPTIFLOW AUTOMATION + CLOUD SYSTEM IS ONLINE")
    print("=" * 60)
    print(f"[*] Interface        : {TARGET_INTERFACE}")
    print(f"[*] Emergency port   : {EMERGENCY_PORT} → mark 1 → class 1:10 ({EMERGENCY_RATE}/{EMERGENCY_CEIL})")
    print(f"[*] Normal port      : {NORMAL_PORT} → mark 2 → class 1:20 ({BASELINE_RATE}/{BASELINE_CEIL})")
    print(f"[*] Throttled state  : class 1:20 → {THROTTLED_RATE}/{THROTTLED_CEIL}")
    print()

    # Step 1 — build nftables mark-based firewall
    setup_nftables()
    print()

    # Step 2 — build TC with mark-based filters
    setup_tc()
    print()

    # Step 3 — verify rules
    verify_nftables()
    print()

    # Step 4 — start telemetry thread
    threading.Thread(target=telemetry_reporter, daemon=True).start()
    print("[*] Telemetry pipeline active (Flask + Firebase).")

    # Step 4.5 — start Firebase cloud state listener & watchdog thread
    threading.Thread(target=firebase_state_listener, daemon=True).start()

    # Step 5 — start packet capture
    bpf_filter = f"port {EMERGENCY_PORT} or port {NORMAL_PORT}"
    print(f"[*] BPF filter: {bpf_filter}")
    print("[*] Monitoring loop active. Ctrl+C to stop.\n")

    try:
        sniff(
            iface=TARGET_INTERFACE,
            filter=bpf_filter,
            prn=packet_analyzer,
            store=0
        )
    except KeyboardInterrupt:
        print("\n[-] Shutting down...")
    finally:
        print("\n[-] Flushing kernel alterations...")
        # Deep cleaning: delete the root qdisc completely from the public interface
        subprocess.run(f"sudo tc qdisc del dev {TARGET_INTERFACE} root 2>/dev/null || true", shell=True)
        # Deep cleaning: drop the optiflow tables completely to unblock matching configurations
        subprocess.run("sudo nft delete table ip optiflow 2>/dev/null || true", shell=True)
        print("[+] Network engine returned cleanly to system host defaults. Environment safe.")
        print("[+] Done.")


if __name__ == "__main__":
    main()