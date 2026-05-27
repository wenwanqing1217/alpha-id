from langchain.tools import tool
from langchain.tools import ToolRuntime
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_dev_sdk import LLMClient
from langchain_core.messages import HumanMessage
import json


@tool
def ocr_recognize_payment(image_url: str, runtime: ToolRuntime = None) -> str:
    """
    识别支付截图中的消费信息。

    参数:
        image_url: 支付截图的URL地址

    返回:
        JSON格式的消费信息，包含：
        - amount: 金额（数字）
        - merchant: 商户名称
        - category: 消费分类（餐饮/交通/购物/娱乐/医疗/教育/居住/通讯/其他）
        - payment_method: 支付方式（微信/支付宝/银行卡/现金等）
        - description: 备注说明
        - expense_date: 消费时间（YYYY-MM-DD HH:mm:ss格式）
    """
    ctx = runtime.context if runtime else new_context(method="ocr_recognize_payment")

    client = LLMClient(ctx=ctx)

    prompt = """你是一个专业的支付信息识别助手。请仔细分析这张支付截图，提取出以下信息：

1. **消费金额**：提取准确的数字金额
2. **商户名称**：支付对象的名称
3. **消费时间**：支付发生的具体时间
4. **支付方式**：微信/支付宝/银行卡/现金等
5. **消费分类**：根据商户名称和消费内容，归类为以下之一：
   - 餐饮：奶茶、咖啡、餐厅、外卖、超市食品等
   - 交通：打车、地铁、公交、加油、停车等
   - 购物：服装、日用品、电子产品、网购等
   - 娱乐：电影、游戏、会员、旅游等
   - 医疗：药店、医院、体检等
   - 教育：书籍、课程、培训等
   - 居住：房租、水电、物业等
   - 通讯：话费、流量、宽带等
   - 其他：无法归类的消费

请以纯JSON格式返回，不要包含任何其他文字。格式如下：
{
  "amount": 12.50,
  "merchant": "星巴克咖啡",
  "category": "餐饮",
  "payment_method": "微信支付",
  "description": "拿铁咖啡",
  "expense_date": "2025-06-18 10:30:00"
}

如果某些信息无法识别，对应的字段设为null。"""

    messages = [
        HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ])
    ]

    try:
        response = client.invoke(
            messages=messages,
            model="doubao-seed-1-6-vision-250815",
            temperature=0.1
        )

        # 提取文本内容
        content = response.content
        if isinstance(content, list):
            # 处理多模态响应
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)

        # 清理并解析JSON
        if isinstance(content, str):
            # 移除可能的markdown代码块标记
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # 尝试提取JSON部分（如果模型返回了额外文字）
            if "{" in content and "}" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]

            result = json.loads(content)
            return json.dumps(result, ensure_ascii=False)
        else:
            return json.dumps({"error": f"无法解析响应，类型：{type(content)}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"识别失败: {str(e)}"}, ensure_ascii=False)
