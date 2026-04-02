"""
class: ResourceManager
"""

import asyncio
from collections.abc import Coroutine, Hashable, Callable
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from treelib import Tree
from treelib.exceptions import NodeIDAbsentError

from .utils import async_to_sync, sync_to_async, is_async_func


# 资源类型
Resource = Any

# 控制码类型，一般是字符串或整数
ControlCode = Hashable

# 访问码类型，一般是字符串或整数
AccessCode = Hashable

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



class PermissionInsufficient(Exception):
    """
    所使用的控制/访问码的权限不足（控制/访问码不存在）
    """



class ResourceManager:
    """
    Implementing access control for resources.

    Resources can be any Python object.

    A single resource can have multiple access codes, but only one control code.

    If control/access codes, codes generators, and resources are pickle serializable,
    then the ResourceManager object can also be.

    Provide asynchronous version interfaces for operations on resources.
    """
    def __init__(
        self,
        control_code_gen: Optional[ControlCodeGen | ControlCodeGenAsync] = None,
        access_code_gen: Optional[AccessCodeGen | AccessCodeGenAsync] = None,
    ):
        # 控制码、访问码生成函数
        if not control_code_gen:
            control_code_gen = uuid4
        if not is_async_func(control_code_gen):
            control_code_gen = sync_to_async(control_code_gen)

        if not access_code_gen:
            access_code_gen = control_code_gen
        if not is_async_func(access_code_gen):
            access_code_gen = sync_to_async(access_code_gen)

        self._control_code_gen_raw_async: ControlCodeGen = control_code_gen
        self._access_code_gen_raw_async: AccessCodeGen = access_code_gen

        # 存储控制码和资源的关系：control_code -> resource
        self._control_resource_map: Dict[ControlCode, Resource] = {}

        # 存储访问码和控制码的关系：access_code -> control_code
        self._access_control_map: Dict[AccessCode, ControlCode] = {}

        # 存储资源的访问码树：control_code -> code_tree
        self._control_code_tree_map: Dict[ControlCode, Tree[Code]] = {}


    async def control_code_gen_async(self, resource: Optional[Resource] = None) -> ControlCode:
        """
        包装了生成控制码的函数，使其能够接受接受 resource 参数。
        """
        try:
            return await self._control_code_gen_raw_async(resource)
        except TypeError:
            return await self._control_code_gen_raw_async()


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


    async def is_control_code_async(self, code: Code) -> bool:
        """
        判断一个 code 是否是控制码。
        """
        return code in self._control_resource_map


    async def is_access_code_async(self, code: Code) -> bool:
        """
        判断一个 code 是否是访问码。
        """
        return code in self._access_control_map


    async def create_async(self, resource: Resource) -> ControlCode:
        """
        创建一个资源。
        """
        # 记录资源
        control_code = await self.control_code_gen_async(resource)
        self._control_resource_map[control_code] = resource

        # 初始化 code_tree
        code_tree = Tree()
        code_tree.create_node(identifier=control_code)
        self._control_code_tree_map[control_code] = code_tree

        return control_code


    async def replace_async(self, control_code: ControlCode, new_resource: Resource) -> None:
        """
        替换一项资源。
        """
        if not await self.is_control_code_async(control_code):
            raise PermissionInsufficient("Control code not found")
        self._control_resource_map[control_code] = new_resource


    async def delete_async(self, control_code: ControlCode) -> None:
        """
        删除一项资源及其所有访问码。
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
        self._control_resource_map.pop(control_code, None)
        # 删除访问码树
        self._control_code_tree_map.pop(control_code, None)


    async def get_async(self, code: Code) -> Resource:
        """
        获取一项资源。
        """
        if await self.is_control_code_async(code):
            return self._control_resource_map[code]
        if await self.is_access_code_async(code):
            control_code = self._access_control_map[code]
            return await self.get_async(control_code)
        raise PermissionInsufficient("Code not found")


    async def _access_async(
        self,
        control_code: ControlCode,
        parent_code: Optional[Code] = None
    ) -> AccessCode:
        """
        生成一个访问码。
        """
        if not await self.is_control_code_async(control_code):
            raise PermissionInsufficient("Control code not found")

        access_code = await self.access_code_gen_async(
            await self.get_async(control_code),
            control_code,
            parent_code
        )
        self._access_control_map[access_code] = control_code

        if not parent_code:
            parent_code = control_code

        # 将访问码添加到访问码树中
        code_tree = self._control_code_tree_map[control_code]
        code_tree.create_node(identifier=access_code, parent=parent_code)

        return access_code


    async def share_async(self, code: Code) -> AccessCode:
        """
        生成一个新的访问码。
        """
        if await self.is_control_code_async(code):
            return await self._access_async(control_code=code)

        if await self.is_access_code_async(code):
            control_code = self._access_control_map[code]
            return await self._access_async(control_code=control_code, parent_code=code)

        raise PermissionInsufficient("Code not found")


    async def revoke_async(self, ancestor_code: Code, descendant_code: AccessCode) -> None:
        """
        撤销一个访问码及其所有子访问码，不能撤销自己。
        """
        # 查找 ancestor_code 对应的资源
        control_code = None
        if await self.is_control_code_async(ancestor_code):
            control_code = ancestor_code
        elif await self.is_access_code_async(ancestor_code):
            control_code = self._access_control_map[ancestor_code]
        else:
            raise PermissionInsufficient("Ancestor code not found")

        # 获取访问码树
        code_tree = self._control_code_tree_map.get(control_code)
        assert code_tree, "Code tree not found"

        # 检查 ancestor_code 是否是 descendant_code 的祖先节点（TreeLib 的实现已保证自己不是自己的祖先）
        if (descendant_code not in code_tree) or (not code_tree.is_ancestor(ancestor_code, descendant_code)):
            raise PermissionInsufficient("Cannot revoke: not ancestor of the descendant code")

        # 获取删除的树节点（descendant_code 及其子树）
        subtree = code_tree.remove_subtree(descendant_code)
        subtree_nodes = subtree.all_nodes()

        # 删除访问码映射
        for node in subtree_nodes:
            self._access_control_map.pop(node.identifier, None)


    async def get_access_codes_async(self, code: Code) -> List[AccessCode]:
        """
        查看 code 的所有后代。
        """
        # 确定资源对应的控制码
        control_code = None
        if await self.is_control_code_async(code):
            control_code = code
        elif await self.is_access_code_async(code):
            control_code = self._access_control_map[code]
        else:
            raise PermissionInsufficient("Code not found")

        # 获取访问码树
        code_tree = self._control_code_tree_map.get(control_code)
        assert code_tree, "Code tree not found"

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


    async def transfer_async(
        self,
        old_control_code: ControlCode,
        new_control_code: ControlCode
    ) -> None:
        """
        转让资源所有者。

        原控制码及其树被删除，新控制码的资源被修改为原控制码的资源。
        """
        if not await self.is_control_code_async(old_control_code):
            raise PermissionInsufficient("Old control code not found")
        if not await self.is_control_code_async(new_control_code):
            raise PermissionInsufficient("New control code not found")

        # 获取原资源
        resource = await self.get_async(old_control_code)

        # 将资源转移到新控制码
        await self.replace_async(new_control_code, resource)

        # 移除原访问码树
        await self.delete_async(old_control_code)


    # 异步方法转同步
    control_code_gen    = async_to_sync(control_code_gen_async)
    access_code_gen     = async_to_sync(access_code_gen_async)
    is_control_code     = async_to_sync(is_control_code_async)
    is_access_code      = async_to_sync(is_access_code_async)
    create              = async_to_sync(create_async)
    replace             = async_to_sync(replace_async)
    delete              = async_to_sync(delete_async)
    get                 = async_to_sync(get_async)
    share               = async_to_sync(share_async)
    revoke              = async_to_sync(revoke_async)
    get_access_codes    = async_to_sync(get_access_codes_async)
    transfer            = async_to_sync(transfer_async)



def _test():
    """
    测试。
    """
    resource = 1
    manager = ResourceManager()
    control_code = manager.create(resource)
    print(f"{control_code=}")
    access_code1 = manager.share(control_code)
    access_code2 = manager.share(control_code)
    access_code3 = manager.share(access_code1)
    print(manager.get_access_codes(control_code)) # access_code1, access_code2, access_code3
    manager.revoke(control_code, access_code1)
    print(manager.get_access_codes(control_code)) # access_code2

    import pickle
    print(pickle.dumps(manager))


async def _test_async():
    """
    异步测试。
    """
    resource = 1
    manager = ResourceManager()
    control_code = await manager.create_async(resource)
    print(f"{control_code=}")
    access_code1 = await manager.share_async(control_code)
    access_code2 = await manager.share_async(control_code)
    access_code3 = await manager.share_async(access_code1)
    print(await manager.get_access_codes_async(control_code)) # access_code1, access_code2, access_code3
    await manager.revoke_async(control_code, access_code1)
    print(await manager.get_access_codes_async(control_code)) # access_code2

    import pickle
    print(pickle.dumps(manager))


if __name__ == '__main__':
    _test()
    asyncio.run(_test_async())
