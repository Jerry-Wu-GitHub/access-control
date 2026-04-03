"""
class: FileBackedResourceManager
"""

import asyncio
from collections.abc import Callable, Coroutine
import os
import pickle
from typing import Generic, Optional, override
from uuid import uuid4

import aiofiles
import aiofiles.os

from .utils import to_async
from .resource_manager import (
    ResourceManager,
    ControlCode, AccessCode, Resource,
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


class FileBackedResourceManager(
    Generic[Resource, ControlCode, AccessCode],
    ResourceManager[FileName, ControlCode, AccessCode]
):
    """
    Subclass of ResourceManager.
    
    Store resources in disk files.

    If control/access codes, codes generators and filename generator are all pickle serializable,
    then the FileBackedResourceManager object can also be.
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

        Args:
            data_dir_path (str): 存储资源文件的目录。
            dumps_function (Optional[DumpsFunction | DumpsFunctionAsync]): 将资源转换为字节串的函数，
                默认为 pickle.dumps 。
            loads_function (Optional[LoadsFunction | LoadsFunctionAsync]): 将字节串解码为资源的函数，
                默认为 pickle.loads 。
            file_name_gen (Optional[FileNameGen | FileNameGenAsync]): 根据资源内容（可选）和控制码（可选）生成文件名的函数。
            control_code_gen (Optional[ControlCodeGen | ControlCodeGenAsync]): 根据资源内容（可选）生成控制码的函数。
            access_code_gen (Optional[AccessCodeGen | AccessCodeGenAsync]): 根据资源内容（可选）、控制码（可选）、
                父级访问码（可选）生成访问码的函数。
        """
        super().__init__(control_code_gen, access_code_gen)

        # 文件存放路径
        self.data_dir_path = data_dir_path

        # 数据转换函数
        if not dumps_function:
            dumps_function = pickle.dumps

        if not loads_function:
            loads_function = pickle.loads

        self.dumps_async: DumpsFunctionAsync = to_async(dumps_function)
        self.loads_async: LoadsFunctionAsync = to_async(loads_function)

        # 文件名生成函数
        if not file_name_gen:
            file_name_gen = uuid4_str
        self._file_name_gen_raw_async: FileNameGenAsync = to_async(file_name_gen)


    def _get_path(self, file_name: str) -> str:
        """
        获取文件存储的路径。
        """
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
        async with aiofiles.open(file_path, mode="rb") as file:
            content = await file.read()
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

        # 写入文件
        await aiofiles.os.makedirs(self.data_dir_path, exist_ok=True)
        file_path = self._get_path(file_name)
        content = await self.dumps_async(resource)
        async with aiofiles.open(file_path, mode="wb") as file:
            await file.write(content)

        # 记录
        await super()._set_resource_async(control_code, file_name)


    @override
    async def _delete_resource_async(self, control_code: ControlCode) -> None:
        """
        删除资源。

        Args:
            control_code (Code): 控制码。
        """
        file_name = await super()._get_resource_async(control_code)

        # 删除记录
        await super()._delete_resource_async(control_code)

        # 删除文件
        file_path = self._get_path(file_name)
        if await aiofiles.os.path.isfile(file_path):
            await aiofiles.os.remove(file_path)


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

    print(pickle.dumps(manager))

    manager.delete(control_code)


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

    print(pickle.dumps(manager))

    await manager.delete_async(control_code)


if __name__ == '__main__':
    _test()
    asyncio.run(_test_async())
