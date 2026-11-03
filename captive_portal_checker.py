# captive_portal_checker.py
# Run this whenever you connect to a new public wifi

try:
    import requests
except ImportError:
    import urllib.request
    import urllib.error

    class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def http_error_301(self, req, fp, code, msg, headers):
            raise urllib.error.HTTPError(req.full_url, code, msg, fp, headers)
        def http_error_302(self, req, fp, code, msg, headers):
            raise urllib.error.HTTPError(req.full_url, code, msg, fp, headers)
        def http_error_303(self, req, fp, code, msg, headers):
            raise urllib.error.HTTPError(req.full_url, code, msg, fp, headers)
        def http_error_307(self, req, fp, code, msg, headers):
            raise urllib.error.HTTPError(req.full_url, code, msg, fp, headers)
        def http_error_308(self, req, fp, code, msg, headers):
            raise urllib.error.HTTPError(req.full_url, code, msg, 
                                         fp, headers)

    class _Response:
        def __init__(self, status_code, content, url, headers):
            self.status_code = status_code
            self.content = content
            self.text = content.decode("utf-8", errors="replace")
            self.url = url
            self.headers = headers

    class _RequestsFallback:
        class exceptions:
            ConnectionError = urllib.error.URLError
            Timeout = urllib.error.URLError

        @staticmethod
        def get(url, timeout=10, allow_redirects=False, headers33=None):
            request = urllib.request.Request(url, headers=headers or {}, method="GET")
            opener = urllib.request.build_opener(_NoRedirectHandler) if not allow_redirects else urllib.request.build_opener()
            try:
                response = opener.open(request, timeout=timeout)
                content = response.read()
                return _Response(
                    status_code=response.getcode(),
                    content=content,
                    url=response.geturl(),
                    headers={k: v for k, v in response.headers.items()}
                )
            except urllib.error.HTTPError as err:
                content = err.read() if hasattr(err, "read") else b""
                return _Response(
                    status_code=err.code,
                    content=content,
                    url=err.geturl(),
                    headers={k: v for k, v in err.headers.items()} if hasattr(err, "headers") else {}
                )

    requests = _RequestsFallback

import socket
import time
import subprocess
import json
import sys
from datetime import datetime

# ─────────────────────────────────────────────────────────
# WHAT THIS SCRIPT DOES AT EACH STEP
#
# STEP 1: Try to reach a known URL
#         If we get redirected → captive portal exists
#         If we get the real page → no portal, open wifi
#
# STEP 2: Measure how annoying the login process is
#         You tell it what happened (OTP time, etc)
#         It calculates the hassle score
#
# STEP 3: After you log in, test if it actually works
#         Some portals show success but still block internet
#
# STEP 4: Measure session duration
#         Start a timer, check every few minutes
#         When internet dies → session expired
# ─────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════
# PART 1: DETECT IF CAPTIVE PORTAL EXISTS
# ══════════════════════════════════════════════════════════

def detect_captive_portal():
    """
    How this works:
    
    We try to reach a URL that we KNOW exactly what it returns.
    Google has a special page: http://clients1.google.com/generate_204
    That page always returns HTTP status 204 and empty body.
    
    If we get 204 → no captive portal, internet is open
    If we get 200 with different content → portal intercepted us
    If we get 302 redirect → portal is redirecting us
    If connection fails → no internet at all
    """
    
    print("\n" + "═"*55)
    print("  STEP 1: DETECTING CAPTIVE PORTAL")
    print("═"*55)
    
    # These are URLs specifically designed for portal detection
    # Different devices use different ones
    detection_urls = [
        {
            "url": "http://clients1.google.com/generate_204",
            "expected_status": 204,
            "name": "Google Generate 204"
        },
        {
            "url": "http://connectivitycheck.gstatic.com/generate_204",
            "expected_status": 204,
            "name": "Google Connectivity Check"
        },
        {
            "url": "http://www.msftconnecttest.com/connecttest.txt",
            "expected_status": 200,
            "name": "Microsoft Connect Test"
        },
        {
            "url": "http://captive.apple.com/hotspot-detect.html",
            "expected_status": 200,
            "name": "Apple Captive Detection"
        }
    ]
    
    result = {
        "portal_detected": False,
        "portal_url": None,
        "portal_type": "none",
        "redirect_url": None,
        "detection_method": None,
        "internet_accessible": False
    }
    
    for check in detection_urls:
        print(f"\n  Checking via {check['name']}...")
        print(f"  URL: {check['url']}")
        
        try:
            response = requests.get(
                check["url"],
                timeout=10,
                allow_redirects=False,  
                # ↑ IMPORTANT: do not follow redirects automatically
                # We want to SEE the redirect, not follow it
                headers={
                    "User-Agent": "Mozilla/5.0 (Android 13; Mobile)"
                }
            )
            
            print(f"  Status code received: {response.status_code}")
            
            # ── CASE 1: Got exactly what we expected ──────────────
            if response.status_code == check["expected_status"]:
                
                # Extra check: is the content right?
                if check["expected_status"] == 204:
                    # 204 means No Content, body should be empty
                    if len(response.content) == 0:
                        result["internet_accessible"] = True
                        result["portal_detected"] = False
                        print(f"  ✅ Got expected {check['expected_status']}")
                        print(f"  ✅ NO captive portal detected")
                        print(f"  ✅ Internet is directly accessible")
                        return result
                
                elif check["expected_status"] == 200:
                    # Check if content matches what we expect
                    if "Microsoft Connect Test" in check["name"]:
                        if "Microsoft Connect Test" in response.text:
                            result["internet_accessible"] = True
                            result["portal_detected"] = False
                            print(f"  ✅ Content matches expected")
                            print(f"  ✅ NO captive portal detected")
                            return result
            
            # ── CASE 2: Got a redirect ─────────────────────────────
            elif response.status_code in [301, 302, 303, 307, 308]:
                redirect_to = response.headers.get("Location", "unknown")
                result["portal_detected"] = True
                result["redirect_url"] = redirect_to
                result["detection_method"] = check["name"]
                print(f"  🚨 REDIRECT detected!")
                print(f"  🚨 Redirecting to: {redirect_to}")
                print(f"  🚨 CAPTIVE PORTAL EXISTS")
                
                # Try to figure out what kind of portal
                result["portal_type"] = identify_portal_type(redirect_to)
                print(f"  📋 Portal type: {result['portal_type']}")
                return result
            
            # ── CASE 3: Got 200 but with portal content ────────────
            elif response.status_code == 200:
                # Portal intercepted our request and returned its own page
                content = response.text.lower()
                
                portal_keywords = [
                    "login", "sign in", "connect", "register",
                    "otp", "mobile", "phone", "accept", "terms",
                    "railwire", "railtel", "bsnl", "airtel wifi",
                    "free wifi", "captive"
                ]
                
                found_keywords = [k for k in portal_keywords if k in content]
                
                if found_keywords:
                    result["portal_detected"] = True
                    result["detection_method"] = check["name"]
                    result["portal_type"] = "intercepted"
                    print(f"  🚨 Got 200 but content looks like a portal")
                    print(f"  🚨 Portal keywords found: {found_keywords[:3]}")
                    print(f"  🚨 CAPTIVE PORTAL EXISTS (intercept type)")
                    return result
        
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Connection failed — no internet or wifi not connected")
            result["portal_detected"] = False
            result["internet_accessible"] = False
            result["portal_type"] = "no_internet"
            return result
            
        except requests.exceptions.Timeout:
            print(f"  ⏱  Timeout — wifi connected but internet blocked")
            print(f"  ⏱  This often means captive portal exists")
            result["portal_detected"] = True
            result["portal_type"] = "timeout_block"
            return result
            
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
            continue
    
    return result


def identify_portal_type(redirect_url):
    """
    Look at the URL we got redirected to
    and figure out what kind of portal it is.
    """
    url_lower = redirect_url.lower()
    
    if "railwire" in url_lower or "railtel" in url_lower:
        return "railwire_otp"
    
    elif "bsnl" in url_lower:
        return "bsnl_otp"
    
    elif "airtel" in url_lower:
        return "airtel_portal"
    
    elif "smartcity" in url_lower or "smart-city" in url_lower:
        return "smart_city_otp"
    
    elif "facebook" in url_lower or "fb.com" in url_lower:
        return "facebook_login"
    
    elif "google" in url_lower and "accounts" in url_lower:
        return "google_login"
    
    elif "aadhaar" in url_lower or "uidai" in url_lower:
        return "aadhaar_required"
    
    elif "voucher" in url_lower or "coupon" in url_lower:
        return "voucher_required"
    
    elif "ads" in url_lower or "advertisement" in url_lower:
        return "ad_based"
    
    else:
        return "unknown_portal"


# ══════════════════════════════════════════════════════════
# PART 2: INTERACTIVE HASSLE MEASUREMENT
# ══════════════════════════════════════════════════════════

def measure_login_hassle(portal_detected, portal_type):
    """
    We cannot automate the actual login process
    (every portal is different, OTP goes to your phone, etc)
    
    So instead: we time the process while YOU do it,
    and ask you questions about what happened.
    
    Think of this as a structured interview while
    you are going through the login process.
    """
    
    print("\n" + "═"*55)
    print("  STEP 2: MEASURING LOGIN HASSLE")
    print("═"*55)
    
    hassle_data = {
        "portal_detected": portal_detected,
        "portal_type": portal_type,
        "login_method": None,
        "otp_required": False,
        "otp_arrived": None,
        "otp_time_seconds": None,
        "login_page_loaded": None,
        "login_succeeded": None,
        "attempts_needed": 1,
        "hassle_score": None,
        "hassle_reason": []
    }
    
    # ── NO PORTAL: BEST CASE ───────────────────────────────────
    if not portal_detected:
        print("\n  No captive portal detected.")
        print("  This is the BEST possible situation.")
        print("  Wifi just works. No login needed.")
        
        hassle_data["login_method"] = "none"
        hassle_data["hassle_score"] = 1
        hassle_data["hassle_reason"] = ["No login required"]
        
        print("\n  Hassle Score: 1/5 — Seamless ✅")
        return hassle_data
    
    # ── PORTAL EXISTS: ASK QUESTIONS ──────────────────────────
    print(f"\n  Portal type detected: {portal_type}")
    print("\n  I will ask you questions as you go through the login.")
    print("  Open your browser now and try to connect.\n")
    
    # QUESTION 1: Did the login page load?
    print("  ┌─ QUESTION 1 ──────────────────────────────────┐")
    print("  │  Did the captive portal login page load?      │")
    print("  │  (Did you see a login/connect page at all?)   │")
    print("  └───────────────────────────────────────────────┘")
    print("  1 = Yes, loaded fine")
    print("  2 = Yes but very slowly (>10 seconds)")
    print("  3 = Partially loaded (broken page)")
    print("  4 = Did not load at all")
    
    page_load = input("\n  Your answer (1/2/3/4): ").strip()
    
    if page_load == "1":
        hassle_data["login_page_loaded"] = "yes"
    elif page_load == "2":
        hassle_data["login_page_loaded"] = "slow"
        hassle_data["hassle_reason"].append("Login page loaded slowly")
    elif page_load == "3":
        hassle_data["login_page_loaded"] = "broken"
        hassle_data["hassle_reason"].append("Login page was broken/incomplete")
    elif page_load == "4":
        hassle_data["login_page_loaded"] = "failed"
        hassle_data["hassle_reason"].append("Login page did not load")
        hassle_data["login_succeeded"] = False
        hassle_data["hassle_score"] = 5
        print("\n  ❌ Login page did not load.")
        print("  Hassle Score: 5/5 — Completely unusable")
        return hassle_data
    
    # QUESTION 2: What does it ask for?
    print("\n  ┌─ QUESTION 2 ──────────────────────────────────┐")
    print("  │  What does the portal ask you to do?         │")
    print("  └───────────────────────────────────────────────┘")
    print("  1 = Just a 'Connect' button (no info needed)")
    print("  2 = Enter mobile number for OTP")
    print("  3 = Enter email address")
    print("  4 = Login with Facebook/Google")
    print("  5 = Enter a password/voucher code")
    print("  6 = Aadhaar number required")
    print("  7 = Watch an advertisement")
    print("  8 = Something else")
    
    login_type = input("\n  Your answer (1-8): ").strip()
    
    login_method_map = {
        "1": "one_click",
        "2": "otp",
        "3": "email",
        "4": "social_media",
        "5": "password",
        "6": "aadhaar",
        "7": "advertisement",
        "8": "other"
    }
    hassle_data["login_method"] = login_method_map.get(login_type, "unknown")
    
    # QUESTION 3: OTP specific questions
    if login_type == "2":
        hassle_data["otp_required"] = True
        
        print("\n  ┌─ QUESTION 3: OTP DETAILS ─────────────────────┐")
        print("  │  Enter your number now and start the timer.   │")
        print("  │  Press Enter when OTP arrives on your phone.  │")
        print("  └───────────────────────────────────────────────┘")
        
        print("\n  Waiting... enter your number on the portal now.")
        print("  Press ENTER the moment OTP arrives on your phone.")
        
        otp_start = time.time()
        
        # Start a visible timer
        print("\n  Timer started. Waiting for OTP...")
        
        # Show elapsed time while waiting
        try:
            input("  [Press ENTER when OTP arrives] ")
            otp_time = round(time.time() - otp_start)
            
            hassle_data["otp_arrived"] = True
            hassle_data["otp_time_seconds"] = otp_time
            
            print(f"\n  OTP arrived in: {otp_time} seconds")
            
            if otp_time <= 10:
                print("  ⚡ Very fast OTP delivery")
            elif otp_time <= 30:
                print("  ✅ Acceptable OTP delivery")
            elif otp_time <= 60:
                print("  ⚠️  Slow OTP delivery")
                hassle_data["hassle_reason"].append(f"OTP took {otp_time} seconds")
            else:
                print("  ❌ Very slow OTP delivery")
                hassle_data["hassle_reason"].append(f"OTP took {otp_time} seconds")
        
        except KeyboardInterrupt:
            # User pressed Ctrl+C meaning OTP never came
            hassle_data["otp_arrived"] = False
            hassle_data["otp_time_seconds"] = None
            hassle_data["hassle_reason"].append("OTP never arrived")
            print("\n  ❌ OTP did not arrive")
            hassle_data["hassle_score"] = 5
            print("  Hassle Score: 5/5 — OTP never arrived")
            return hassle_data
    
    # QUESTION 4: Did login actually work?
    print("\n  ┌─ QUESTION 4 ──────────────────────────────────┐")
    print("  │  Go through the login process now.           │")
    print("  │  After completing it, answer this:           │")
    print("  └───────────────────────────────────────────────┘")
    print("  1 = Yes, internet works after login")
    print("  2 = Logged in but internet still not working")
    print("  3 = Login failed (error message)")
    print("  4 = Had to try multiple times")
    
    login_result = input("\n  Your answer (1/2/3/4): ").strip()
    
    if login_result == "1":
        hassle_data["login_succeeded"] = True
        hassle_data["attempts_needed"] = 1
    elif login_result == "2":
        hassle_data["login_succeeded"] = False
        hassle_data["hassle_reason"].append("Login succeeded but internet still blocked")
    elif login_result == "3":
        hassle_data["login_succeeded"] = False
        hassle_data["hassle_reason"].append("Login process failed with error")
    elif login_result == "4":
        hassle_data["login_succeeded"] = True
        attempts = input("  How many attempts did it take? ")
        try:
            hassle_data["attempts_needed"] = int(attempts)
            hassle_data["hassle_reason"].append(f"Needed {attempts} attempts to login")
        except:
            hassle_data["attempts_needed"] = 2
    
    # QUESTION 5: Session duration (optional, takes time)
    print("\n  ┌─ QUESTION 5 ──────────────────────────────────┐")
    print("  │  Session Duration (optional)                  │")
    print("  │  How long before the wifi logs you out?       │")
    print("  └───────────────────────────────────────────────┘")
    print("  1 = Never logged out (or unknown)")
    print("  2 = About 15 minutes")
    print("  3 = About 30 minutes")
    print("  4 = About 1 hour")
    print("  5 = More than 1 hour")
    
    session = input("\n  Your answer (1-5): ").strip()
    session_map = {
        "1": None, "2": 15, "3": 30, "4": 60, "5": 120
    }
    hassle_data["session_duration_min"] = session_map.get(session)
    
    if session == "2":
        hassle_data["hassle_reason"].append("Session expires every 15 minutes")
    elif session == "3":
        hassle_data["hassle_reason"].append("Session expires every 30 minutes")
    
    # CALCULATE FINAL HASSLE SCORE
    hassle_data["hassle_score"] = calculate_hassle_score(hassle_data)
    
    return hassle_data


def calculate_hassle_score(hassle_data):
    """
    Takes everything we measured and returns 1-5.
    
    1 = Seamless (no login or instant connect)
    2 = Easy (simple login, works first time)
    3 = Moderate (OTP needed, arrives quickly)
    4 = Annoying (slow OTP, multiple attempts)
    5 = Unusable (page broken, OTP never arrives)
    """
    
    score = 1  # start optimistic
    
    login_method = hassle_data.get("login_method")
    
    # No login = best possible
    if login_method == "none" or login_method == "one_click":
        return 1
    
    # Login page did not load = worst
    if hassle_data.get("login_page_loaded") == "failed":
        return 5
    
    # OTP never arrived = worst
    if hassle_data.get("otp_required") and not hassle_data.get("otp_arrived"):
        return 5
    
    # Login failed completely
    if hassle_data.get("login_succeeded") == False:
        return 5
    
    # Now score based on friction
    
    # Base score by login method
    method_scores = {
        "one_click":    1,
        "email":        2,
        "social_media": 2,
        "otp":          3,
        "password":     2,
        "advertisement":3,
        "aadhaar":      4,
        "other":        3
    }
    score = method_scores.get(login_method, 3)
    
    # OTP time penalty
    otp_time = hassle_data.get("otp_time_seconds")
    if otp_time:
        if otp_time > 120:   score = min(5, score + 2)
        elif otp_time > 60:  score = min(5, score + 1)
        elif otp_time > 30:  score = min(5, score + 0.5)
    
    # Multiple attempts penalty
    attempts = hassle_data.get("attempts_needed", 1)
    if attempts >= 3:    score = min(5, score + 1)
    elif attempts == 2:  score = min(5, score + 0.5)
    
    # Broken page penalty
    if hassle_data.get("login_page_loaded") == "broken":
        score = min(5, score + 1)
    elif hassle_data.get("login_page_loaded") == "slow":
        score = min(5, score + 0.5)
    
    # Short session penalty
    session = hassle_data.get("session_duration_min")
    if session and session <= 15:
        score = min(5, score + 1)
    elif session and session <= 30:
        score = min(5, score + 0.5)
    
    return round(min(5, max(1, score)))


# ══════════════════════════════════════════════════════════
# PART 3: TEST INTERNET AFTER LOGIN
# ══════════════════════════════════════════════════════════

def test_post_login_internet():
    """
    After you log in, does the internet actually work?
    We test this properly with real sites.
    """
    
    print("\n" + "═"*55)
    print("  STEP 3: TESTING INTERNET AFTER LOGIN")
    print("═"*55)
    
    test_sites = [
        ("Google",    "https://www.google.com",    5),
        ("YouTube",   "https://m.youtube.com",     10),
        ("WhatsApp",  "https://web.whatsapp.com",  8),
        ("Wikipedia", "https://en.wikipedia.org",  5),
    ]
    
    results = {}
    all_passed = True
    
    for name, url, timeout in test_sites:
        try:
            start = time.time()
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            load_time = round((time.time() - start) * 1000)
            
            # Check we got a real response (not a portal redirect)
            # Portal redirect would give us portal HTML, not YouTube HTML
            is_real_site = response.status_code == 200
            
            # Extra check: did we get redirected to a portal?
            if response.url != url:
                final_url = response.url
                if any(portal_word in final_url.lower()
                       for portal_word in ["login", "captive", "portal", "connect"]):
                    is_real_site = False
            
            results[name] = {
                "loaded": is_real_site,
                "time_ms": load_time,
                "status": response.status_code
            }
            
            if is_real_site:
                status_icon = "✅" if load_time < 3000 else "⚠️"
                print(f"  {status_icon} {name}: {load_time}ms")
            else:
                print(f"  ❌ {name}: Redirected to portal (login not complete?)")
                all_passed = False
                
        except requests.exceptions.Timeout:
            results[name] = {"loaded": False, "time_ms": None, "error": "timeout"}
            print(f"  ❌ {name}: Timeout")
            all_passed = False
            
        except Exception as e:
            results[name] = {"loaded": False, "time_ms": None, "error": str(e)}
            print(f"  ❌ {name}: Failed")
            all_passed = False
    
    if all_passed:
        print("\n  ✅ Internet working after login")
    else:
        print("\n  ⚠️  Some sites not accessible even after login")
        print("  This means the portal logged you in but still blocks content")
    
    return results


# ══════════════════════════════════════════════════════════
# PART 4: SESSION TIMEOUT MONITOR
# ══════════════════════════════════════════════════════════

def monitor_session_timeout(max_minutes=30):
    """
    Keeps checking every 60 seconds if internet still works.
    Stops when:
    - Internet dies (session expired)
    - max_minutes reached
    - You press Ctrl+C
    
    This tells you how long the session lasts.
    """
    
    print("\n" + "═"*55)
    print("  STEP 4: SESSION TIMEOUT MONITOR")
    print("═"*55)
    print(f"\n  Will monitor for up to {max_minutes} minutes.")
    print("  Press Ctrl+C to stop early.\n")
    
    start_time = time.time()
    check_interval = 60  # check every 60 seconds
    check_count = 0
    
    print("  Time    | Status")
    print("  ─────────────────────────────")
    
    try:
        while True:
            elapsed = round((time.time() - start_time) / 60, 1)
            
            # Quick check: can we reach Google?
            try:
                response = requests.get(
                    "http://clients1.google.com/generate_204",
                    timeout=5,
                    allow_redirects=False
                )
                
                if response.status_code == 204:
                    print(f"  {elapsed:5} min | ✅ Internet active")
                    check_count += 1
                else:
                    # Got redirected → session expired → portal back
                    session_duration = round(time.time() - start_time)
                    print(f"  {elapsed:5} min | 🔴 SESSION EXPIRED")
                    print(f"\n  Session lasted: {session_duration} seconds")
                    print(f"  ({round(session_duration/60, 1)} minutes)")
                    return session_duration
                    
            except:
                session_duration = round(time.time() - start_time)
                print(f"  {elapsed:5} min | 🔴 CONNECTION LOST")
                print(f"\n  Session lasted approx: {round(session_duration/60, 1)} minutes")
                return session_duration
            
            if elapsed >= max_minutes:
                print(f"\n  ✅ Session still active after {max_minutes} minutes")
                print(f"  Stopping monitor. Good session duration.")
                return None  # means: lasted at least max_minutes
            
            time.sleep(check_interval)
    
    except KeyboardInterrupt:
        elapsed = round((time.time() - start_time) / 60, 1)
        print(f"\n  Stopped after {elapsed} minutes")
        print(f"  Session was still active when stopped")
        return None


# ══════════════════════════════════════════════════════════
# PART 5: FULL REPORT + SAVE
# ══════════════════════════════════════════════════════════

def save_portal_report(location_name, portal_data, hassle_data, post_login_data):
    """
    Combines all measurements into one report.
    Saves to JSON file.
    Prints human-readable summary.
    """
    
    score = hassle_data.get("hassle_score", 3)
    
    score_descriptions = {
        1: "Seamless — Just works, no friction",
        2: "Easy — Simple login, works reliably",
        3: "Moderate — OTP or some friction but usable",
        4: "Annoying — Slow OTP, multiple attempts, short sessions",
        5: "Unusable — Portal broken, OTP fails, login impossible"
    }
    
    score_icons = {1: "✅", 2: "🟢", 3: "🟡", 4: "🟠", 5: "🔴"}
    
    report = {
        "location": location_name,
        "timestamp": datetime.now().isoformat(),
        "portal": {
            "detected": portal_data.get("portal_detected"),
            "type": portal_data.get("portal_type"),
            "redirect_url": portal_data.get("redirect_url")
        },
        "login": {
            "method": hassle_data.get("login_method"),
            "otp_required": hassle_data.get("otp_required"),
            "otp_arrived": hassle_data.get("otp_arrived"),
            "otp_time_seconds": hassle_data.get("otp_time_seconds"),
            "page_loaded": hassle_data.get("login_page_loaded"),
            "succeeded": hassle_data.get("login_succeeded"),
            "attempts": hassle_data.get("attempts_needed"),
            "session_duration_min": hassle_data.get("session_duration_min")
        },
        "post_login": post_login_data,
        "hassle_score": score,
        "hassle_reasons": hassle_data.get("hassle_reason", []),
        "hassle_description": score_descriptions.get(score, "Unknown")
    }
    
    # Print the final report
    print("\n" + "═"*55)
    print("  CAPTIVE PORTAL REPORT")
    print("═"*55)
    print(f"\n  Location : {location_name}")
    print(f"  Portal   : {'YES — ' + portal_data.get('portal_type', '') if portal_data.get('portal_detected') else 'NO — Open wifi'}")
    print(f"  Login    : {hassle_data.get('login_method', 'N/A')}")
    
    if hassle_data.get("otp_time_seconds"):
        print(f"  OTP Time : {hassle_data['otp_time_seconds']} seconds")
    
    print(f"\n  {'─'*45}")
    print(f"  HASSLE SCORE: {score_icons.get(score, '?')} {score}/5")
    print(f"  {score_descriptions.get(score, '')}")
    print(f"  {'─'*45}")
    
    if hassle_data.get("hassle_reason"):
        print(f"\n  Reasons for this score:")
        for reason in hassle_data["hassle_reason"]:
            print(f"    → {reason}")
    
    # Save to file
    filename = "portal_readings.json"
    try:
        with open(filename, "r") as f:
            all_reports = json.load(f)
    except FileNotFoundError:
        all_reports = []
    
    all_reports.append(report)
    
    with open(filename, "w") as f:
        json.dump(all_reports, f, indent=2)
    
    print(f"\n  💾 Saved to {filename}")
    print(f"  Total portal readings: {len(all_reports)}")
    print("═"*55)
    
    return report


# ══════════════════════════════════════════════════════════
# MAIN: RUN EVERYTHING IN ORDER
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    
    print("╔═══════════════════════════════════════════════════╗")
    print("║     CAPTIVE PORTAL HASSLE CHECKER                ║")
    print("║     Connect to the wifi FIRST, then run this     ║")
    print("╚═══════════════════════════════════════════════════╝")
    
    # Get location name from user
    print("\nMake sure you are connected to the wifi you want to test.")
    location = input("Enter location name: ").strip()
    
    if not location:
        location = "Niken's phone wifi"
    
    # STEP 1: Detect portal
    portal_data = detect_captive_portal()
    
    # STEP 2: Measure hassle (you go through login while answering questions)
    hassle_data = measure_login_hassle(
        portal_detected=portal_data["portal_detected"],
        portal_type=portal_data.get("portal_type", "unknown")
    )
    
    # STEP 3: Test internet after login
    if hassle_data.get("login_succeeded") or not portal_data["portal_detected"]:
        post_login = test_post_login_internet()
    else:
        post_login = {}
        print("\n  Skipping post-login test (login did not succeed)")
    
    # STEP 4: Optional session monitor
    print("\n" + "═"*55)
    print("  OPTIONAL: Monitor session timeout?")
    print("  This will keep running and tell you when wifi kicks you out.")
    monitor = input("  Monitor session? (y/n): ").strip().lower()
    
    if monitor == "y":
        minutes = input("  For how many minutes? (default 30): ").strip()
        try:
            max_min = int(minutes)
        except:
            max_min = 30
        
        monitor_session_timeout(max_minutes=max_min)
    
    # STEP 5: Save everything
    save_portal_report(location, portal_data, hassle_data, post_login)