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
def set_budget(
    category: str,
    amount: float,
    period: str = "monthly",
    runtime: ToolRuntime = None
) -> str:
    """
    设置预算。

    参数:
        category: 预算分类（餐饮/交通/购物/娱乐/医疗/教育/居住/通讯/其他）
        amount: 预算金额
        period: 预算周期 - daily（每日）/ weekly（每周）/ monthly（每月，默认）/ yearly（每年）

    返回:
        成功消息
    """
    try:
        client = get_supabase_client()

        # 检查是否已存在该分类的预算
        response = client.table('budgets').select('*').eq('category', category).eq('is_active', True).execute()

        if response.data and isinstance(response.data, list) and len(response.data) > 0:
            # 更新现有预算
            budget_id = _safe_get(response.data[0], 'id')
            update_response = client.table('budgets').update({
                'amount': amount,
                'period': period,
                'updated_at': datetime.now().isoformat()
            }).eq('id', budget_id).execute()

            return f"✅ 预算已更新！\n\n分类：{category}\n预算金额：¥{amount:.2f}\n周期：{period}"
        else:
            # 创建新预算
            insert_response = client.table('budgets').insert({
                'category': category,
                'amount': amount,
                'period': period,
                'is_active': True
            }).execute()

            return f"✅ 预算已创建！\n\n分类：{category}\n预算金额：¥{amount:.2f}\n周期：{period}"

    except Exception as e:
        return f"❌ 设置预算失败：{str(e)}"


@tool
def check_budget(category: str = None, runtime: ToolRuntime = None) -> str:
    """
    检查预算使用情况，返回超支预警。

    参数:
        category: 指定分类（可选），不填则检查所有分类

    返回:
        预算使用情况，包括剩余金额、使用率、预警信息
    """
    try:
        client = get_supabase_client()
        from datetime import timedelta

        now = datetime.now()

        # 获取预算信息
        if category:
            budgets_response = client.table('budgets').select('*').eq('category', category).eq('is_active', True).execute()
            budgets: List[Dict[str, Any]] = []
            if isinstance(budgets_response.data, list):
                budgets = [item for item in budgets_response.data if isinstance(item, dict)]
        else:
            budgets_response = client.table('budgets').select('*').eq('is_active', True).execute()
            budgets: List[Dict[str, Any]] = []
            if isinstance(budgets_response.data, list):
                budgets = [item for item in budgets_response.data if isinstance(item, dict)]

        if not budgets:
            return "📭 还没有设置任何预算"

        result = "📊 预算使用情况\n\n"

        for budget in budgets:
            cat = _safe_str(_safe_get(budget, 'category'))
            budget_amount = _safe_float(_safe_get(budget, 'amount'))
            period = _safe_str(_safe_get(budget, 'period'))

            # 计算时间范围
            if period == 'daily':
                start_date = now.date()
                end_date = now.date()
                period_text = "今天"
            elif period == 'weekly':
                start_date = now.date() - timedelta(days=now.weekday())
                end_date = now.date()
                period_text = "本周"
            elif period == 'monthly':
                start_date = now.date().replace(day=1)
                end_date = now.date()
                period_text = "本月"
            elif period == 'yearly':
                start_date = now.date().replace(month=1, day=1)
                end_date = now.date()
                period_text = "今年"
            else:
                continue

            # 获取该分类的实际消费
            expenses_response = (client.table('expense_records')
                       .select('*')
                       .eq('category', cat)
                       .gte('expense_date', f"{start_date} 00:00:00")
                       .lte('expense_date', f"{end_date} 23:59:59")
                       .execute())

            expense_records: List[Dict[str, Any]] = []
            if isinstance(expenses_response.data, list):
                expense_records = [item for item in expenses_response.data if isinstance(item, dict)]

            actual_amount = sum(_safe_float(_safe_get(record, 'amount')) for record in expense_records)

            # 计算预算使用情况
            remaining = budget_amount - actual_amount
            usage_rate = (actual_amount / budget_amount * 100) if budget_amount > 0 else 0

            # 构建结果
            result += f"📌 {cat}（{period_text}）\n"
            result += f"  预算：¥{budget_amount:.2f}\n"
            result += f"  已消费：¥{actual_amount:.2f}\n"
            result += f"  剩余：¥{remaining:.2f}\n"
            result += f"  使用率：{usage_rate:.1f}%\n"

            # 预警提示
            if usage_rate >= 100:
                result += f"  ⚠️ 已超支 ¥{-remaining:.2f}！请注意控制消费！\n"
            elif usage_rate >= 90:
                result += f"  ⚠️ 预算即将用完（仅剩{100 - usage_rate:.1f}%）！\n"
            elif usage_rate >= 70:
                result += f"  💡 已使用{usage_rate:.1f}%，请注意合理消费\n"

            result += "\n"

        return result

    except Exception as e:
        return f"❌ 检查预算失败：{str(e)}"


@tool
def list_budgets(runtime: ToolRuntime = None) -> str:
    """
    列出所有预算配置。

    返回:
        所有预算的列表
    """
    try:
        client = get_supabase_client()

        response = client.table('budgets').select('*').eq('is_active', True).order('category').execute()

        budgets: List[Dict[str, Any]] = []
        if isinstance(response.data, list):
            budgets = [item for item in response.data if isinstance(item, dict)]

        if not budgets:
            return "📭 还没有设置任何预算"

        result = f"📋 预算配置（共 {len(budgets)} 个）\n\n"

        period_map = {
            'daily': '每日',
            'weekly': '每周',
            'monthly': '每月',
            'yearly': '每年'
        }

        for budget in budgets:
            cat = _safe_str(_safe_get(budget, 'category'))
            amount = _safe_float(_safe_get(budget, 'amount'))
            period = _safe_str(_safe_get(budget, 'period'))
            period_text = period_map.get(period, period)

            result += f"• {cat}：¥{amount:.2f} ({period_text})\n"

        return result

    except Exception as e:
        return f"❌ 获取预算列表失败：{str(e)}"
