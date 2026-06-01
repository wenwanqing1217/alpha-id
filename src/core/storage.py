"""
存储抽象层：定义存储后端接口，支持 JSON 文件和 PostgreSQL 两种实现。

核心模块（UserIdentityManager / AlphaSocialManager）通过此接口读写数据，
不直接耦合任何存储实现。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class StorageBackend(ABC):
    """存储后端抽象基类"""

    @abstractmethod
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载整个数据集"""
        ...

    @abstractmethod
    def save(self, key: str, data: Dict[str, Any]):
        """保存整个数据集"""
        ...

    @abstractmethod
    def get(self, collection: str, record_id: str) -> Optional[Dict[str, Any]]:
        """获取单条记录"""
        ...

    @abstractmethod
    def put(self, collection: str, record_id: str, record: Dict[str, Any]):
        """写入单条记录（不存在则创建，存在则覆盖）"""
        ...

    @abstractmethod
    def delete(self, collection: str, record_id: str):
        """删除单条记录"""
        ...

    @abstractmethod
    def list(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """列出集合中的记录，支持按字段过滤"""
        ...

    @abstractmethod
    def count(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> int:
        """统计记录数"""
        ...


class JsonStorage(StorageBackend):
    """JSON 文件存储后端"""

    def __init__(self, db_path: str):
        import json
        import os

        self._json = json
        self._os = os
        self.db_path = db_path

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return self._json.load(f)
        except (FileNotFoundError, self._json.JSONDecodeError):
            return {}

    def _write(self, data: Dict[str, Any]):
        self._os.makedirs(self._os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            self._json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        data = self._read()
        return data.get(key)

    def save(self, key: str, data: Dict[str, Any]):
        full = self._read()
        full[key] = data
        self._write(full)

    def get(self, collection: str, record_id: str) -> Optional[Dict[str, Any]]:
        data = self._read()
        return data.get(collection, {}).get(record_id)

    def put(self, collection: str, record_id: str, record: Dict[str, Any]):
        data = self._read()
        if collection not in data:
            data[collection] = {}
        data[collection][record_id] = record
        self._write(data)

    def delete(self, collection: str, record_id: str):
        data = self._read()
        if collection in data and record_id in data[collection]:
            del data[collection][record_id]
            self._write(data)

    def list(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        data = self._read()
        items = list(data.get(collection, {}).values())
        if filters:
            items = [item for item in items if all(item.get(k) == v for k, v in filters.items())]
        return items

    def count(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> int:
        return len(self.list(collection, filters))
