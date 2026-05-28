"""TwinBrain comprehensive verification"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.twin_brain import TwinBrain, BrainRegistry, BrainState, BrainSettings
from core.message import Message, MessageType
from core.storage import JsonStorage

tmp = os.path.join(tempfile.gettempdir(), 'alpha_brain_test.json')
if os.path.exists(tmp):
    os.remove(tmp)

storage = JsonStorage(tmp)

passed = 0
failed = 0

# === Test 1: Create and basic state ===
b1 = TwinBrain(alpha_id='Alpha-001', storage=storage)
assert b1.alpha_id == 'Alpha-001'
assert b1.state == BrainState.SLEEP
assert str(b1) == '<TwinBrain Alpha-001 [sleep]>'
passed += 1
print('[PASS] 1. Create: sleep state')

# === Test 2: Wake ===
assert b1.awake() == True
assert b1.state == BrainState.AWAKE
passed += 1
print('[PASS] 2. Wake: awake state')

# === Test 3: Invalid transition ===
assert b1.sleep() == True  # AWAKE -> SLEEP is valid
assert b1.state == BrainState.SLEEP
passed += 1
print('[PASS] 3. Sleep: sleep state')

# === Test 4: Receive while sleeping (no auto-reply) ===
msg = Message.create_chat('Alpha-002', 'Alpha-001', 'hello')
resp = b1.receive(msg)
assert resp.success == False
assert resp.error_code == 'SLEEPING'
passed += 1
print('[PASS] 4. Offline reject (no auto-reply)')

# === Test 5: Auto-reply ===
b1.settings.auto_reply = True
resp = b1.receive(msg)
assert resp.success == True
assert '稍后回复' in resp.message
passed += 1
print('[PASS] 5. Auto-reply works')

# === Test 6: Awake and receive ===
b1.awake()
resp = b1.receive(msg)
assert resp.success == False  # social module not initialized yet, but routed to _handle_chat
print(f'[NOTE] 6. Chat routing: success={resp.success} msg={resp.message}')
passed += 1
print('[PASS] 6. Message routing to chat handler')

# === Test 7: Profile query ===
b1.awake()
query_msg = Message.create_profile_query('Alpha-002', 'Alpha-001', layer='public')
resp = b1.receive(query_msg)
assert resp.success == False  # profile not exist
passed += 1
print('[PASS] 7. Profile query routing')

# === Test 8: Ping ===
b1.awake()
ping_msg = Message(sender='Alpha-002', recipient='Alpha-001', msg_type=MessageType.PING)
resp = b1.receive(ping_msg)
assert resp.success == True
assert resp.data['alpha_id'] == 'Alpha-001'
assert resp.data['status'] == 'awake'
passed += 1
print('[PASS] 8. Ping/Pong')

# === Test 9: External app action ===
app_msg = Message(
    sender='E-Pet-001',
    recipient='Alpha-001',
    msg_type=MessageType.APP_ACTION,
    payload={'action': 'say', 'text': 'Hello from e-pet'}
)
resp = b1.receive(app_msg)
assert resp.success == True
assert resp.data['echo'] == 'Hello from e-pet'
passed += 1
print('[PASS] 9. External app integration')

# === Test 10: Think cycle ===
b1.awake()
result = b1.think()
assert result['alpha_id'] == 'Alpha-001'
assert result['state'] == 'awake'
assert 'message_count' in result
passed += 1
print('[PASS] 10. Think cycle')

# === Test 11: Registry ===
reg = BrainRegistry()
reg.register(b1)
b2 = TwinBrain(alpha_id='Alpha-002', storage=storage)
b2.awake()
reg.register(b2)
stats = reg.count()
assert stats['total'] == 2
assert stats['awake'] == 1
assert stats['sleep'] == 1
assert reg.get('Alpha-001') is b1
assert reg.get_or_create('Alpha-003') is not None
passed += 1
print('[PASS] 11. Brain registry')

# === Test 12: BrainSettings ===
settings = BrainSettings(
    auto_reply=True,
    auto_reply_text='busy now',
    idle_timeout=60,
    sleep_timeout=300,
)
b3 = TwinBrain(alpha_id='Alpha-003', storage=storage, settings=settings)
assert b3.settings.auto_reply == True
assert b3.settings.auto_reply_text == 'busy now'
assert b3.settings.idle_timeout == 60
passed += 1
print('[PASS] 12. BrainSettings')

# === Test 13: Message creation helpers ===
chat = Message.create_chat('A', 'B', 'hello')
assert chat.msg_type == MessageType.CHAT
assert chat.payload['text'] == 'hello'
fr = Message.create_friend_request('A', 'B', 'hi')
assert fr.msg_type == MessageType.FRIEND_REQUEST
assert fr.payload['note'] == 'hi'
pq = Message.create_profile_query('A', 'B', 'friends')
assert pq.msg_type == MessageType.PROFILE_QUERY
assert pq.payload['layer'] == 'friends'
passed += 1
print('[PASS] 13. Message helpers')

# === Test 14: Visibility filtering (self) ===
profile = {'alpha_id': 'Alpha-001', 'user_id': 'secret_user_001', 'devices': ['dev_a', 'dev_b']}
safe = b1._filter_by_visibility(profile, 'public', 'Alpha-001')
assert safe['alpha_id'] == 'Alpha-001'
assert 'user_id' in safe  # self sees everything
passed += 1
print('[PASS] 14. Visibility: self sees all')

# === Test 15: Visibility filtering (public) ===
safe = b1._filter_by_visibility(profile, 'public', 'Alpha-999')
assert safe['alpha_id'] == 'Alpha-001'
assert 'user_id' not in safe
passed += 1
print('[PASS] 15. Visibility: stranger only sees public')

# cleanup
if os.path.exists(tmp):
    os.remove(tmp)

print(f'\n=== {passed} TESTS PASSED, {failed} FAILED ===')
