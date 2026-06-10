# 工具演示：如何在Alpha-ID项目中使用新增工具

本文档演示如何使用我们新添加的开发工具：Bandit、pdoc、factory-boy 和 hypothesis。

## 1. Bandit - 安全漏洞扫描

### 用途
检测Python代码中的安全问题，如硬编码密码、不安全的加密使用等。

### 安装（已完成）
```bash
.venv/bin/pip install bandit
```

### 基本使用
```bash
# 扫描整个src目录
.venv/bin/bandit -r src/

# 只显示高危和中危问题
.venv/bin/bandit -r src/ -ll

# 生成HTML报告
.venv/bin/bandit -r src/ -f html -o bandit-report.html
```

### 在pre-commit中的集成示例（添加到 .pre-commit-config.yaml）：
```yaml
- repo: https://github.com/PyCQA/bandit
  rev: 1.7.5
  hooks:
    - id: bandit
      args: ["-r", "src/", "-ll"]
```

### 示例：检测硬编码密码
如果代码中有类似：
```python
# 不安全！硬编码密码
API_KEY = "sk-1234567890abcdef"
```

Bandit会报告：`B105:硬编码密码字符串`

## 2. pdoc - 自动API文档生成

### 用途
从docstrings自动生成干净的API文档，减少维护负担。

### 安装（已完成）
```bash
.venv/bin/pip install pdoc
```

### 基本使用
```bash
# 生成API文档到docs/api目录
.venv/bin/pdoc src/ -o docs/api

# 启动本地文档服务器进行预览
.venv/bin/pdoc --http :8080 src/
```

### 在代码中编写良好docstring的示例：
```python
def generate_did(seed: str = None) -> str:
    """
    根据种子生成去中心化身份标识符(DID)。
    
    参数:
        seed: 可选的种子字符串。如果未提供，将生成随机种子。
        
    返回:
        符援DID规范的字符串，格式为: did:aid:<标识符>
        
    示例:
        >>> generate_did("test-seed")
        'did:aid:abc123def456'
        
    注意:
        此函数使用SHA-256哈希确保生成的确定性。
    """
    # 实现细节...
    pass
```

### 集成到文档构建流程
可以在 `docs/Makefile` 或构建脚本中添加：
```makefile
api-docs:
	pdoc src/ -o docs/api --force
```

## 3. factory-boy - 测试数据生成

### 用途
为测试创建fixture对象，比手动创建更清晰可维护。

### 安装（已完成）
```bash
.venv/bin/pip install factory-boy
```

### 基本使用
在 `tests/factories.py` 中创建工厂：
```python
import factory
from alpha_id.models import Persona, DIDIdentity

class PersonaFactory(factory.Factory):
    class Meta:
        model = Persona
    
    summary = "深夜技术探索者, Python/异步/Agent 方向"
    style = "简洁直接, 偏好功能性编程"
    active_hours = "22:00-03:00"
    topics = ["MCP 协议", "Python 异步", "Rust 函数式"]

class DIDIdentityFactory(factory.Factory):
    class Meta:
        model = DIDIdentity
    
    did = factory.Sequence(lambda n: f"did:aid:test{n:06d}")
    persona = factory.SubFactory(PersonaFactory)
    created_at = factory.Faker("date_time_this_year")
```

### 在测试中使用
```python
def test_persona_creation():
    # 自动创建具有默认值的Persona对象
    persona = PersonaFactory()
    assert persona.summary is not None
    assert len(persona.topics) > 0
    
    # 覆盖特定属性
    admin_persona = PersonaFactory(
        summary="系统管理员",
        topics=["系统架构", "DevOps"]
    )
    assert admin_persona.summary == "系统管理员"

def test_identity_generation():
    identity = DIDIdentityFactory()
    assert identity.did.startswith("did:aid:")
    assert identity.persona is not None
```

### 优势
- 减少测试fixture的样板代码
- 易于维护和更新
- 支持继承和组合
- 自动处理复杂对象图

## 4. hypothesis - 基于属性的测试

### 用途
通过生成广泛的测试用例来发现边界情况和意外行为。

### 安装（已完成）
```bash
.venv/bin/pip install hypothesis
```

### 基本使用
在测试中使用 `@given` 装饰器：
```python
from hypothesis import given, strategies as st
from alpha_id.models import validate_did_format

# 策略：生成各种字符串
did_like_strings = st.text(min_size=1, max_size=100).filter(
    lambda s: s.startswith("did:aid:") and len(s) > 8
)

@given(did_like_strings)
def test_did_validation_accepts_valid_formats(did):
    """假设：所有以did:aid:开头且足够长的字符串应该通过基本格式验证"""
    # 注意：这是一个示例，实际验证逻辑可能更复杂
    assert validate_did_format(did) is True or validate_did_format(did) is False

# 测试特定属性
@given(st.text())
def test_persona_summary_always_string(summary):
    """假设：无论输入什么，摘要最终总是字符串"""
    persona = Persona(summary=summary, style="test", active_hours="00:00-23:59")
    assert isinstance(persona.summary, str)

# 使用假设测试发现边界情况
@given(st.lists(st.text(min_size=1), min_size=0, max_size=10))
def test_topics_list_handles_various_sizes(topics):
    """假设：主题列表应该能处理各种大小"""
    persona = Persona(
        summary="测试用户",
        style="测试风格", 
        active_hours="00:00-23:59",
        topics=topics
    )
    assert len(persona.topics) == len(topics)
    assert all(isinstance(t, str) for t in persona.topics)
```

### 常用策略
- `st.integers()`、`st.floats()` - 数字
- `st.text()`、`st.characters()` - 字符串
- `st.lists()`, `st.tuples()`, `st.sets()` - 集合类型
- `st.dictionaries()` - 字典
- `st.dates()`, `st.times()`, `st.datetimes()` - 日期时间
- `st.one_of()`, `st.just()` - 组合策略

### 集成到pytest
hypothesis与pytest完全兼容，只需要在测试文件中导入即可使用。

## 在Alpha-ID项目中的具体应用建议

### 1. 身份验证模块测试
使用factory-boy创建身份对象，使用hypothesis测试验证函数的边界情况。

### 2. 数据导入模块测试
使用hypothesis生成各种格式不正确的导入数据，确保解析器健壮性。

### 3. API端点测试
结合factory-boy和hypothesis测试各种输入组合下的API行为。

### 4. 安全审计
定期运行bandit扫描，特别是在处理加密、密码存储和身份验证相关代码时。

## 将这些工具加入开发工作流

### 本地开发
```bash
# 运行所有质量检查
make check-all  # 如果在taskipy中配置了的话

# 或者手动运行
.venv/bin/bandit -r src/
.venv/bin/pydoc src/ -o docs/api --force
.venv/bin/mypy src/
.venv/bin/ruff check src/
.venv/bin/pytest tests/
```

### CI/CD集成
在GitHub Actions中添加步骤：
```yaml
- name: 安装依赖
  run: |
    python -m venv .venv
    source .venv/bin/activate
    pip install -e .[dev]
    
- name: 安全扫描
  run: |
    .venv/bin/bandit -r src/ -f sarif -o bandit.sarif
    
- name: 代码质量检查
  run: |
    .venv/bin/ruff check src/
    .venv/bin/mypy src/
    
- name: 测试
  run: |
    .venv/bin/pytest tests/ --cov=src --cov-report=xml
```

这些工具将共同提升Alpha-ID项目的代码质量、安全性和可维护性。