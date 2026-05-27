from langchain.tools import tool
from langchain.tools import ToolRuntime
from storage.database.supabase_client import get_supabase_client
from datetime import datetime
from typing import Any, Dict, List


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
def add_expense(
    amount: float,
    merchant: str,
    category: str,
    payment_method: str = None,
    description: str = None,
    expense_date: str = None,
    runtime: ToolRuntime = None
) -> str:
    """
    添加消费记录到数据库。

    参数:
        amount: 消费金额（必填）
        merchant: 商户名称（必填）
        category: 消费分类（必填）- 餐饮/交通/购物/娱乐/医疗/教育/居住/通讯/其他
        payment_method: 支付方式（可选）- 微信/支付宝/银行卡/现金等
        description: 备注说明（可选）
        expense_date: 消费时间（可选）- 格式为YYYY-MM-DD HH:mm:ss，不填则使用当前时间

    返回:
        成功消息，包含记录ID
    """
    try:
        client = get_supabase_client()

        # 处理消费时间
        if expense_date:
            try:
                expense_dt = datetime.strptime(expense_date, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return f"错误：消费时间格式不正确，请使用 YYYY-MM-DD HH:mm:ss 格式"
        else:
            expense_dt = datetime.now()

        # 构建记录数据
        record_data: Dict[str, Any] = {
            "amount": amount,
            "merchant": merchant,
            "category": category,
            "expense_date": expense_dt.isoformat()
        }

        # 添加可选字段
        if payment_method:
            record_data["payment_method"] = payment_method
        if description:
            record_data["description"] = description

        # 插入数据库
        response = client.table('expense_records').insert(record_data).execute()

        if response.data and isinstance(response.data, list) and len(response.data) > 0:
            record_id = _safe_get(response.data[0], 'id')
            return f"✅ 消费记录已保存！\n\n金额：¥{amount}\n商户：{merchant}\n分类：{category}\n时间：{expense_dt.strftime('%Y-%m-%d %H:%M')}\n记录ID：{record_id}"
        else:
            return "❌ 保存失败，请稍后重试"

    except Exception as e:
        return f"❌ 添加消费记录失败：{str(e)}"


@tool
def query_expenses(
    start_date: str = None,
    end_date: str = None,
    category: str = None,
    runtime: ToolRuntime = None
) -> str:
    """
    查询消费记录，支持按时间范围和分类筛选。

    参数:
        start_date: 开始日期（可选）- 格式为YYYY-MM-DD
        end_date: 结束日期（可选）- 格式为YYYY-MM-DD
        category: 消费分类（可选）- 餐饮/交通/购物/娱乐/医疗/教育/居住/通讯/其他

    返回:
        消费记录列表，包含总金额统计
    """
    try:
        client = get_supabase_client()

        # 构建查询
        query = client.table('expense_records').select('*').order('expense_date', desc=True)

        # 添加时间范围筛选
        if start_date:
            query = query.gte('expense_date', f"{start_date} 00:00:00")
        if end_date:
            query = query.lte('expense_date', f"{end_date} 23:59:59")

        # 添加分类筛选
        if category:
            query = query.eq('category', category)

        # 执行查询
        response = query.execute()

        # 安全获取数据
        records: List[Dict[str, Any]] = []
        if isinstance(response.data, list):
            records = [item for item in response.data if isinstance(item, dict)]

        if not records:
            return "📭 没有找到符合条件的消费记录"

        # 计算总金额
        total_amount = sum(_safe_float(_safe_get(record, 'amount')) for record in records)

        # 构建结果
        result = f"📊 查询结果（共 {len(records)} 条记录）\n"
        result += f"💰 总金额：¥{total_amount:.2f}\n\n"

        # 按日期分组统计
        from collections import defaultdict
        date_groups = defaultdict(list)
        for record in records:
            expense_date = _safe_get(record, 'expense_date', '')
            if isinstance(expense_date, str) and expense_date:
                date_key = expense_date.split(' ')[0]  # 只取日期部分
                date_groups[date_key].append(record)

        # 按分类统计
        category_stats = defaultdict(float)
        for record in records:
            cat = _safe_get(record, 'category', '其他')
            if isinstance(cat, str):
                category_stats[cat] += _safe_float(_safe_get(record, 'amount'))

        # 显示分类统计
        result += "📈 分类统计：\n"
        for cat, amount in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
            result += f"  • {cat}：¥{amount:.2f}\n"

        result += "\n💵 详细记录：\n"
        for record in records[:20]:  # 最多显示20条
            expense_date = _safe_get(record, 'expense_date', '')
            date_time = ""
            if isinstance(expense_date, str) and expense_date:
                date_time = expense_date.replace('T', ' ').split('.')[0]

            merchant = _safe_get(record, 'merchant', '未知商户')
            amount = _safe_float(_safe_get(record, 'amount'))
            category = _safe_get(record, 'category', '未知')
            payment = _safe_get(record, 'payment_method')
            desc = _safe_get(record, 'description')

            result += f"\n【{date_time}】{merchant}\n"
            result += f"  金额：¥{amount:.2f} | 分类：{category}"
            if payment:
                result += f" | 支付方式：{payment}"
            if desc:
                result += f"\n  备注：{desc}"
            result += "\n"

        if len(records) > 20:
            result += f"\n...还有 {len(records) - 20} 条记录未显示"

        return result

    except Exception as e:
        return f"❌ 查询消费记录失败：{str(e)}"


@tool
def get_summary(
    period: str = "today",
    runtime: ToolRuntime = None
) -> str:
    """
    获取消费统计摘要。

    参数:
        period: 统计周期 - today（今天）/ week（本周）/ month（本月）/ year（今年）

    返回:
        消费统计摘要，包含总金额、分类占比、高频消费等
    """
    try:
        client = get_supabase_client()
        from datetime import timedelta

        # 根据周期确定时间范围
        now = datetime.now()
        if period == "today":
            start_date = now.date()
            end_date = now.date()
        elif period == "week":
            start_date = now.date() - timedelta(days=now.weekday())
            end_date = now.date()
        elif period == "month":
            start_date = now.date().replace(day=1)
            end_date = now.date()
        elif period == "year":
            start_date = now.date().replace(month=1, day=1)
            end_date = now.date()
        else:
            return "❌ 不支持的统计周期，请使用：today/week/month/year"

        # 查询数据
        response = (client.table('expense_records')
                   .select('*')
                   .gte('expense_date', f"{start_date} 00:00:00")
                   .lte('expense_date', f"{end_date} 23:59:59")
                   .execute())

        # 安全获取数据
        records: List[Dict[str, Any]] = []
        if isinstance(response.data, list):
            records = [item for item in response.data if isinstance(item, dict)]

        if not records:
            period_text = {
                'today': '今天',
                'week': '本周',
                'month': '本月',
                'year': '今年'
            }.get(period, period)
            return f"📭 {period_text}还没有消费记录"

        # 统计分析
        total_amount = sum(_safe_float(_safe_get(record, 'amount')) for record in records)
        count = len(records)

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

        # 构建结果
        period_text = {
            'today': '今天',
            'week': '本周',
            'month': '本月',
            'year': '今年'
        }.get(period, period)

        result = f"📊 {period_text}消费统计\n\n"
        result += f"💰 总支出：¥{total_amount:.2f}\n"
        result += f"📝 消费笔数：{count} 笔\n"
        if count > 0:
            result += f"📊 平均每笔：¥{total_amount / count:.2f}\n"

        result += "\n📈 分类占比：\n"
        sorted_categories = sorted(category_stats.items(), key=lambda x: x[1]['amount'], reverse=True)
        for cat, stats in sorted_categories:
            percentage = (stats['amount'] / total_amount * 100) if total_amount > 0 else 0
            result += f"  • {cat}：¥{stats['amount']:.2f} ({percentage:.1f}%) - {stats['count']}笔\n"

        result += "\n🏪 消费最多的商户 TOP 5：\n"
        sorted_merchants = sorted(merchant_stats.items(), key=lambda x: x[1], reverse=True)[:5]
        for merchant, amount in sorted_merchants:
            result += f"  • {merchant}：¥{amount:.2f}\n"

        return result

    except Exception as e:
        return f"❌ 获取统计摘要失败：{str(e)}"
