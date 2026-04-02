"""
异常
"""

class ResourceManagerError(Exception):
    """
    与 ResourceManager 有关的错误。
    """

class PermissionInsufficient(ResourceManagerError):
    """
    所使用的控制/访问码的权限不足（控制/访问码不存在）。
    """

class CodeExistError(ResourceManagerError):
    """
    若控制码/访问码重复。
    """
