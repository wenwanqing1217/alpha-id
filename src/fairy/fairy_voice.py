"""
FAIRY 语音 — Whisper STT + Coqui TTS

语音识别：faster-whisper（CPU 模式，~0.5GB）
语音合成：Coqui TTS（~1.5GB VRAM）
唤醒监听：WakeupListener（关键词检测）

注意：Whisper 和 TTS 不同时运行以节省 VRAM。
"""

import logging
import os
import threading
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
TTS_MODEL = os.getenv("TTS_MODEL", "tts_models/zh-CN/baker/tacotron2-DDC-GST")


class FairyVoice:
    """语音识别 + 合成引擎"""

    def __init__(self, whisper_model: str = WHISPER_MODEL, tts_model: str = TTS_MODEL):
        self.whisper_model_name = whisper_model
        self.tts_model_name = tts_model
        self._whisper = None
        self._tts = None
        self._initialized = False

        # 检查可用性
        self._check_availability()

    def _check_availability(self):
        """检查 STT/TTS 是否可用"""
        # STT
        try:
            import faster_whisper  # noqa
            self._has_stt = True
        except ImportError:
            self._has_stt = False

        # TTS
        try:
            import TTS  # noqa
            self._has_tts = True
        except ImportError:
            self._has_tts = False

    @property
    def has_stt(self) -> bool:
        """语音识别是否可用"""
        return self._has_stt

    @property
    def has_tts(self) -> bool:
        """语音合成是否可用"""
        return self._has_tts

    def _init_whisper(self):
        """延迟初始化 Whisper"""
        if self._whisper:
            return
        try:
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel(self.whisper_model_name, device="cpu", compute_type="int8")
            logger.info(f"Whisper 初始化: {self.whisper_model_name}")
        except ImportError:
            logger.warning("faster-whisper 未安装，语音输入不可用")
        except Exception as e:
            logger.error(f"Whisper 初始化失败: {e}")

    def _init_tts(self):
        """延迟初始化 TTS"""
        if self._tts:
            return
        try:
            from TTS.api import TTS
            self._tts = TTS(model_name=self.tts_model_name)
            logger.info(f"TTS 初始化: {self.tts_model_name}")
        except ImportError:
            logger.warning("TTS 未安装，语音输出不可用")
        except Exception as e:
            logger.error(f"TTS 初始化失败: {e}")

    def is_available(self) -> bool:
        """检查语音能力是否可用"""
        return self._has_stt or self._has_tts

    def stt(self, audio_path: str) -> str:
        """
        语音识别：音频文件 → 文本

        Args:
            audio_path: 音频文件路径（wav/mp3）

        Returns:
            识别出的文本
        """
        self._init_whisper()
        if not self._whisper:
            return ""
        try:
            segments, info = self._whisper.transcribe(audio_path, language="zh")
            text = " ".join(seg.text for seg in segments)
            logger.debug(f"STT: {len(text)} chars, lang={info.language}")
            return text.strip()
        except Exception as e:
            logger.error(f"STT 失败: {e}")
            return ""

    def tts(self, text: str, output_path: str = "fairy_speech.wav") -> str:
        """
        语音合成：文本 → 音频文件

        Args:
            text: 要合成的文本
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        self._init_tts()
        if not self._tts:
            return ""
        try:
            self._tts.tts_to_file(text=text, file_path=output_path)
            logger.debug(f"TTS: {len(text)} chars → {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"TTS 失败: {e}")
            return ""

    def speak(self, text: str) -> str:
        """合成并播放语音"""
        fairy_speech = "fairy_speech.wav"
        path = self.tts(text, fairy_speech)
        if path:
            try:
                import sounddevice as sd
                import soundfile as sf
                data, samplerate = sf.read(fairy_speech)
                sd.play(data, samplerate)
                sd.wait()
            except ImportError:
                logger.warning("sounddevice/soundfile 未安装，仅保存音频文件")
            except Exception as e:
                logger.error(f"播放失败: {e}")
        return path


class WakeupListener:
    """唤醒词监听器（后台线程）"""

    def __init__(self, callback: Callable, wakeup_phrase: str = "你好 FAIRY"):
        self.callback = callback
        self.wakeup_phrase = wakeup_phrase
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """启动监听"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info(f"唤醒监听启动: '{self.wakeup_phrase}'")

    def stop(self):
        """停止监听"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _listen_loop(self):
        """监听循环（简化版，实际需要麦克风输入）"""
        logger.info("唤醒监听运行中（需要麦克风输入）")
        # 实际实现需要 pyaudio + VAD + Whisper 流式识别
        # 这里仅作为占位，后续接入完整实现
        while self._running:
            time.sleep(1)
