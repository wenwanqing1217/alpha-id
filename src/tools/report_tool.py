from langchain.tools import tool
from langchain.tools import ToolRuntime
from storage.database.supabase_client import get_supabase_client
from datetime import datetime, timedelta
from typing import Any, Dict, List
from coze_coding_dev_sdk import DocumentGenerationClient
from coze_coding_utils.runtime_ctx.context import new_context


def _safe_get(data: Any, key: str, default: Any = None) -> Any:
    """安全获取字典值"""
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def _safe_float(value: Any) -> float:
    """安全转换为float"""
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _safe_str(value: Any) -> str:
    """安全转换为str"""
    if value is None:
        return ""
    return str(value)


@tool
def generate_expense_report(
    period: str = "month",
    format: str = "pdf",
    runtime: ToolRuntime = None
) -> str:
    """
    生成消费分析报告文档。

    参数:
        period: 报告周期 - month（本月，默认）/ week（本周）/ year（今年）/ all（全部）
        format: 文档格式 - pdf（默认）/ docx / xlsx

    返回:
        报告文档的下载链接（24小时有效）
    """
    try:
        client = get_supabase_client()
        doc_client = DocumentGenerationClient()

        # 根据周期确定时间范围
        now = datetime.now()
        if period == "month":
            start_date = now.date().replace(day=1)
            end_date = now.date()
            period_text = "本月"
        elif period == "week":
            start_date = now.date() - timedelta(days=now.weekday())
            end_date = now.date()
            period_text = "本周"
        elif period == "year":
            start_date = now.date().replace(month=1, day=1)
            end_date = now.date()
            period_text = "今年"
        elif period == "all":
            start_date = None
            end_date = None
            period_text = "全部时间"
        else:
            return "❌ 不支持的报告周期，请使用：month/week/year/all"

        # 查询数据
        query = client.table('expense_records').select('*').order('expense_date', desc=True)

        if start_date:
            query = query.gte('expense_date', f"{start_date} 00:00:00")
        if end_date:
            query = query.lte('expense_date', f"{end_date} 23:59:59")

        response = query.execute()

        # 安全获取数据
        records: List[Dict[str, Any]] = []
        if isinstance(response.data, list):
            records = [item for item in response.data if isinstance(item, dict)]

        if not records:
            return f"📭 {period_text}还没有消费记录，无法生成报告"

        # 统计分析
        total_amount = sum(_safe_float(_safe_get(record, 'amount')) for record in records)
        count = len(records)
        avg_amount = total_amount / count if count > 0 else 0

        # 分类统计
        from collections import defaultdict
        category_stats = defaultdict(lambda: {'amount': 0.0, 'count': 0})
        for record in records:
            cat = _safe_get(record, 'category', '其他')
            if isinstance(cat, str):
                category_stats[cat]['amount'] += _safe_float(_safe_get(record, 'amount'))
                category_stats[cat]['count'] += 1

        # 商户统计
        merchant_stats = defaultdict(float)
        for record in records:
            merchant = _safe_get(record, 'merchant', '未知')
            if isinstance(merchant, str):
                merchant_stats[merchant] += _safe_float(_safe_get(record, 'amount'))

        # 支付方式统计
        payment_stats = defaultdict(float)
        for record in records:
            payment = _safe_get(record, 'payment_method', '')
            if payment:
                payment_stats[payment] += _safe_float(_safe_get(record, 'amount'))

        # 按日期统计
        daily_stats = defaultdict(float)
        for record in records:
            expense_date = _safe_get(record, 'expense_date', '')
            if isinstance(expense_date, str) and expense_date:
                date_key = expense_date.split(' ')[0]
                daily_stats[date_key] += _safe_float(_safe_get(record, 'amount'))

        # 生成Markdown报告
        report_title = f"{period_text}消费分析报告"
        report_date = now.strftime("%Y年%m月%d日")

        # 构建Markdown内容
        markdown_content = f"# {report_title}\n\n"
        markdown_content += f"📅 报告日期：{report_date}\n\n"

        # 概览
        markdown_content += "## 📊 概览\n\n"
        markdown_content += f"- **统计周期**：{period_text}\n"
        markdown_content += f"- **总支出**：¥{total_amount:.2f}\n"
        markdown_content += f"- **消费笔数**：{count} 笔\n"
        markdown_content += f"- **平均每笔**：¥{avg_amount:.2f}\n\n"

        # 分类统计
        markdown_content += "## 📈 分类统计\n\n"
        markdown_content += "| 分类 | 金额 | 笔数 | 占比 |\n"
        markdown_content += "|------|------|------|------|\n"

        sorted_categories = sorted(category_stats.items(), key=lambda x: x[1]['amount'], reverse=True)
        for cat, stats in sorted_categories:
            percentage = (stats['amount'] / total_amount * 100) if total_amount > 0 else 0
            markdown_content += f"| {cat} | ¥{stats['amount']:.2f} | {stats['count']} | {percentage:.1f}% |\n"

        markdown_content += "\n"

        # 商户TOP 10
        markdown_content += "## 🏪 消费最多的商户 TOP 10\n\n"
        markdown_content += "| 排名 | 商户 | 金额 |\n"
        markdown_content += "|------|------|------|\n"

        sorted_merchants = sorted(merchant_stats.items(), key=lambda x: x[1], reverse=True)[:10]
        for i, (merchant, amount) in enumerate(sorted_merchants, 1):
            markdown_content += f"| {i} | {merchant} | ¥{amount:.2f} |\n"

        markdown_content += "\n"

        # 支付方式
        if payment_stats:
            markdown_content += "## 💳 支付方式\n\n"
            markdown_content += "| 支付方式 | 金额 |\n"
            markdown_content += "|----------|------|\n"

            sorted_payments = sorted(payment_stats.items(), key=lambda x: x[1], reverse=True)
            for payment, amount in sorted_payments:
                markdown_content += f"| {payment} | ¥{amount:.2f} |\n"

            markdown_content += "\n"

        # 每日消费趋势
        if period != "all":
            markdown_content += "## 📅 每日消费趋势\n\n"
            markdown_content += "| 日期 | 金额 |\n"
            markdown_content += "|------|------|\n"

            sorted_dates = sorted(daily_stats.items(), reverse=True)[:30]
            for date, amount in sorted_dates:
                markdown_content += f"| {date} | ¥{amount:.2f} |\n"

            markdown_content += "\n"

        # 详细记录（最多显示50条）
        markdown_content += "## 💵 详细消费记录\n\n"
        markdown_content += "| 日期 | 商户 | 分类 | 金额 | 支付方式 | 备注 |\n"
        markdown_content += "|------|------|------|------|----------|------|\n"

        for record in records[:50]:
            expense_date = _safe_get(record, 'expense_date', '')
            date_str = ""
            if isinstance(expense_date, str) and expense_date:
                date_str = expense_date.replace('T', ' ').split('.')[0].split(' ')[0]

            merchant = _safe_str(_safe_get(record, 'merchant'))
            category = _safe_str(_safe_get(record, 'category'))
            amount = _safe_float(_safe_get(record, 'amount'))
            payment = _safe_str(_safe_get(record, 'payment_method'))
            description = _safe_str(_safe_get(record, 'description'))

            markdown_content += f"| {date_str} | {merchant} | {category} | ¥{amount:.2f} | {payment} | {description} |\n"

        if len(records) > 50:
            markdown_content += f"\n*...还有 {len(records) - 50} 条记录未显示*\n"

        # 生成文档
        if format.lower() == 'pdf':
            url = doc_client.create_pdf_from_markdown(markdown_content, f"expense_report_{period}")
        elif format.lower() == 'docx':
            url = doc_client.create_docx_from_markdown(markdown_content, f"expense_report_{period}")
        elif format.lower() == 'xlsx':
            # 转换为XLSX格式
            data = [
                ["日期", "商户", "分类", "金额", "支付方式", "备注"]
            ]
            for record in records:
                expense_date = _safe_get(record, 'expense_date', '')
                date_str = ""
                if isinstance(expense_date, str) and expense_date:
                    date_str = expense_date.replace('T', ' ').split('.')[0].split(' ')[0]

                data.append([
                    date_str,
                    _safe_str(_safe_get(record, 'merchant')),
                    _safe_str(_safe_get(record, 'category')),
                    _safe_float(_safe_get(record, 'amount')),
                    _safe_str(_safe_get(record, 'payment_method')),
                    _safe_str(_safe_get(record, 'description'))
                ])
            url = doc_client.create_xlsx_from_2d_list(data, f"expense_report_{period}", "Expenses", has_header=True)
        else:
            return f"❌ 不支持的文档格式：{format}"

        return f"✅ 报告生成成功！\n\n📥 下载链接：{url}\n\n⏰ 链接24小时有效，请及时下载"

    except Exception as e:
        return f"❌ 生成报告失败：{str(e)}"
