"""Чтение формата .MDN (модель «Управление страной», 1995)."""
from .sections import read_sections
from .blocks import Block, parse_blocks, load, NONE
