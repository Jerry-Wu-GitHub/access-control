"""
class: ResourceManager
"""

import asyncio
from collections.abc import Coroutine, Hashable, Callable
import functools
from typing import Dict, Generic, List, Optional, TypeVar, Union
from uuid import uuid4

from treelib import Tree
from treelib.exceptions import NodeIDAbsentError

from .utils import to_async, AsyncRLock
from .exceptions import CodeExistError, PermissionInsufficient, ResourceManagerError


# 资源类型
Resource = TypeVar("Resource")

# 控制码类型，一般是字符串或整数
ControlCode = TypeVar("ControlCode", bound=Hashable)

# 访问码类型，一般是字符串或整数
AccessCode = TypeVar("AccessCode", bound=Hashable)

# 控制码和访问码的联合类型
Code = Union[ControlCode, AccessCode]

# 生成控制码的函数类型
ControlCodeGen = Callable[[Optional[Resource]], ControlCode]

# 生成访问码的函数类型
AccessCodeGen = Callable[
    [Optional[Resource], Optional[ControlCode], Optional[AccessCode]],
    AccessCode
]

# 生成控制码的异步函数类型
ControlCodeGenAsync = Callable[[Optional[Resource]], Coroutine[None, None, ControlCode]]

# 生成访问码的异步函数类型
AccessCodeGenAsync = Callable[
    [Optional[Resource], Optional[ControlCode], Optional[AccessCode]],
    Coroutine[None, None, AccessCode]
]



def async_locked(method: Callable) -> Callable:
    """装饰器：为异步方法自动加上 RLock"""
    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        async with self._lock_async:
            return await method(self, *args, **kwargs)
    return wrapper



class ResourceManager(Generic[Resource, ControlCode, AccessCode]):
    """
    Implementing access control for resources.

    Resources can be any Python object.

    A single resource can have multiple access codes, but only one control code.

    If control/access codes, codes generators, and resources are all pickle serializable,
    then the ResourceManager object can also be.
    """
    def __init__(
        self,
        control_code_gen: Optional[ControlCodeGen | ControlCodeGenAsync] = None,
        access_code_gen: Optional[AccessCodeGen | AccessCodeGenAsync] = None,
    ):
        """
        初始化一个 ResourceManager 对象。

        Args:
            control_code_gen (Optional[ControlCodeGen | ControlCodeGenAsync]): 根据资源内容（可选）生成控制码的函数。
            access_code_gen (Optional[AccessCodeGen | AccessCodeGenAsync]): 根据资源内容（可选）、控制码（可选）、
                父级访问码（可选）生成访问码的函数。
        """
        # 控制码、访问码生成函数
        if not control_code_gen:
            control_code_gen = uuid4

        if not access_code_gen:
            access_code_gen = control_code_gen

        self._control_code_gen_raw_async: ControlCodeGenAsync = to_async(control_code_gen)
        self._access_code_gen_raw_async: AccessCodeGenAsync = to_async(access_code_gen)

        # 存储控制码和资源的关系：control_code -> resource
        self._control_resource_map: Dict[ControlCode, Resource] = {}

        # 存储访问码和控制码的关系：access_code -> control_code
        self._access_control_map: Dict[AccessCode, ControlCode] = {}

        # 存储资源的访问码树：control_code -> code_tree
        self._control_code_tree_map: Dict[ControlCode, Tree] = {}

        # 异步锁，用于线程安全
        self._lock_async = AsyncRLock()


    def __len__(self) -> int:
        """
        返回资源数量。
        """
        return len(self._control_resource_map)


    # ==== 子类可能需要重载的方法 ====


    async def _get_control_code_async(self, code: Code) -> ControlCode:
        """
        返回 code 的控制码。

        Args:
            code (Code): 控制码或访问码。

        Returns:
            ControlCode: code 对应的控制码。

        Raises:
            PermissionInsufficient: 如果 code 不存在。
        """
        if await self.is_control_code_async(code):
            return code
        if await self.is_access_code_async(code):
            return self._access_control_map[code]
        raise PermissionInsufficient("Code not found")


    async def _get_tree_async(self, code: Code) -> Tree:
        """
        返回 code 的访问控制树。

        Args:
            code (Code): 控制码或访问码。

        Returns:
            Tree: code 所在的访问控制树。

        Raises:
            PermissionInsufficient: 如果 code 不存在。
            ResourceManagerError: 内部错误：找不到访问树。
        """
        control_code = await self._get_control_code_async(code)
        code_tree = self._control_code_tree_map.get(control_code)
        if not code_tree:
            raise ResourceManagerError("Code tree not found")
        return code_tree


    async def _access_async(
        self,
        control_code: ControlCode,
        parent_code: Optional[Code] = None,
        child_code: Optional[AccessCode] = None
    ) -> AccessCode:
        """
        生成一个访问码。

        Args:
            control_code (ControlCode): 控制码。
            parent_code (Optional[Code]): 分享者。
            child_code (Optional[AccessCode]): 自定义的访问码。若缺省，则由 access_code_gen 生成。

        Raises:
            CodeExistError: 如果提供的 child_code 已存在，或 access_code_gen 生成了重复的访问码。
            PermissionInsufficient: 如果不存在 control_code 。
        """
        if not await self.is_control_code_async(control_code):
            raise PermissionInsufficient("Control code not found")

        # 生成访问码
        access_code = child_code or await self.access_code_gen_async(
            await self.get_async(control_code),
            control_code,
            parent_code
        )
        if await self.is_access_code_async(access_code):
            raise CodeExistError("Access code already exists")

        self._access_control_map[access_code] = control_code

        if not parent_code:
            parent_code = control_code

        # 将访问码添加到访问码树中
        code_tree = self._control_code_tree_map[control_code]
        code_tree.create_node(identifier=access_code, parent=parent_code)

        return access_code


    async def _create_tree_async(self, control_code: ControlCode) -> Tree:
        """
        创建一棵访问树。
        """
        code_tree = Tree()
        code_tree.create_node(identifier=control_code)
        self._control_code_tree_map[control_code] = code_tree
        return code_tree


    async def _get_resource_async(self, control_code: ControlCode) -> Resource:
        """
        返回资源。

        Args:
            code (Code): 控制码或访问码。

        Returns:
            Resource: control_code 对应的资源。

        Raises:
            PermissionInsufficient: 如果 control_code 不是控制码。
        """
        return self._control_resource_map[control_code]


    async def _set_resource_async(self, control_code: ControlCode, resource: Resource) -> None:
        """
        记录资源。

        Args:
            control_code (Code): 控制码。
        """
        self._control_resource_map[control_code] = resource


    async def _delete_resource_async(self, control_code: ControlCode) -> None:
        """
        删除资源。

        Args:
            control_code (Code): 控制码。
        """
        self._control_resource_map.pop(control_code, None)
        self._control_code_tree_map.pop(control_code, None)


    # ==== 子类应该不用重载的方法 ====

    @async_locked
    async def control_code_gen_async(self, resource: Optional[Resource] = None) -> ControlCode:
        """
        包装了生成控制码的函数，使其能够接受接受 resource 参数。
        """
        try:
            return await self._control_code_gen_raw_async(resource)
        except TypeError:
            return await self._control_code_gen_raw_async()


    @async_locked
    async def access_code_gen_async(
        self,
        resource: Optional[Resource] = None,
        control_code: Optional[ControlCode] = None,
        parent_access_code: Optional[AccessCode] = None
    ) -> AccessCode:
        """
        包装生成访问码的异步函数，使其能够接受 resource、control_code、parent_access_code 参数。
        """
        try:
            return await self._access_code_gen_raw_async(resource, control_code, parent_access_code)
        except TypeError:
            try:
                return await self._access_code_gen_raw_async(resource, control_code)
            except TypeError:
                try:
                    return await self._access_code_gen_raw_async(resource)
                except TypeError:
                    return await self._access_code_gen_raw_async()


    @async_locked
    async def is_control_code_async(self, code: Code) -> bool:
        """
        判断一个 code 是否是控制码。
        """
        return code in self._control_resource_map


    @async_locked
    async def is_access_code_async(self, code: Code) -> bool:
        """
        判断一个 code 是否是访问码。
        """
        return code in self._access_control_map


    @async_locked
    async def create_async(
        self,
        resource: Resource,
        control_code: Optional[ControlCode] = None
    ) -> ControlCode:
        """
        创建一个资源。

        Args:
            resource (Resource): 资源。
            control_code (Optional[ControlCode]): 自定义的控制码。若缺省，则由 control_code_gen 生成。

        Raises:
            CodeExistError: 如果提供的 control_code 已存在，或 control_code_gen 生成了重复的控制码。
        """
        # 生成控制码
        control_code = control_code or await self.control_code_gen_async(resource)
        if await self.is_control_code_async(control_code):
            raise CodeExistError("Control code already exists")

        # 记录资源
        await self._set_resource_async(control_code, resource)

        # 初始化 code_tree
        await self._create_tree_async(control_code)

        return control_code


    @async_locked
    async def replace_async(self, control_code: ControlCode, new_resource: Resource) -> None:
        """
        替换一项资源。

        Args:
            control_code (ControlCode): 被操作的控制码。
            new_resource (Resource): 新的资源。
        """
        if not await self.is_control_code_async(control_code):
            raise PermissionInsufficient("Control code not found")
        await self._set_resource_async(control_code, new_resource)


    @async_locked
    async def delete_async(self, control_code: ControlCode) -> None:
        """
        删除一项资源及其控制码、所有访问码。
        """
        if not await self.is_control_code_async(control_code):
            raise PermissionInsufficient("Control code not found")

        # 获取该资源对应的访问码树
        code_tree = self._control_code_tree_map.get(control_code)
        if code_tree:
            # 删除所有访问码映射
            for node in code_tree.all_nodes():
                if node.identifier != control_code:
                    self._access_control_map.pop(node.identifier, None)

        # 删除资源映射
        await self._delete_resource_async(control_code)


    @async_locked
    async def get_async(self, code: Code) -> Resource:
        """
        获取一项资源。

        Args:
            code (Code): 控制码或访问码。

        Raises:
            PermissionInsufficient: 如果 code 不存在。
        """
        control_code = await self._get_control_code_async(code)
        return await self._get_resource_async(control_code)


    @async_locked
    async def share_async(self, parent_code: Code, child_code: Optional[AccessCode] = None) -> AccessCode:
        """
        生成一个新的访问码。

        Args:
            parent_code (Optional[Code]): 分享者。
            child_code (Optional[AccessCode]): 自定义的访问码。若缺省，则由 access_code_gen 生成。

        Raises:
            CodeExistError: 如果提供的 child_code 已存在，或 access_code_gen 生成了重复的访问码 。
            PermissionInsufficient: 如果不存在 parent_code 。
        """
        control_code = await self._get_control_code_async(parent_code)
        return await self._access_async(
            control_code=control_code,
            parent_code=parent_code,
            child_code=child_code
        )


    @async_locked
    async def revoke_async(self, ancestor_code: Code, descendant_code: AccessCode) -> None:
        """
        撤销一个访问码及其所有子访问码，不能撤销自己。

        Args:
            ancestor_code (Code): 撤销发起者。
            descendant_code (Code): 被撤销者。

        Raises:
            PermissionInsufficient: 
            - 如果不存在 ancestor_code 或 descendant_code 。
            - 如果 descendant_code 不是 ancestor_code 的后代。

            ResourceManagerError: 内部错误：找不到访问树。
        """
        # 获取访问码树
        code_tree = await self._get_tree_async(ancestor_code)

        # 检查 ancestor_code 是否是 descendant_code 的祖先节点（TreeLib 的实现已保证自己不是自己的祖先）
        if (descendant_code not in code_tree) or (not code_tree.is_ancestor(ancestor_code, descendant_code)):
            raise PermissionInsufficient("Cannot revoke: not ancestor of the descendant code")

        # 获取删除的树节点（descendant_code 及其子树）
        subtree = code_tree.remove_subtree(descendant_code)
        subtree_nodes = subtree.all_nodes()

        # 删除访问码映射
        for node in subtree_nodes:
            self._access_control_map.pop(node.identifier, None)


    @async_locked
    async def get_access_codes_async(self, code: Code) -> List[AccessCode]:
        """
        查看 code 的所有后代。

        Raises:
            PermissionInsufficient: 如果 code 不存在。
            ResourceManagerError: 内部错误：找不到访问树。
        """
        # 获取访问码树
        code_tree = await self._get_tree_async(code)

        # 直接获取整个子树，然后排除根节点自身
        try:
            subtree = code_tree.subtree(code)
        except NodeIDAbsentError:
            # 如果 code 不在树中（可能已被删除），返回空列表
            return []

        return [
            node.identifier
            for node in subtree.all_nodes()
            if node.identifier != code
        ]


    @async_locked
    async def transfer_async(
        self,
        old_control_code: ControlCode,
        new_control_code: ControlCode
    ) -> None:
        """
        转让资源所有者。

        原控制码及其访问树被删除，新控制码的资源被修改为原控制码的资源。

        Args:
            old_control_code (ControlCode): 原控制码。
            new_control_code (ControlCode): 新控制码。
        """
        if not await self.is_control_code_async(old_control_code):
            raise PermissionInsufficient("Old control code not found")
        if not await self.is_control_code_async(new_control_code):
            raise PermissionInsufficient("New control code not found")
        if old_control_code == new_control_code:
            return

        # 获取原资源
        resource = await self.get_async(old_control_code)

        # 将资源转移到新控制码
        await self.replace_async(new_control_code, resource)

        # 移除原访问码树
        await self.delete_async(old_control_code)


    # ==== 异步方法转同步 ====

    def control_code_gen(self, resource: Optional[Resource] = None) -> ControlCode:
        """ Synchronous version of `.control_code_gen_async`. """
        return asyncio.run(self.control_code_gen_async(resource))

    def access_code_gen(
        self, resource: Optional[Resource] = None,
        control_code: Optional[ControlCode] = None,
        parent_access_code: Optional[AccessCode] = None
    ) -> AccessCode:
        """ Synchronous version of `.access_code_gen_async`. """
        return asyncio.run(self.access_code_gen_async(resource, control_code, parent_access_code))

    def is_control_code(self, code: Code) -> bool:
        """ Synchronous version of `.is_control_code_async`. """
        return asyncio.run(self.is_control_code_async(code))

    def is_access_code(self, code: Code) -> bool:
        """ Synchronous version of `.is_access_code_async`. """
        return asyncio.run(self.is_access_code_async(code))

    def create(self, resource: Resource, control_code: Optional[ControlCode] = None) -> ControlCode:
        """ Synchronous version of `.create_async`. """
        return asyncio.run(self.create_async(resource, control_code))

    def replace(self, control_code: ControlCode, new_resource: Resource) -> None:
        """ Synchronous version of `.replace_async`. """
        return asyncio.run(self.replace_async(control_code, new_resource))

    def delete(self, control_code: ControlCode) -> None:
        """ Synchronous version of `.delete_async`. """
        return asyncio.run(self.delete_async(control_code))

    def get(self, code: Code) -> Resource:
        """ Synchronous version of `.get_async`. """
        return asyncio.run(self.get_async(code))

    def share(self, parent_code: Code, child_code: Optional[AccessCode] = None) -> AccessCode:
        """ Synchronous version of `.share_async`. """
        return asyncio.run(self.share_async(parent_code, child_code))

    def revoke(self, ancestor_code: Code, descendant_code: AccessCode) -> None:
        """ Synchronous version of `.revoke_async`. """
        return asyncio.run(self.revoke_async(ancestor_code, descendant_code))

    def get_access_codes(self, code: Code) -> List[AccessCode]:
        """ Synchronous version of `.get_access_codes_async`. """
        return asyncio.run(self.get_access_codes_async(code))

    def transfer(self, old_control_code: ControlCode, new_control_code: ControlCode) -> None:
        """ Synchronous version of `.transfer_async`. """
        return asyncio.run(self.transfer_async(old_control_code, new_control_code))
