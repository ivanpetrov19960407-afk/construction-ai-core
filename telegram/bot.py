"""Совместимость: запускайте telegram.main."""

from telegram.main import create_bot, create_dispatcher, main

__all__ = ["create_bot", "create_dispatcher", "main"]
