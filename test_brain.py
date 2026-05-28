"""TwinBrain 快速验证"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.twin_brain import TwinBrain, BrainRegistry, BrainState
from core.message import Message, MessageType

b1 = TwinBrain(alpha_id='Alpha-001')
print('[1] 创建:', b1, '状态:', b1.state.value)

b1.awake()
print('[2] 唤醒:', b1.state.value)

msg = Message.create_chat('Alpha-002', 'Alpha-001', '你好！')
r = b1.receive(msg)
print('[3] 消息接收:', r.success, r.message)

b1.sleep()
print('[4] 休眠:', b1.state.value)

reg = BrainRegistry()
reg.register(b1)
b2 = TwinBrain(alpha_id='Alpha-002')
b2.awake()
reg.register(b2)
print('[5] 注册表统计:', reg.count())

# 离线回复
offline_msg = Message.create_chat('Alpha-003', 'Alpha-001', '在吗？')
r2 = b1.receive(offline_msg)
print('[6] 离线回复:', r2.success, r2.message)

# 自动回复
b1.settings.auto_reply = True
r3 = b1.receive(offline_msg)
print('[7] 自动回复:', r3.success, r3.message)

# 外部应用
app_msg = Message(
    sender='E-Pet-001', recipient='Alpha-001',
    msg_type=MessageType.APP_ACTION,
    payload={'action': 'say', 'text': '你好！'}
)
b1.awake()
r4 = b1.receive(app_msg)
print('[8] 外部应用:', r4.success, r4.data)

# 好友请求
friend_msg = Message.create_friend_request('Alpha-002', 'Alpha-001', '加个好友')
b1.awake()
r5 = b1.receive(friend_msg)
print('[9] 好友请求:', r5.success, r5.message)

print()
print('=== 全部测试通过 ===')
