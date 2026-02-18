#!/usr/bin/env python3
"""Test Pocket Ledger blind sign via Speculos emulator.
Uses threading to handle concurrent APDU + button presses."""

import hashlib
import json
import struct
import sys
import time
import threading
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:5005"

def sha256(data):
    return hashlib.sha256(data).digest()

def to_hex(data):
    return data.hex()

def u32le(val):
    return struct.pack('<I', val)

def http_post(url, data_dict, timeout=30):
    body = json.dumps(data_dict).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))

def http_get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))

def http_delete(url):
    req = urllib.request.Request(url, method='DELETE')
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read()

def serialize_path(path_str):
    parts = path_str.split('/')
    components = []
    for p in parts:
        if p.endswith("'"):
            components.append(int(p[:-1]) | 0x80000000)
        else:
            components.append(int(p))
    buf = bytes([len(components)])
    for c in components:
        buf += u32le(c)
    return buf

def build_chunked_param(payload):
    next_hash = b'\x00' * 32
    chunk = next_hash + payload
    root_hash = sha256(chunk)
    return root_hash, {to_hex(root_hash): chunk}

def apdu_hex(cla, ins, p1, p2, data):
    return to_hex(bytes([cla, ins, p1, p2, len(data)]) + data)

def send_apdu(data_hex, timeout=30):
    resp = http_post(f"{BASE_URL}/apdu", {"data": data_hex}, timeout=timeout)
    return bytes.fromhex(resp["data"])

def press_button(name):
    http_post(f"{BASE_URL}/button/{name}", {"action": "press-and-release"})

def clear_automation():
    http_post(f"{BASE_URL}/automation", {"version": 1, "rules": []})

def delete_events():
    http_delete(f"{BASE_URL}/events")

def toggle_blind_signing():
    buttons = ["right", "right", "both", "both", "right", "both", "left", "left"]
    for b in buttons:
        press_button(b)
        time.sleep(0.15)

def get_current_screen_text():
    """Get the most recent screen text."""
    events = http_get(f"{BASE_URL}/events").get("events", [])
    if not events:
        return []
    # Get unique recent texts
    recent = []
    for e in events[-10:]:
        t = e.get("text", "")
        if t and t not in recent:
            recent.append(t)
    return recent

def wait_for_text_and_advance(target_texts, action="right", max_wait=10, interval=0.2):
    """Wait for specific text to appear then press button."""
    start = time.time()
    while time.time() - start < max_wait:
        texts = get_current_screen_text()
        for target in target_texts:
            if target in texts:
                time.sleep(0.1)
                press_button(action)
                return target
        time.sleep(interval)
    return None

def auto_approve_blind_sign_prompts():
    """Press buttons to approve all blind sign prompts.
    Expected prompts:
    1. WARNING / long text → right to advance
    2. Sign for Address / address → right to advance
    3. Blind Sign Transaction? → right to go to Confirm
    4. Confirm → both buttons
    """
    time.sleep(0.3)  # Wait for first prompt to appear

    # Navigate through scrollers by pressing right repeatedly
    # Each right-button press advances to the next screen
    # The scrollers are: WARNING, Sign for Address
    # After those, we get: Blind Sign Transaction? → Confirm → Reject

    # Strategy: press right button rapidly to advance through all scrollers
    # until we see "Confirm", then press both buttons
    max_presses = 30
    for i in range(max_presses):
        texts = get_current_screen_text()
        # Check if we see "Confirm" - if so, press both to accept
        if "Confirm" in texts:
            time.sleep(0.1)
            press_button("both")
            time.sleep(0.1)
            print("    [auto] Pressed BOTH on Confirm")
            return True
        # Check if we see "Reject" - went too far, press left to go back to Confirm
        if "Reject" in texts:
            press_button("left")
            time.sleep(0.2)
            texts = get_current_screen_text()
            if "Confirm" in texts:
                time.sleep(0.1)
                press_button("both")
                time.sleep(0.1)
                print("    [auto] Pressed BOTH on Confirm (after left from Reject)")
                return True

        # Otherwise press right to advance
        press_button("right")
        time.sleep(0.15)

    print("    [auto] WARNING: Could not find Confirm prompt")
    return False

def send_apdu_in_thread(data_hex, result_holder, timeout=30):
    """Send APDU in a thread, store result."""
    try:
        resp = send_apdu(data_hex, timeout=timeout)
        result_holder['response'] = resp
        result_holder['error'] = None
    except Exception as e:
        result_holder['response'] = None
        result_holder['error'] = str(e)

def test_get_version():
    print("\n=== Test GetVersion ===")
    data = bytes([0x00])
    resp = send_apdu(apdu_hex(0x00, 0x00, 0x00, 0x00, data))
    sw = (resp[-2] << 8) | resp[-1]
    if sw == 0x9000 and resp[0] == 0x01:
        major, minor, patch = resp[1], resp[2], resp[3]
        name = resp[4:-2].decode('utf-8', errors='replace')
        print(f"  Version: {major}.{minor}.{patch} \"{name}\"")
        return True
    print(f"  FAILED SW=0x{sw:04x}")
    return False

def test_get_pubkey():
    print("\n=== Test GetPubkey ===")
    path = serialize_path("44'/635'/0/0")
    path_hash, path_chunks = build_chunked_param(path)

    start_data = bytes([0x00]) + path_hash
    resp = send_apdu(apdu_hex(0x00, 0x02, 0x00, 0x00, start_data))
    sw = (resp[-2] << 8) | resp[-1]
    if sw != 0x9000:
        print(f"  ERROR: START failed SW=0x{sw:04x}")
        return None, None

    requested_hash = to_hex(resp[1:33])
    chunk = path_chunks[requested_hash]
    chunk_data = bytes([0x01]) + chunk
    resp = send_apdu(apdu_hex(0x00, 0x02, 0x00, 0x00, chunk_data))
    sw = (resp[-2] << 8) | resp[-1]
    if sw != 0x9000 or resp[0] != 0x01:
        print(f"  ERROR: failed SW=0x{sw:04x}")
        return None, None

    result = resp[1:-2]
    key_len = result[0]
    pub_key = result[1:1+key_len]
    addr_len = result[1+key_len]
    addr = result[2+key_len:2+key_len+addr_len]

    pub_key_hex = to_hex(pub_key)
    addr_hex = to_hex(addr)
    expected_addr = to_hex(sha256(pub_key)[:20])

    print(f"  Public key: {pub_key_hex}")
    print(f"  Address:    {addr_hex}")
    print(f"  Match:      {addr_hex == expected_addr}")
    return pub_key_hex, addr_hex

def test_blind_sign():
    print("\n=== Test BlindSign ===")

    txn_obj = {"type": "pocket_ownership_proof", "test": True}
    txn_json = json.dumps(txn_obj, separators=(',', ':'))
    txn_bytes = txn_json.encode('utf-8')
    print(f"  JSON: {txn_json} ({len(txn_bytes)} bytes)")

    txn_payload = u32le(len(txn_bytes)) + txn_bytes
    path_payload = serialize_path("44'/635'/0/0")

    txn_hash, txn_chunks = build_chunked_param(txn_payload)
    path_hash, path_chunks = build_chunked_param(path_payload)

    all_chunks = {}
    all_chunks.update(txn_chunks)
    all_chunks.update(path_chunks)

    txn_hash_hex = to_hex(txn_hash)
    path_hash_hex = to_hex(path_hash)
    print(f"  Txn hash:  {txn_hash_hex[:16]}...")
    print(f"  Path hash: {path_hash_hex[:16]}...")

    # Step 0: START
    start_data = bytes([0x00]) + txn_hash + path_hash
    print(f"\n  Step 0: START")
    resp = send_apdu(apdu_hex(0x00, 0x04, 0x00, 0x00, start_data))
    sw = (resp[-2] << 8) | resp[-1]
    print(f"    SW: 0x{sw:04x}")
    if sw != 0x9000:
        print(f"  ERROR: START failed")
        return None

    tag = resp[0]
    if tag != 0x02:
        print(f"  ERROR: Expected GetChunk, got 0x{tag:02x}")
        return None

    rh = to_hex(resp[1:33])
    print(f"    GetChunk: {rh[:16]}... ({'PATH' if rh == path_hash_hex else 'TXN'})")

    # Step 1: Send PATH chunk
    # This will BLOCK because the app shows WARNING and Sign for Address scrollers
    print(f"\n  Step 1: Sending PATH chunk (will block for UI prompts)")
    chunk = all_chunks[rh]
    chunk_hex = apdu_hex(0x00, 0x04, 0x00, 0x00, bytes([0x01]) + chunk)

    delete_events()
    result1 = {}
    t1 = threading.Thread(target=send_apdu_in_thread, args=(chunk_hex, result1, 60))
    t1.start()

    # Press buttons to approve the WARNING and Sign for Address prompts
    print("    Approving prompts...")
    auto_approve_blind_sign_prompts()

    t1.join(timeout=15)
    if not t1.is_alive() and result1.get('response'):
        resp = result1['response']
        sw = (resp[-2] << 8) | resp[-1]
        print(f"    SW: 0x{sw:04x}")
        if sw != 0x9000:
            print(f"  ERROR: PATH chunk failed")
            events = http_get(f"{BASE_URL}/events").get("events", [])
            for e in events[-10:]:
                print(f"    text='{e.get('text','')}' y={e.get('y','')}")
            return None
    else:
        print(f"  ERROR: PATH chunk timed out or failed")
        print(f"  Error: {result1.get('error')}")
        return None

    tag = resp[0]
    if tag != 0x02:
        print(f"  ERROR: Expected GetChunk, got 0x{tag:02x}")
        return None
    rh = to_hex(resp[1:33])
    print(f"    GetChunk: {rh[:16]}... ({'TXN' if rh == txn_hash_hex else 'PATH'})")

    # Step 2: Send TXN chunk (first pass - should NOT block for UI)
    print(f"\n  Step 2: Sending TXN chunk (first pass)")
    chunk = all_chunks[rh]
    resp = send_apdu(apdu_hex(0x00, 0x04, 0x00, 0x00, bytes([0x01]) + chunk))
    sw = (resp[-2] << 8) | resp[-1]
    print(f"    SW: 0x{sw:04x}")
    if sw != 0x9000:
        print(f"  ERROR: TXN chunk (first pass) failed")
        return None

    tag = resp[0]
    if tag == 0x01:
        print(f"  Unexpected: ResultFinal already returned")
        result = resp[1:-2]
        return to_hex(result[:64]), txn_bytes

    if tag != 0x02:
        print(f"  ERROR: Expected GetChunk, got 0x{tag:02x}")
        return None
    rh = to_hex(resp[1:33])
    print(f"    GetChunk: {rh[:16]}... ({'TXN' if rh == txn_hash_hex else 'PATH'})")

    # Step 3: Send TXN chunk (second pass)
    # This will BLOCK because "Blind Sign Transaction?" prompt appears AFTER parsing
    print(f"\n  Step 3: Sending TXN chunk (second pass, will block for confirm)")
    chunk = all_chunks[rh]
    chunk_hex = apdu_hex(0x00, 0x04, 0x00, 0x00, bytes([0x01]) + chunk)

    delete_events()
    result3 = {}
    t3 = threading.Thread(target=send_apdu_in_thread, args=(chunk_hex, result3, 60))
    t3.start()

    # Wait for and approve the "Blind Sign Transaction?" + "Confirm" prompt
    time.sleep(0.3)
    print("    Waiting for Blind Sign Transaction? prompt...")

    # Press right to advance past "Blind Sign Transaction?" to "Confirm"
    # Then press both to accept
    max_attempts = 20
    approved = False
    for i in range(max_attempts):
        texts = get_current_screen_text()
        if "Confirm" in texts:
            time.sleep(0.1)
            press_button("both")
            print("    Pressed BOTH on Confirm")
            approved = True
            break
        if any("Blind Sign" in t for t in texts) or any("Transaction" in t for t in texts):
            press_button("right")
            time.sleep(0.15)
            continue
        # Just press right to advance
        press_button("right")
        time.sleep(0.2)

    if not approved:
        # Try one more: check if we're on Reject, go left to Confirm
        texts = get_current_screen_text()
        if "Reject" in texts:
            press_button("left")
            time.sleep(0.2)
            press_button("both")
            print("    Pressed BOTH on Confirm (via left from Reject)")
            approved = True

    t3.join(timeout=15)
    if not t3.is_alive() and result3.get('response'):
        resp = result3['response']
        sw = (resp[-2] << 8) | resp[-1]
        print(f"    SW: 0x{sw:04x}")
        if sw != 0x9000:
            print(f"  ERROR: TXN chunk (second pass) failed")
            events = http_get(f"{BASE_URL}/events").get("events", [])
            for e in events[-10:]:
                print(f"    text='{e.get('text','')}' y={e.get('y','')}")
            return None
    else:
        print(f"  ERROR: TXN chunk (second pass) timed out or failed")
        print(f"  Error: {result3.get('error')}")
        return None

    tag = resp[0]
    if tag != 0x01:
        print(f"  ERROR: Expected ResultFinal, got 0x{tag:02x}")
        return None

    result = resp[1:-2]
    sig_hex = to_hex(result[:64])
    print(f"\n  SUCCESS: Signature = {sig_hex}")
    return sig_hex, txn_bytes

def main():
    try:
        http_get(f"{BASE_URL}/events")
        print("Speculos is running.")
    except:
        print("ERROR: Speculos not reachable at", BASE_URL)
        sys.exit(1)

    # Clear automation - we'll handle buttons manually via threads
    clear_automation()
    delete_events()
    time.sleep(0.3)

    # Enable blind signing
    print("\n=== Enabling Blind Signing ===")
    toggle_blind_signing()
    time.sleep(0.5)

    events = http_get(f"{BASE_URL}/events").get("events", [])
    texts = [e.get("text", "") for e in events]
    if "Enabled" in texts:
        print("  Blind signing: ENABLED")
    else:
        print("  Toggling again...")
        toggle_blind_signing()
        time.sleep(0.5)
        events = http_get(f"{BASE_URL}/events").get("events", [])
        texts = [e.get("text", "") for e in events]
        if "Enabled" in texts:
            print("  Blind signing: ENABLED")
        else:
            print("  WARNING: Cannot confirm state")

    delete_events()
    time.sleep(0.3)

    # Test GetVersion (no UI prompts needed)
    test_get_version()

    # Test GetPubkey (no UI prompts for INS_GET_PUBKEY with PROMPT=false)
    pub_key_hex, addr_hex = test_get_pubkey()
    if not pub_key_hex:
        print("\nGetPubkey failed")
        sys.exit(1)

    delete_events()
    time.sleep(0.3)

    # Test BlindSign (with threaded button handling)
    result = test_blind_sign()

    if result:
        sig_hex, txn_bytes = result
        print(f"\n{'='*50}")
        print(f"BLIND SIGN SUCCESS!")
        print(f"{'='*50}")
        print(f"  Public key: {pub_key_hex}")
        print(f"  Address:    {addr_hex}")
        print(f"  Signature:  {sig_hex}")

        # Verify signature
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_key_hex))
            pk.verify(bytes.fromhex(sig_hex), txn_bytes)
            print("  Sig verify: PASSED")
        except ImportError:
            print("  (install 'cryptography' for sig verification)")
        except Exception as e:
            print(f"  Sig verify: FAILED - {e}")
    else:
        print(f"\n{'='*50}")
        print(f"BLIND SIGN FAILED")
        print(f"{'='*50}")
        events = http_get(f"{BASE_URL}/events").get("events", [])
        print(f"\nAll events ({len(events)}):")
        for i, e in enumerate(events):
            print(f"  [{i}] text='{e.get('text','')}' y={e.get('y','')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
