"""Logging configuration and redaction filters for the daemon."""

import logging
import re
from typing import Any

# Simple regex to catch generic bearer tokens and basic keys for Phase 2
BEARER_PATTERN = re.compile(r'(Bearer\s+|api_key[\s=:]+[\'"]?)([a-zA-Z0-9_\-\.]{15,})', re.IGNORECASE)

class CredentialRedactionFilter(logging.Filter):
    """Filters log records to redact sensitive credentials."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        
        # Redact any string arguments passed to the logger
        if isinstance(record.args, tuple):
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(self._redact(arg))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)
        elif isinstance(record.args, dict):
            new_args_dict = {}
            for k, v in record.args.items():
                if isinstance(v, str):
                    new_args_dict[k] = self._redact(v)
                else:
                    new_args_dict[k] = v
            record.args = new_args_dict
            
        return True

    def _redact(self, text: str) -> str:
        return BEARER_PATTERN.sub(r'\1[REDACTED_CREDENTIAL]', text)


def configure_logging(debug: bool = False) -> None:
    """Configure daemon logging. Disabled by default unless debug is True."""
    root_logger = logging.getLogger()
    
    # Remove any existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        
    if not debug:
        root_logger.addHandler(logging.NullHandler())
        root_logger.setLevel(logging.CRITICAL)
        return

    root_logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(CredentialRedactionFilter())
    
    root_logger.addHandler(console_handler)
