"""
VK Ads API - backward compatibility layer
All functions are now in utils/vk_api/ submodules

This file re-exports all functions from the modular structure
to maintain backward compatibility with existing imports:
    from utils.vk_api import get_banners_active
    from utils import vk_api
"""

# Re-export everything from the vk_api package
from utils.vk_api import *
