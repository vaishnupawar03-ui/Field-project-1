import speedtest
import socket
import subprocess
import time
import json
from datetime import datetime

def test_wifi_quality(location_name):
    print(f"\n{'='*55}")
    print(f"  TESTING: {location_name}")
    print(f"  Time: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    print(f"{'='*55}\n")

    results = {
    "location": location_name,
    "timestamp": datetime.now().isoformat(),
}

# =============================================
# TEST 1: SPEED TEST (Download + Upload + Ping)
# =============================================
    print("[1/5] Running speed test...")
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        
        download = st.download() / 1_000_000
        upload = st.upload() / 1_000_000
        ping = st.results.ping
        
        results["download_mbps"] = round(download, 2)
        results["upload_mbps"] = round(upload, 2)
        results["ping_ms"] = round(ping, 1)
        results["server"] = st.results.server.get("name", "Unknown")
        
        print(f"  ↓ Download : {download:.2f} Mbps")
        print(f"  ↑ Upload   : {upload:.2f} Mbps")
        print(f"  ⏱  Ping     : {ping:.1f} ms")
        print(f"  🖥  Server   : {results['server']}")
        
    except Exception as e:
        print(f"  ❌ Speed test failed: {e}")
        results["download_mbps"] = None
        results["upload_mbps"] = None
        results["ping_ms"] = None

    # =============================================
    # TEST 2: DNS RESOLUTION TIME
    # =============================================
    print("\n[2/5] Testing DNS resolution...")
    try:
        start = time.time()
        socket.getaddrinfo("google.com", 80)
        dns_time = round((time.time() - start) * 1000, 2)
        results["dns_ms"] = dns_time
        print(f"  DNS Time  : {dns_time} ms")
        if dns_time > 1000:
            print(f"  ⚠️  WARNING: Very slow DNS!")
    except:
        results["dns_ms"] = None
        print(f"  ❌ DNS resolution failed")

    # =============================================
    # TEST 3: PACKET LOSS
    # =============================================
    print("\n[3/5] Testing packet loss...")
    try:
        output = subprocess.run(
            ["ping", "-c", "10", "8.8.8.8"],
            capture_output=True, text=True, timeout=15
        )
        for line in output.stdout.split("\n"):
            if "packet loss" in line:
                loss = float(line.split("%")[0].split()[-1])
                results["packet_loss_pct"] = loss
                print(f"  Packet Loss: {loss}%")
                if loss > 5:
                    print(f"  ⚠️  WARNING: High packet loss!")
                break
    except:
        results["packet_loss_pct"] = None
        print(f"  ❌ Packet loss test failed")

    # =============================================
    # TEST 4: REAL WEBSITE LOAD TIMES
    # =============================================
    print("\n[4/5] Testing real website load times...")
    import urllib.request

    websites = {
        "Google": "https://www.google.com",
        "YouTube": "https://m.youtube.com",
        "Wikipedia": "https://en.wikipedia.org",
        "Twitter/X": "https://x.com",
    }

    for name, url in websites.items():
        try:
            start = time.time()
            urllib.request.urlopen(url, timeout=10)
            load_time = round((time.time() - start) * 1000)
            results[f"{name.lower()}_ms"] = load_time
            status = "✅" if load_time < 3000 else "⚠️" if load_time < 8000 else "❌"
            print(f"  {status} {name}: {load_time}ms")
        except Exception as e:
            results[f"{name.lower()}_ms"] = None
            print(f"  ❌ {name}: Failed to load")

    # =============================================
    # TEST 5: NETWORK INTERFACE INFO
    # =============================================
    print("\n[5/5] Checking network info...")
    try:
        import psutil
        addrs = psutil.net_if_addrs()
        for iface, addr_list in addrs.items():
            if "wlan" in iface.lower() or "wifi" in iface.lower():
                for addr in addr_list:
                    if addr.family == 2:  # AF_INET = IPv4
                        results["local_ip"] = addr.address
                        print(f"  Interface : {iface}")
                        print(f"  Local IP  : {addr.address}")
    except:
        print(f"  Could not detect network interface")

    # =============================================
    # SIGNAL STRENGTH (if available)
    # =============================================
    try:
        output = subprocess.run(
            ["iwconfig"], capture_output=True, text=True, timeout=5
        )
        for line in output.stdout.split("\n"):
            if "Signal level" in line:
                signal = line.split("Signal level=")[1].split()[0]
                results["signal_dbm"] = float(signal)
                print(f"  Signal    : {signal} dBm")
                break
    except:
        pass

    # =============================================
    # SAVE RESULTS
    # =============================================
    print(f"\n{'='*55}")
    print("  SUMMARY")
    print(f"{'='*55}")
    print(f"  Download   : {results.get('download_mbps', 'N/A')} Mbps")
    print(f"  Upload     : {results.get('upload_mbps', 'N/A')} Mbps")
    print(f"  Ping       : {results.get('ping_ms', 'N/A')} ms")
    print(f"  DNS        : {results.get('dns_ms', 'N/A')} ms")
    print(f"  Packet Loss: {results.get('packet_loss_pct', 'N/A')}%")
    print(f"{'='*55}")

    # Save to file
    filename = "wifi_readings.json"
    try:
        with open(filename, "r") as f:
            all_readings = json.load(f)
    except FileNotFoundError:
        all_readings = []

    all_readings.append(results)
    with open(filename, "w") as f:
        json.dump(all_readings, f, indent=2)

    print(f"\n  💾 Saved to {filename}")
    print(f"  Total readings so far: {len(all_readings)}\n")

    return results


if __name__ == "__main__":
    test_wifi_quality("Niken's phone wifi")

