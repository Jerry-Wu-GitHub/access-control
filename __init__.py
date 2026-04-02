"""
访问控制模块。
"""

from .resource_manager import (
    ResourceManager,
    ControlCode, AccessCode, Code, Resource
)

from .file_backed_resource_manager import FileBackedResourceManager
