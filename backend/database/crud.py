"""
CRUD operations - backward compatibility layer
All functions are now in database/crud/ submodules

This file re-exports all functions from the modular structure
to maintain backward compatibility with existing imports:
    from database import crud
    from database.crud import get_user_by_id
"""

# Re-export everything from the crud package
from database.crud import *
