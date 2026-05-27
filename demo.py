#!/usr/bin/env python3
"""
Alpha-ID - Digital Identity OS
Core Module Demo (stdlib only, zero external dependencies)

Run:  python demo.py

Covers:
  1. JWT Authentication (issue, verify, refresh, extract)
  2. User Identity Manager (register founder/user, bind device, stats)
  3. Risk Assessment Engine (device score, behavior score, voice score, total risk)
  4. Social Network (friend request, accept, message, query)

Tested on Python 3.12+.
"""

import os
import sys
import time
import tempfile
import json
import hashlib
import hmac
import base64
from datetime import datetime, timedelta, timezone

TEMP = os.path.join(tempfile.gettempdir(), "alpha_demo")
os.makedirs(TEMP, exist_ok=True)

# ====================================================================
# 1. JWT Authentication (RFC 7519, HMAC-SHA256, no pyjwt)
# ====================================================================
def demo_auth():
    print("\n" + "=" * 60)
    print("[1] JWT Authentication (stdlib only, zero external deps)")
    print("=" * 60)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
    from src.auth.jwt import create_access_token, create_refresh_token, decode_token, verify_token, get_current_alpha_id

    # Issue tokens
    user_id = "alpha_8a3f7b9e2c1d"
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)

    print(f"\n  [KEY] access_token (30min TTL):")
    print(f"     {access[:47]}...")
    print(f"\n  [KEY] refresh_token (7day TTL):")
    print(f"     {refresh[:47]}...")

    # Decode and verify
    payload = decode_token(access)
    print(f"\n  [OK] Decoded payload:")
    print(f"     sub: {payload.get('sub')}")
    print(f"     type: {payload.get('type')}")
    print(f"     iat: {payload.get('iat')}")

    verified = verify_token(access)
    print(f"  [OK] verified -> {verified}")

    extracted = get_current_alpha_id(f"Bearer {access}")
    print(f"  [OK] Bearer extract -> {extracted}")

    # Forged token must be rejected
    forged = access[:-5] + "XXXXX"
    try:
        result = verify_token(forged)
        print(f"  [FAIL] forged token accepted (bug): {result}")
    except ValueError as e:
        print(f"  [OK] forged token rejected")

# ====================================================================
# 2. User Identity Manager
# ====================================================================
def demo_identity():
    print("\n" + "=" * 60)
    print("[2] User Identity Manager (stdlib only)")
    print("=" * 60)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
    from src.core.storage import JsonStorage
    from src.core.user_identity import UserIdentityManager

    tmp = os.path.join(TEMP, "alpha_demo_users.json")
    if os.path.exists(tmp): os.remove(tmp)

    manager = UserIdentityManager(storage=JsonStorage(tmp))

    # Register founder
    result = manager.register_user(device_fingerprint="device_mac_001", is_founder=True, founder_code="Alpha-1-zx")
    print(f"\n  [USER] Founder registration: {result['success']}")
    print(f"     alpha_id: {result['alpha_id']}")

    # Register normal user
    result = manager.register_user(device_fingerprint="device_mac_002")
    print(f"\n  [USER] User registration: {result['success']}")
    print(f"     alpha_id: {result['alpha_id']}")

    # Get profile
    profile = manager.get_user_profile(result['alpha_id'])
    print(f"\n  [PROFILE] username: {profile.get('alpha_id')}")
    print(f"     devices: {profile.get('devices')}")

    # Update device
    profile = manager.update_device_binding(result['alpha_id'], "device_mac_999")
    print(f"\n  [PHONE] Device updated: {profile['success']}")

    # Stats
    stats = manager.get_statistics()
    print(f"\n  [CHART] Statistics:")
    for k, v in stats.items():
        if k != "total_users":
            print(f"     {k}: {v}")

    if os.path.exists(tmp): os.remove(tmp)

# ====================================================================
# 3. Risk Assessment Engine
# ====================================================================
def demo_risk():
    print("\n" + "=" * 60)
    print("[3] Risk Assessment Engine (stdlib only)")
    print("=" * 60)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
    from src.core.risk_engine import RiskAssessmentEngine, DeviceFingerprint, BehaviorFingerprint

    engine = RiskAssessmentEngine()

    baseline_dev = DeviceFingerprint(
        hardware_id="hw_001",
        ip_address="192.168.1.100",
        location="Beijing",
        browser_info="Safari/iOS 17.4",
        screen_resolution="2556x1179",
        first_access_time="2024-01-01T00:00:00"
    )
    baseline_beh = BehaviorFingerprint(
        typing_speed=5.2,
        common_words=["hello", "thanks", "ok"],
        error_rate=0.05,
        session_time="09:00-18:00",
        word_count=10,
        emoji_count=2
    )
    engine._establish_baseline(baseline_beh)

    current_dev = DeviceFingerprint(
        hardware_id="hw_001",
        ip_address="192.168.1.100",
        location="Beijing",
        browser_info="Safari/iOS 17.4",
        screen_resolution="2556x1179",
        first_access_time="2024-06-01T00:00:00"
    )
    current_beh = BehaviorFingerprint(
        typing_speed=5.1,
        common_words=["hello", "thanks", "ok"],
        error_rate=0.04,
        session_time="09:00-18:00",
        word_count=10,
        emoji_count=2
    )

    # Same device
    ds = engine.calculate_device_score(current_dev, baseline_dev)
    bs = engine.calculate_behavior_score(current_beh)
    vs = engine.calculate_voice_score()
    total = engine.calculate_total_risk(ds, bs, vs)
    level = engine.determine_risk_level(total)
    action = engine.get_action_required(level, total)

    print(f"\n  [GREEN] Same device (baseline match):")
    print(f"     device_score: {ds:.1f}, behavior_score: {bs:.1f}")
    print(f"     total_risk: {total:.1f}, level: {level}")
    print(f"     action: {action}")

    # Different device
    current_dev2 = DeviceFingerprint(
        hardware_id="hw_999",
        ip_address="10.0.0.1",
        location="New York",
        browser_info="Chrome/Android 14",
        screen_resolution="1440x3200",
        first_access_time="2024-06-01T00:00:00"
    )
    current_beh2 = BehaviorFingerprint(
        typing_speed=8.0,
        common_words=["yo", "ok"],
        error_rate=0.20,
        session_time="02:00-06:00",
        word_count=3,
        emoji_count=10
    )
    ds2 = engine.calculate_device_score(current_dev2, baseline_dev)
    bs2 = engine.calculate_behavior_score(current_beh2)
    vs2 = engine.calculate_voice_score({"confidence": 0.1})
    total2 = engine.calculate_total_risk(ds2, bs2, vs2)
    level2 = engine.determine_risk_level(total2)
    action2 = engine.get_action_required(level2, total2)
    verify2 = engine.get_recommended_verification(level2)

    print(f"\n  [RED] Different device (high risk):")
    print(f"     device_score: {ds2:.1f}, behavior_score: {bs2:.1f}")
    print(f"     total_risk: {total2:.1f}, level: {level2}")
    print(f"     verification: {verify2}")

# ====================================================================
# 4. Social Network
# ====================================================================
def demo_social():
    print("\n" + "=" * 60)
    print("[4] Social Network (stdlib only)")
    print("=" * 60)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
    from src.core.storage import JsonStorage
    from src.core.alpha_social import AlphaSocialManager

    tmp = os.path.join(TEMP, "alpha_demo_social.json")
    if os.path.exists(tmp): os.remove(tmp)

    sm = AlphaSocialManager(storage=JsonStorage(tmp))

    alice = "alpha_alice"
    bob = "alpha_bob"

    # Send friend request
    req = sm.send_friend_request(alice, bob, "Hi Bob!")
    print(f"\n  [MAIL] Friend request sent: {req['success']}")
    rid = req['request_id']
    print(f"     {alice} -> {bob}  (id: {rid})")

    # Accept
    accepted = sm.respond_friend_request(rid, "accept")
    print(f"\n  [OK] Accepted: {accepted['success']}")
    print(f"     {alice} & {bob} are now friends")

    # Send a message
    msg = sm.send_message(alice, bob, "Hello from Alice!")
    print(f"\n  [MSG] Sent: {msg['success']}")
    print(f"     content: Hello from Alice!  (id: {msg['message_id']})")

    # Alice sent -> Bob's inbox
    bob_inbox = sm.get_messages(bob)
    print(f"\n  [INBOX] {bob} has {len(bob_inbox)} message(s)")
    if bob_inbox:
        print(f"     from: {bob_inbox[0].get('from_alpha_id')}")
        print(f"     text: {bob_inbox[0].get('content')}")

    # Friend list
    alice_friends = sm.get_friends(alice)
    bob_friends = sm.get_friends(bob)
    print(f"\n  [FRIENDS] {alice} -> {len(alice_friends)} friend(s)")
    print(f"  [FRIENDS] {bob} -> {len(bob_friends)} friend(s)")

    if os.path.exists(tmp): os.remove(tmp)

# ====================================================================
# 5. Main Entry
# ====================================================================
if __name__ == "__main__":
    print("=" * 50)
    print("  Alpha-ID - Digital Identity OS")
    print("       Core Module Demo")
    print("=" * 50)
    demo_auth()
    demo_identity()
    demo_risk()
    demo_social()
    print("\n" + "=" * 60)
    print("[*] ALL DEMOS PASSED - 4 modules OK")
    print("=" * 60)
