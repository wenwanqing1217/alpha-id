from coze_coding_dev_sdk.database import Base

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Double, Integer, JSON, Numeric, PrimaryKeyConstraint, Table, Text, text, String, Float, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import OID
from typing import Optional, List
import datetime

from sqlalchemy.orm import Mapped, mapped_column

class HealthCheck(Base):
    __tablename__ = 'health_check'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='health_check_pkey'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('now()'))


t_pg_stat_statements = Table(
    'pg_stat_statements', Base.metadata,
    Column('userid', OID),
    Column('dbid', OID),
    Column('toplevel', Boolean),
    Column('queryid', BigInteger),
    Column('query', Text),
    Column('plans', BigInteger),
    Column('total_plan_time', Double(53)),
    Column('min_plan_time', Double(53)),
    Column('max_plan_time', Double(53)),
    Column('mean_plan_time', Double(53)),
    Column('stddev_plan_time', Double(53)),
    Column('calls', BigInteger),
    Column('total_exec_time', Double(53)),
    Column('min_exec_time', Double(53)),
    Column('max_exec_time', Double(53)),
    Column('mean_exec_time', Double(53)),
    Column('stddev_exec_time', Double(53)),
    Column('rows', BigInteger),
    Column('shared_blks_hit', BigInteger),
    Column('shared_blks_read', BigInteger),
    Column('shared_blks_dirtied', BigInteger),
    Column('shared_blks_written', BigInteger),
    Column('local_blks_hit', BigInteger),
    Column('local_blks_read', BigInteger),
    Column('local_blks_dirtied', BigInteger),
    Column('local_blks_written', BigInteger),
    Column('temp_blks_read', BigInteger),
    Column('temp_blks_written', BigInteger),
    Column('shared_blk_read_time', Double(53)),
    Column('shared_blk_write_time', Double(53)),
    Column('local_blk_read_time', Double(53)),
    Column('local_blk_write_time', Double(53)),
    Column('temp_blk_read_time', Double(53)),
    Column('temp_blk_write_time', Double(53)),
    Column('wal_records', BigInteger),
    Column('wal_fpi', BigInteger),
    Column('wal_bytes', Numeric),
    Column('jit_functions', BigInteger),
    Column('jit_generation_time', Double(53)),
    Column('jit_inlining_count', BigInteger),
    Column('jit_inlining_time', Double(53)),
    Column('jit_optimization_count', BigInteger),
    Column('jit_optimization_time', Double(53)),
    Column('jit_emission_count', BigInteger),
    Column('jit_emission_time', Double(53)),
    Column('jit_deform_count', BigInteger),
    Column('jit_deform_time', Double(53)),
    Column('stats_since', DateTime(True)),
    Column('minmax_stats_since', DateTime(True))
)


t_pg_stat_statements_info = Table(
    'pg_stat_statements_info', Base.metadata,
    Column('dealloc', BigInteger),
    Column('stats_reset', DateTime(True))
)


class ExpenseRecord(Base):
    """消费记录表"""
    __tablename__ = 'expense_records'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False, comment="消费金额")
    merchant: Mapped[str] = mapped_column(String(255), nullable=True, comment="商户名称")
    category: Mapped[str] = mapped_column(String(100), nullable=True, comment="消费分类")
    payment_method: Mapped[str] = mapped_column(String(100), nullable=True, comment="支付方式")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注说明")
    expense_date: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=func.now(), comment="消费时间")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)


class Budget(Base):
    """预算表"""
    __tablename__ = 'budgets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, comment="预算分类")
    amount: Mapped[float] = mapped_column(Float, nullable=False, comment="预算金额")
    period: Mapped[str] = mapped_column(String(50), nullable=False, default='monthly', comment="预算周期: daily, weekly, monthly")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), onupdate=func.now(), nullable=True)


class AlphaUser(Base):
    """Alpha-ID 用户表"""
    __tablename__ = 'alpha_users'

    alpha_id: Mapped[str] = mapped_column(String(20), primary_key=True, comment="Alpha-ID编号")
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="内部唯一标识")
    device_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, comment="设备指纹")
    is_founder: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否创始人")
    status: Mapped[str] = mapped_column(String(20), default='locked', nullable=False, comment="状态: locked/active/inactive")
    password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="安全密码(bcrypt哈希)")
    password_set_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True, comment="密码设置时间")
    security_questions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="安全问题及答案")
    security_questions_set_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True, comment="安全问题设置时间")
    voice_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="声纹数据")
    voice_set_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True, comment="声纹设置时间")
    devices: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list, comment="已绑定设备列表")
    total_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="总会话次数")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)
    last_active: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AlphaFriend(Base):
    """Alpha-ID 好友关系表"""
    __tablename__ = 'alpha_friends'
    __table_args__ = (
        UniqueConstraint('alpha_id', 'friend_alpha_id', name='uq_alpha_friend'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alpha_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="用户Alpha-ID")
    friend_alpha_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="好友Alpha-ID")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)


class AlphaMessage(Base):
    """Alpha-ID 消息表"""
    __tablename__ = 'alpha_messages'

    message_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="消息ID")
    from_alpha_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="发送方Alpha-ID")
    to_alpha_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="接收方Alpha-ID")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    message_type: Mapped[str] = mapped_column(String(20), default='text', nullable=False, comment="消息类型: text/image/file")
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否已读")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)


class AlphaFriendRequest(Base):
    """Alpha-ID 好友请求表"""
    __tablename__ = 'alpha_friend_requests'

    request_id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="请求ID")
    from_alpha_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="发起方Alpha-ID")
    to_alpha_id: Mapped[str] = mapped_column(String(20), nullable=False, comment="接收方Alpha-ID")
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="请求消息")
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False, comment="状态: pending/accepted/rejected")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)
    responded_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True, comment="响应时间")
