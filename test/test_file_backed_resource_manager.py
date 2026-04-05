"""
测试 FileBackedResourceManager
"""

import asyncio
import pickle
from access_control import FileBackedResourceManager


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
