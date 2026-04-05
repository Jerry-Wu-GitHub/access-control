# Access Control

一个轻量级的 Python 资源访问控制库，支持基于控制码（Control Code）和访问码（Access Code）的细粒度权限管理，并提供可选的磁盘持久化能力。

## 特性

- **两级授权模型**：每个资源拥有唯一的控制码（所有者权限）和多个访问码（分享权限）
- **树形访问结构**：访问码可继续衍生子访问码，形成层级分享关系
- **同步与异步双接口**：所有方法均提供 `*_async` 异步版本和同步版本
- **可插拔的码生成器**：支持自定义控制码/访问码生成逻辑
- **磁盘持久化**：`FileBackedResourceManager` 可将资源序列化保存到文件系统
- **Pickle 友好**：管理器对象可序列化（需保证内部对象可 Pickle）

## 安装

```bash
pip install access-control-async
```

或者直接从源码安装：

```bash
git clone https://github.com/Jerry-Wu-GitHub/access-control.git
cd access-control
pip install .
```

## 快速开始

### 基本用法（内存存储）

```python
from access_control import ResourceManager

# 创建管理器（控制码和访问码默认使用 uuid4）
manager = ResourceManager()

# 创建一个资源
resource = {"data": "secret message"}
control_code = manager.create(resource)  # 返回控制码，如 "3a6f2b1c..."

# 基于控制码分享访问码
access_code1 = manager.share(control_code)
access_code2 = manager.share(control_code)

# 从访问码获取资源
retrieved = manager.get(access_code1)
assert retrieved == resource

# 查看某个码的所有后代访问码
codes = manager.get_access_codes(control_code)   # [access_code1, access_code2]

# 撤销一个访问码及其所有子访问码
manager.revoke(control_code, access_code1)

# 删除整个资源（包括所有访问码）
manager.delete(control_code)
```

### 异步接口

所有操作都提供 `*_async` 异步版本，便于集成到异步应用中：

```python
import asyncio
from access_control import ResourceManager

async def main():
    manager = ResourceManager()
    control_code = await manager.create_async({"data": "async test"})
    access_code = await manager.share_async(control_code)
    resource = await manager.get_async(access_code)
    print(resource)

asyncio.run(main())
```

### 使用文件持久化

```python
import asyncio
from access_control import FileBackedResourceManager

async def main():
    # 资源将保存在 ./data 目录下
    manager = FileBackedResourceManager("./data")

    # 创建资源（自动序列化到磁盘）
    resource = {"user": "alice", "score": 100}
    control_code = await manager.create_async(resource)

    # 即使重启程序，只要 data 目录存在，即可恢复
    new_manager = FileBackedResourceManager("./data")
    same_resource = await new_manager.get_async(control_code)
    print(same_resource)

asyncio.run(main())
```

### 自定义码生成器

你可以传入自己的生成函数（同步或异步均可）：

```python
import hashlib
from access_control import ResourceManager

def my_control_code_gen(resource):
    # 根据资源内容生成控制码
    return hashlib.md5(str(resource).encode()).hexdigest()[:8]

def my_access_code_gen(resource, control_code, parent_code):
    # 自定义访问码生成逻辑
    return f"share_{control_code}_{parent_code}"

manager = ResourceManager(
    control_code_gen=my_control_code_gen,
    access_code_gen=my_access_code_gen
)

control = manager.create({"foo": "bar"})
print(control)  # 输出类似 "d3b07384"
```

## API 概览

### `ResourceManager[Resource, ControlCode, AccessCode]`

主要方法（均提供同步版本和 `*_async` 异步版本）：

| 方法 | 描述 |
|------|------|
| `create(resource, control_code=None)` | 创建资源，返回控制码 |
| `get(code)` | 通过控制码或访问码获取资源 |
| `share(parent_code, child_code=None)` | 生成新的访问码 |
| `revoke(ancestor_code, descendant_code)` | 撤销一个访问码及其所有子访问码 |
| `get_access_codes(code)` | 返回某个码的所有后代访问码 |
| `replace(control_code, new_resource)` | 替换控制码对应的资源 |
| `transfer(old_control, new_control)` | 将资源所有权转移给另一个控制码 |
| `delete(control_code)` | 删除资源及其所有关联码 |
| `is_control_code(code)` / `is_access_code(code)` | 判断码的类型 |

### `FileBackedResourceManager`

继承自 `ResourceManager`，额外接受以下构造参数：

- `data_dir_path`: 存储文件的目录路径
- `dumps_function` / `loads_function`: 自定义序列化函数（默认 `pickle.dumps` / `pickle.loads`）
- `file_name_gen`: 根据资源和控制码生成文件名的函数（默认使用 `uuid4`）

所有资源的存取均自动读写磁盘文件。

## 依赖

- Python >= 3.10
- `treelib` – 用于维护访问码树结构
- `aiofiles` – 异步文件操作
- `pathvalidate` – 校验文件名的合法性

## 许可证

本项目使用 [MIT 许可证](LICENSE)。
