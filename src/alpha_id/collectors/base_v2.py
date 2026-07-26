"""Alpha-ID Collector Base v2 - with Gateway sync + watch support"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable
import logging
import json

from core.settings import settings

logger = logging.getLogger(__name__)
GATEWAY_URL = settings.gateway_url
DEFAULT_ALPHA_ID = settings.default_alpha_id


@dataclass
class CollectorInfo:
    name: str = ""
    display_name: str = ""
    description: str = ""
    category: str = "other"
    priority: int = 100
    requires_input: bool = False
    watchable: bool = False


class BaseCollector(ABC):
    info: CollectorInfo

    @abstractmethod
    def detect(self) -> bool:
        ...

    @abstractmethod
    def collect(self, input_path: Optional[Path] = None):
        ...

    def sync_to_gateway(self, profile) -> bool:
        """Push collected profile to Gateway -> MemoryStore -> Obsidian"""
        try:
            import requests
            persona = profile.persona
            parts = []
            if persona.communication.tone:
                parts.append("style: " + persona.communication.tone)
            if persona.communication.sentence_length:
                parts.append("length: " + persona.communication.sentence_length)
            if persona.technical.primary_languages:
                parts.append("langs: " + ", ".join(persona.technical.primary_languages))
            if persona.technical.coding_style:
                parts.append("code: " + persona.technical.coding_style)
            content = "[%s] %s" % (self.info.display_name, " | ".join(parts) if parts else "collected")
            payload = {
                "alpha_id": DEFAULT_ALPHA_ID,
                "content": content,
                "category": "profile_" + self.info.name,
                "sensitivity": 20,
                "source": self.info.name,
                "tags": [self.info.name, "profile", "collector"],
            }
            resp = requests.post(GATEWAY_URL + "/v1/memory/store", json=payload, timeout=10)
            data = resp.json()
            ok = data.get("success", False)
            if ok:
                logger.info("[%s] synced to Gateway", self.info.name)
            else:
                logger.warning("[%s] sync failed: %s", self.info.name, data.get("error", ""))
            return ok
        except Exception as e:
            logger.warning("[%s] sync error (non-fatal): %s", self.info.name, e)
            return False

    def watch(self, callback: Optional[Callable] = None):
        raise NotImplementedError("%s does not support watch mode" % self.info.name)
