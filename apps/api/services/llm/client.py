"""Local Transformers inference, usable unchanged on a workstation or Colab GPU."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "Qwen/Qwen2.5-3B-Instruct")
MODEL_CACHE = Path(__file__).resolve().parent / ".model_cache"
MAX_NEW_TOKENS = 768
MAX_INPUT_TOKENS = 12_000


class QwenClient:
    def __init__(self):
        device = os.environ.get("LLM_DEVICE", "auto")
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("LLM_DEVICE must be auto, cpu or cuda")
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable")
        use_cuda = torch.cuda.is_available() and device != "cpu"
        dtype = torch.float16 if use_cuda else torch.float32
        # auto uses Accelerate; CPU uses float32 for portability.
        options = {
            "cache_dir": str(MODEL_CACHE),
            "dtype": dtype,
            "device_map": "auto" if device == "auto" else {"": device},
        }
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                MODEL_NAME, cache_dir=str(MODEL_CACHE), local_files_only=True
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                MODEL_NAME, local_files_only=True, **options
            )
        except OSError:
            self.tokenizer = AutoTokenizer.from_pretrained(
                MODEL_NAME, cache_dir=str(MODEL_CACHE)
            )
            self.model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, **options)
        self.model.eval()
        self._generation_lock = Lock()

    def ask(
        self, system: str, user: str, *, max_new_tokens: int = MAX_NEW_TOKENS
    ) -> str:
        """The notebook's system/user → chat template → generate → decode flow."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        # The template already contains special tokens; do not add them twice.
        inputs = self.tokenizer(
            text, return_tensors="pt", add_special_tokens=False
        ).to(self.model.device)
        input_length = inputs["input_ids"].shape[1]
        if input_length > MAX_INPUT_TOKENS:
            raise ValueError("The conversation and evidence exceed the input token limit")
        with self._generation_lock, torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        return self.tokenizer.decode(
            output[0][input_length:], skip_special_tokens=True
        ).strip()


_client: QwenClient | None = None
_load_lock = Lock()


def get_client() -> QwenClient:
    """One model per process, including during simultaneous first requests."""
    global _client
    with _load_lock:
        if _client is None:
            _client = QwenClient()
        return _client


def is_loaded() -> bool:
    return _client is not None
