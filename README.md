# 维什戴尔的爆破委托（原型）

参考 `MonsterDeleter` 的桌面演出思路重写的 Windows / PyQt6 小工具：先召唤维什戴尔，再选择并确认目标文件，随后播放投弹与爆炸动画，在炸弹命中时将目标移入系统回收站。

当前演出还原了视频中的夸张表情变化：炸弹命中后会在目标位置弹出红黑冲击圈，并从 8 种原版风格表情中随机选择一张快速放大、抖动后缩回。

## 安全设计

- 不使用鼠标屏幕坐标猜测文件，删除对象始终来自文件选择器或明确的命令行路径。
- 删除前展示完整路径并要求二次确认。
- 选择时记录文件指纹；如果确认后文件被替换或修改，会中止操作。
- 使用 `send2trash` 移入回收站，不做不可逆永久粉碎。
- 禁止把当前脚本/可执行文件自身和磁盘根目录设为目标。
- 按 `Esc` 或“取消”随时退出。

## 源码运行

需要 Windows 10/11 与 Python 3.10+：

```powershell
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
py main.py
```

也可以预选一个目标（仍会显示确认界面）：

```powershell
py main.py "C:\path\to\target.txt"
```

## 右键菜单

安装当前用户的文件右键菜单，无需管理员权限：

```powershell
py main.py --install-menu
```

卸载：

```powershell
py main.py --uninstall-menu
```

Windows 11 的经典菜单项可能显示在“显示更多选项”中。

## 打包

双击 `build.bat`，或在项目目录运行它。输出位于 `dist\WisadelDeleter.exe`。打包完成后可执行：

```powershell
dist\WisadelDeleter.exe --install-menu
```

## 素材替换

当前角色图是非官方生成式原型素材。公开分发前请阅读 [ASSET_NOTES.md](ASSET_NOTES.md)，并替换为你有权使用的正式素材。
