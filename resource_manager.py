"""
class: ResourceManager
"""

from collections.abc import Hashable, Callable
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from treelib import Tree


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
AccessCodeGen = Callable[[Optional[Resource], Optional[ControlCode], Optional[AccessCode]], ControlCode]



class PermissionInsufficient(Exception):
    """
    所使用的控制/访问码的权限不足（控制/访问码不存在）
    """



class ResourceManager:
    """
    Implementing access control for resources.

    Resources can be any Python object.

    A single resource can have multiple access codes, but only one control code.

    If control codes, access codes, and resources are pickle serializable,
    then the ResourceManager object can also be.

    Provide asynchronous version interfaces for operations on resources.
    """
    def __init__(
        self,
        control_code_gen: Optional[ControlCodeGen] = None,
        access_code_gen: Optional[AccessCodeGen] = None,
    ):
        # 控制码、访问码生成函数
        if not control_code_gen:
            control_code_gen = uuid4
        if not access_code_gen:
            access_code_gen = control_code_gen
        self._control_code_gen_raw: ControlCodeGen = control_code_gen
        self._access_code_gen_raw: AccessCodeGen = access_code_gen

        # 存储控制码和资源的关系：control_code -> resource
        self._control_resource_map: Dict[ControlCode, Resource] = {}

        # 存储访问码和控制码的关系：access_code -> control_code
        self._access_control_map: Dict[AccessCode, ControlCode] = {}

        # 存储资源的访问码树：control_code -> code_tree
        self._control_code_tree_map: Dict[Resource, Tree[Code]] = {}


    def control_code_gen(self, resource: Optional[Resource] = None) -> ControlCode:
        """
        包装了生成控制码的函数，使其能够接受接受 resource 参数。
        """
        try:
            return self._control_code_gen_raw(resource)
        except TypeError:
            return self._control_code_gen_raw()


    def access_code_gen(
        self,
        resource: Optional[Resource] = None,
        control_code: Optional[ControlCode] = None,
        parent_access_code: Optional[AccessCode] = None
    ) -> AccessCode:
        """
        包装生成访问码的函数，使其能够接受 resource、control_code、parent_access_code 参数。
        """
        try:
            return self._access_code_gen_raw(resource, control_code, parent_access_code)
        except TypeError:
            try:
                return self._access_code_gen_raw(resource, control_code)
            except TypeError:
                try:
                    return self._access_code_gen_raw(resource)
                except TypeError:
                    return self._access_code_gen_raw()


    def create(self, resource: Resource) -> ControlCode:
        """
        创建一个资源。
        """
        # 记录资源
        control_code = self.control_code_gen(resource)
        self._control_resource_map[control_code] = resource

        # 初始化 code_tree
        code_tree = Tree()
        code_tree.create_node(identifier=control_code)
        self._control_code_tree_map[control_code] = code_tree

        return control_code

    async def create_async(self, resource: Resource) -> ControlCode:
        """
        Asynchronous version of `.create`.
        """
        return self.create(resource)


    def replace(self, control_code: ControlCode, new_resource: Resource) -> None:
        """
        替换一项资源。
        """
        if control_code not in self._control_resource_map:
            raise PermissionInsufficient("Control code not found")
        self._control_resource_map[control_code] = new_resource

    async def replace_async(self, control_code: ControlCode, new_resource: Resource) -> None:
        """
        Asynchronous version of `.replace`.
        """
        return self.replace(control_code=control_code, new_resource=new_resource)


    def delete(self, control_code: ControlCode) -> None:
        """
        删除一项资源及其所有访问码。
        """
        if control_code not in self._control_resource_map:
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

    async def delete_async(self, control_code: ControlCode) -> None:
        """
        Asynchronous version of `.delete`.
        """
        return self.delete(control_code)


    def get(self, code: Code) -> Resource:
        """
        获取一项资源。
        """
        if code in self._control_resource_map:
            return self._control_resource_map[code]
        if code in self._access_control_map:
            control_code = self._access_control_map[code]
            return self._control_resource_map[control_code]
        raise PermissionInsufficient("Code not found")

    async def get_async(self, code: Code) -> Resource:
        """
        Asynchronous version of `.get`.
        """
        return self.get(code)


    def access(
        self,
        control_code: ControlCode,
        parent_code: Optional[Code] = None
    ) -> AccessCode:
        """
        生成一个访问码。
        """
        if control_code not in self._control_resource_map:
            raise PermissionInsufficient("Control code not found")

        access_code = self.access_code_gen(
            self._control_resource_map[control_code],
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


    def share(self, code: Code) -> AccessCode:
        """
        生成一个新的访问码。
        """
        if code in self._control_resource_map:
            return self.access(control_code=code)

        if code in self._access_control_map:
            control_code = self._access_control_map[code]
            return self.access(control_code=control_code, parent_code=code)

        raise PermissionInsufficient("Code not found")


    def revoke(self, ancestor_code: Code, descendant_code: AccessCode) -> None:
        """
        撤销一个访问码及其所有子访问码，不能撤销自己。
        """
        # 查找 ancestor_code 对应的资源
        control_code = None
        if ancestor_code in self._control_resource_map:
            control_code = ancestor_code
        elif ancestor_code in self._access_control_map:
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
        subtree_nodes = code_tree.remove_subtree(descendant_code).all_nodes()

        # 删除访问码映射
        for node_id in subtree_nodes:
            self._access_control_map.pop(node_id, None)


    def get_access_codes(self, code: Code) -> List[AccessCode]:
        """
        查看 code 的所有后代。
        """
        # 确定资源对应的控制码
        control_code = None
        if code in self._control_resource_map:
            control_code = code
        elif code in self._access_control_map:
            control_code = self._access_control_map[code]
        else:
            raise PermissionInsufficient("Code not found")

        # 获取访问码树
        code_tree = self._control_code_tree_map.get(control_code)
        assert code_tree, "Code tree not found"

        # 获取指定节点的所有后代节点
        descendants = code_tree.children(code)
        result = []
        for node in descendants:
            result.append(node.identifier)
            # 递归获取所有后代
            result.extend(self.get_access_codes(node.identifier))

        return result


    def transfer(
        self,
        old_control_code: ControlCode,
        new_control_code: ControlCode
    ) -> None:
        """
        转让资源所有者。

        原控制码及其树被删除，新控制码的资源被修改为原控制码的资源。
        """
        if old_control_code not in self._control_resource_map:
            raise PermissionInsufficient("Old control code not found")
        if new_control_code not in self._control_resource_map:
            raise PermissionInsufficient("New control code not found")

        # 获取原资源
        resource = self._control_resource_map[old_control_code]

        # 将资源转移到新控制码
        self.replace(new_control_code, resource)

        # 移除原访问码树
        self.delete(old_control_code)

    async def transfer_async(
        self,
        old_control_code: ControlCode,
        new_control_code: ControlCode
    ) -> None:
        """
        Asynchronous version of `.transfer`.
        """
        return self.transfer(old_control_code=old_control_code, new_control_code=new_control_code)


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


if __name__ == '__main__':
    _test()
