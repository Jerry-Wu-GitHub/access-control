"""
class: FileBackedResourceManager
"""

import asyncio
from collections.abc import Callable, Coroutine
import os
import pickle
from typing import Optional, override
from uuid import uuid4

from .utils import sync_to_async, is_async_func
from .resource_manager import (
    ResourceManager,
    ControlCode, Resource,
    ControlCodeGen, ControlCodeGenAsync, AccessCodeGen, AccessCodeGenAsync,
)


def uuid4_str():
    """生成一个标准格式的随机UUID字符串"""
    return str(uuid4())

# 资源与二进制数据转换函数
DumpsFunction = Callable[[Resource], bytes]
LoadsFunction = Callable[[bytes], Resource]
DumpsFunctionAsync = Callable[[Resource], Coroutine[None, None, bytes]]
LoadsFunctionAsync = Callable[[bytes], Coroutine[None, None, Resource]]

# 文件名生成函数
FileName = str
FileNameGen = Callable[[Optional[Resource], Optional[ControlCode]], FileName]
FileNameGenAsync = Callable[[Optional[Resource], Optional[ControlCode]], Coroutine[None, None, FileName]]


class FileBackedResourceManager(ResourceManager):
    """
    将数据存储到磁盘上。
    """

    def __init__(
        self,
        data_dir_path: str,
        dumps_function: Optional[DumpsFunction | DumpsFunctionAsync] = None,
        loads_function: Optional[LoadsFunction | LoadsFunctionAsync] = None,
        file_name_gen: Optional[FileNameGen | FileNameGenAsync] = None,
        *,
        control_code_gen: Optional[ControlCodeGen | ControlCodeGenAsync] = None,
        access_code_gen: Optional[AccessCodeGen | AccessCodeGenAsync] = None,
    ):
        """
        初始化一个 FileBackedResourceManager 对象。
        """
        super().__init__(control_code_gen, access_code_gen)

        # 文件存放路径
        self.data_dir_path = data_dir_path

        # 数据转换函数
        if not dumps_function:
            dumps_function = pickle.dumps
        if not is_async_func(dumps_function):
            dumps_function = sync_to_async(dumps_function)

        if not loads_function:
            loads_function = pickle.loads
        if not is_async_func(loads_function):
            loads_function = sync_to_async(loads_function)

        self.dumps_async: DumpsFunctionAsync = dumps_function
        self.loads_async: LoadsFunctionAsync = loads_function

        # 文件名生成函数
        if not file_name_gen:
            file_name_gen = uuid4_str
        if not is_async_func(file_name_gen):
            file_name_gen = sync_to_async(file_name_gen)
        self._file_name_gen_raw_async: FileNameGenAsync = file_name_gen


    def _get_path(self, file_name: str) -> str:
        return os.path.join(self.data_dir_path, file_name)


    async def file_name_gen_async(
        self,
        resource: Optional[Resource] = None,
        control_code: Optional[ControlCode] = None
    ) -> FileName:
        """
        包装了生成文件名的函数，使其能够接受接受 resource, control_code 参数。
        """
        try:
            return await self._file_name_gen_raw_async(resource, control_code)
        except TypeError:
            try:
                return await self._file_name_gen_raw_async(resource)
            except TypeError:
                return await self._file_name_gen_raw_async()


    # ==== 重载父类方法 ====

    @override
    async def _get_resource_async(self, control_code: ControlCode) -> Resource:
        """
        返回资源。

        Args:
            code (Code): 控制码或访问码。

        Returns:
            Resource: control_code 对应的资源。

        Raises:
            FileNotFoundError: 如果文件没有找到。
            PermissionInsufficient: 如果 control_code 不是控制码。
        """
        # 获取文件路径
        file_name = await super()._get_resource_async(control_code)
        file_path = self._get_path(file_name)

        # 读取文件
        with open(file_path, mode="rb") as file:
            content = file.read()
        return await self.loads_async(content)


    @override
    async def _set_resource_async(self, control_code: ControlCode, resource: Resource) -> None:
        """
        记录资源。

        Args:
            control_code (Code): 控制码。
        """
        # 生成文件名
        file_name = await self.file_name_gen_async(resource=resource, control_code=control_code)
        await super()._set_resource_async(control_code, file_name)

        # 写入文件
        os.makedirs(self.data_dir_path, exist_ok=True)
        file_path = self._get_path(file_name)
        content = await self.dumps_async(resource)
        with open(file_path, mode="wb") as file:
            file.write(content)


    @override
    async def _delete_resource_async(self, control_code: ControlCode) -> None:
        """
        删除资源。

        Args:
            control_code (Code): 控制码。
        """
        # 删除文件
        file_name = await super().get_async(control_code)
        file_path = self._get_path(file_name)
        os.remove(file_path)

        # 删除记录
        await super()._delete_resource_async(control_code)


def _test():
    """
    测试。
    """
    resource = {"data": "this is resource in _test"}
    manager = FileBackedResourceManager("data")

    control_code = manager.create(resource)
    print(f"{control_code=}")

    access_code1 = manager.share(control_code)
    access_code2 = manager.share(control_code)
    access_code3 = manager.share(access_code1)
    print(manager.get_access_codes(control_code)) # access_code1, access_code2, access_code3

    manager.revoke(control_code, access_code1)
    print(manager.get_access_codes(control_code)) # access_code2

    print(manager.get(access_code2))

    import pickle
    print(pickle.dumps(manager))


async def _test_async():
    """
    异步测试。
    """
    resource = {"data": "this is resource in _test_async"}
    manager = FileBackedResourceManager("data")

    control_code = await manager.create_async(resource)
    print(f"{control_code=}")

    access_code1 = await manager.share_async(control_code)
    access_code2 = await manager.share_async(control_code)
    access_code3 = await manager.share_async(access_code1)
    print(await manager.get_access_codes_async(control_code)) # access_code1, access_code2, access_code3

    await manager.revoke_async(control_code, access_code1)
    print(await manager.get_access_codes_async(control_code)) # access_code2

    print(await manager.get_async(access_code2))

    import pickle
    print(pickle.dumps(manager))


if __name__ == '__main__':
    _test()
    asyncio.run(_test_async())
