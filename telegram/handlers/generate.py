"""Generate handlers exports for compatibility."""

from telegram.handlers import (
    ks_confirm_yes_handler,
    letter_confirm_yes_handler,
    tk_confirm_yes_handler,
)

__all__ = ["tk_confirm_yes_handler", "letter_confirm_yes_handler", "ks_confirm_yes_handler"]
