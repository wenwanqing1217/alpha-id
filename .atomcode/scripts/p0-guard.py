"""
P0 Scope Guard — PreToolUse 拦截检查
在每次编辑前检查涉及的文件/内容是否触及 P0 禁止清单。
如果命中，打印警告并要求确认。
"""
import re
import sys

# P0 禁止清单（正则匹配）
P1_PATTERNS = [
    r"MCP.*inject",
    r"\ba2a\b",
    r"\bvoice\b",
    r"\bspeech\b",
    r"html.*particle",
    r"safety.*layer",
    r"export_card",
    r"cursor.*collector",
    r"A2A.*protocol",
    r"Plan.*Safety.*layer",
]

def check_file(filepath: str) -> list[str]:
    """检查文件内容是否包含 P1 模式"""
    hits = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            for pattern in P1_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    hits.append(pattern)
    except (FileNotFoundError, PermissionError):
        pass
    return hits

def main():
    args = " ".join(sys.argv[1:])
    # 从参数中提取文件路径
    paths = re.findall(r'[\w\\/:.\-]+\.py', args)
    paths += re.findall(r'[\w\\/:.\-]+\.md', args)
    
    all_hits = []
    for p in paths:
        hits = check_file(p)
        all_hits.extend(hits)
    
    if all_hits:
        print("=" * 60)
        print("⚠️  P0 范围守卫警告 ⚠️")
        print("=" * 60)
        print(f"检测到以下 P1 领域内容：")
        for h in sorted(set(all_hits)):
            print(f"  🔴 {h}")
        print()
        print("P0 禁止修改以下领域：")
        print("  MCP 身份注入  |  A2A 协议  |  语音交互")
        print("  HTML 粒子星链 |  Safety 层 |  Cursor 采集器")
        print()
        print("如果你确实需要修改这些，请先确认是否已进入 P1 阶段。")
        print("=" * 60)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
