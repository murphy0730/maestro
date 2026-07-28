# 安装包放置目录

官网下载区的两个按钮指向本目录下的固定文件名。把构建产物按这两个名字放进来，链接即可用：

| 平台 | 文件名 | 构建方式 |
| --- | --- | --- |
| macOS (Apple Silicon) | `Maestro-mac-arm64.dmg` | 在 macOS 上执行仓库根目录的 `./build-mac.sh`，产物在 `frontend/release/*.dmg` |
| Windows (x64) | `Maestro-win-x64.exe` | 在 Windows 上执行 `build-win.bat`，产物在 `frontend/release/*.exe` |

后端被 PyInstaller 冻结为原生二进制，**无法交叉编译** —— 每个平台的包必须在该平台上构建。

改文件名的话，同步改 `site/index.html` 下载区两个 `<a href>`。

本目录下的安装包不建议提交进 git（体积过大），部署时单独上传即可。
