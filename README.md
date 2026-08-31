# Fantia Auto Downloader

[![Test](https://github.com/jonathan0lau/fantia-auto-downloader/actions/workflows/test.yml/badge.svg)](https://github.com/jonathan0lau/fantia-auto-downloader/actions/workflows/test.yml)

一个可在 Windows、群晖和飞牛 fnOS 上无人值守运行的 Fantia 下载器。

它会使用你自己的 Fantia 登录状态，下载当前账号有权查看的帖子图片、视频和附件；也可以在多重安全检查后，自动领取并下载价格严格为 0 日元的下载商品。

> [!IMPORTANT]
> `session.txt` 相当于 Fantia 登录密码。不要上传、分享或截图展示它。本仓库已经通过 `.gitignore` 和 `.dockerignore` 将个人 Session、配置、日志及下载内容排除在外。

## 功能

- 支持多个 Club，Club ID 每行一个。
- 默认下载最近 7 天的帖子。
- 多个帖子及帖子内的多个 Plan 内容按页面顺序处理。
- 下载帖子图片、视频、附件和封面。
- Plan 内容标题会成为独立文件夹。
- 帖子照片使用 Fantia 资源 ID 命名，例如 `照片资源ID.jpeg`。
- 帖子封面命名为 `###thumb-帖子ID.扩展名`。
- 已存在的文件直接跳过，不覆盖。
- 媒体文件及相关文件夹使用帖子更新时间作为最后修改时间。
- 可每天定时执行，适合长期开机的 Windows 电脑和 NAS。
- 可选：安全领取并下载 Club 中价格严格为 0 日元的下载商品。
- 不生成 `post.json`。

## 保存结构

```text
下载根目录/
└─ Club 名/
   ├─ YYYYMM/
   │  └─ 帖子主题名/
   │     ├─ ###thumb-帖子ID.jpeg
   │     ├─ 无标题内容的文件.扩展名
   │     └─ Plan 内容标题/（仅在内容有标题时创建）
   │        ├─ 照片资源ID.扩展名
   │        └─ 视频原始文件名.扩展名
   └─ 商品/
      └─ 商品ID_商品名/
         ├─ ###thumb-product-商品ID.jpeg
         └─ 商品文件.zip
```

帖子示例：

```text
D:\Fantia\Club名\YYYYMM\帖子主题名\Plan内容标题\原始文件名.扩展名
```

Windows 文件名不允许使用的字符会自动转换为全角字符。

如果某段 Plan 内容没有标题，或标题是旧版占位词 `内容_数字`、`无标题`、`無題`，程序不会建立额外文件夹，其媒体文件会直接保存到帖子主题文件夹。新版再次处理该帖子时，也会把旧占位目录中的文件移回帖子主题文件夹；遇到同名文件会保留原文件并跳过，不会覆盖。

## Windows 快速开始

### 1. 安装环境

需要 Python 3.9 或更高版本：

```powershell
py -m pip install -r requirements.txt
```

如果帖子使用 HLS（`m3u8`）视频，还需要安装 `ffmpeg` 并将其加入 `PATH`。直接 MP4/MOV 下载不依赖 `ffmpeg`。

### 2. 创建个人配置

在 PowerShell 中执行：

```powershell
Copy-Item session.example.txt session.txt
Copy-Item clubs.example.txt clubs.txt
Copy-Item config.example.json config.json
```

### 3. 填写 Session

1. 使用浏览器登录 [Fantia](https://fantia.jp/)。
2. 按 `F12` 打开开发者工具。
3. 打开 `Application` → `Cookies` → `https://fantia.jp`。
4. 复制 `_session_id` 的 Value。
5. 将它粘贴到 `session.txt`，文件中只保留这一行。

不要把整个 Cookie 请求头粘贴进去，只需要 `_session_id` 的值。

### 4. 填写 Club

编辑 `clubs.txt`，每行填写一个 Club ID。Club ID 是 Club 页面网址中的数字：

```text
# https://fantia.jp/fanclubs/1
1
2
```

空行和以 `#` 开头的注释会被忽略。

### 5. 修改配置

```json
{
  "session_file": "session.txt",
  "club_file": "clubs.txt",
  "download_root": "D:\\Fantia",
  "since_days": 7,
  "schedule": "03:00",
  "delay": 1.0,
  "download_free_products": false
}
```

### 6. 运行

双击 `run_fantia.bat`，或者执行：

```powershell
python fantia_downloader.py
```

运行日志保存在 `fantia_downloader.log`。

## 配置说明

| 配置项 | 默认/示例 | 说明 |
| --- | --- | --- |
| `session_file` | `session.txt` | 保存 `_session_id` 的文件，相对于 `config.json` 所在目录 |
| `club_file` | `clubs.txt` | Club ID 列表，相对于 `config.json` 所在目录 |
| `download_root` | `D:\\Fantia` | 下载根目录；Docker 中会被覆盖为 `/downloads` |
| `since_days` | `7` | 未指定 `since` 时，下载最近多少天的帖子 |
| `since` | `2026-08-01` | 可选，固定开始日期，格式为 `YYYY-MM-DD` |
| `schedule` | `03:00` | 立即执行一次后常驻，并在每天指定时间再次执行 |
| `schedule` | `null` | 立即执行一次后退出 |
| `delay` | `1.0` | 帖子/商品之间的请求间隔秒数 |
| `download_free_products` | `false` | 是否自动领取并下载 0 日元下载商品 |

命令行参数会临时覆盖配置文件：

```powershell
python fantia_downloader.py --clubs 1 2
python fantia_downloader.py --since 2026-08-01
python fantia_downloader.py --download-root E:\Fantia
python fantia_downloader.py --free-products
python fantia_downloader.py --no-free-products
```

查看所有参数：

```powershell
python fantia_downloader.py --help
```

## 0 日元下载商品

在 `config.json` 中启用：

```json
"download_free_products": true
```

启用后，程序会检查 `clubs.txt` 中每个 Club 的商品页。自动下单前必须依次通过以下检查：

1. 商品类型必须是下载商品。
2. Fantia 商品结构化数据中的价格必须严格等于 `0 JPY`。
3. 商品必须处于可领取状态，或者账号已经拥有下载权限。
4. 用户购物车必须为空；购物车中已有任何内容都会停止自动领取。
5. 加入后购物车必须只有当前目标商品。
6. 购物车合计必须明确显示为 `0円`。
7. 最终订单表单必须只包含当前商品。
8. 提交后必须取得该商品的下载权限。

以下情况不会自动购买：

- 原价大于 0 日元的商品。
- 价格无法确认的商品。
- 只显示“加入某 Plan 后 0 日元”的商品。
- 实体商品、抽选商品和投稿精选。
- 购物车中已经存在其他商品。

> [!NOTE]
> 启用该功能代表程序会在每个 0 日元订单中勾选并接受 Fantia 的隐私政策和服务条款。请先自行阅读并确认同意 Fantia 的相关条款。

## 群晖 / 飞牛 fnOS

推荐使用 Docker Compose。项目没有 Web UI，也不需要开放端口或配置 Web Station。

### 1. 下载项目

通过 SSH：

```sh
git clone https://github.com/jonathan0lau/fantia-auto-downloader.git
cd fantia-auto-downloader
```

也可以下载 GitHub ZIP，解压后将整个项目文件夹上传到 NAS。

### 2. 创建配置

```sh
cp session.example.txt session.txt
cp clubs.example.txt clubs.txt
cp config.example.json config.json
cp .env.example .env
```

编辑 `session.txt`、`clubs.txt` 和 `config.json`。然后修改 `.env` 中的 NAS 下载路径：

```dotenv
# 群晖示例
FANTIA_DOWNLOAD_DIR=/volume1/Fantia

# 飞牛 fnOS 示例，请以文件管理器显示的原始路径为准
# FANTIA_DOWNLOAD_DIR=/vol1/1000/Fantia

FANTIA_SCHEDULE=03:00
TZ=Asia/Tokyo
```

### 3. 构建并启动

```sh
docker compose up -d --build
```

容器启动后会立即运行一次，之后每天在 `FANTIA_SCHEDULE` 指定的时间运行。Compose 会把容器内的 `/downloads` 映射到 `FANTIA_DOWNLOAD_DIR`，因此 `config.json` 中的 Windows 下载路径不会影响 NAS。

在图形界面中也可以部署：

- 群晖：`Container Manager` → `项目` → `新增`，选择项目目录中的 `compose.yaml`。
- 飞牛 fnOS：`Docker` → `Compose` → `新增项目`。
- Web 门户、Web Station 和端口映射均不需要设置。

### 常用管理命令

```sh
# 查看日志
docker compose logs -f

# 重启
docker compose restart

# 停止并删除容器，不会删除映射到 NAS 的下载文件
docker compose down

# 更新源代码并重新构建
git pull
docker compose up -d --build
```

Docker 镜像已经包含 `ffmpeg`。基础镜像可在常见的 x86-64 和 ARM64 NAS 上构建，但群晖机型仍需支持 Container Manager/Docker。

## Windows 自动启动

当 `schedule` 设置为 `HH:MM` 时，程序会保持运行。若希望 Windows 开机后自动启动，可在“任务计划程序”中创建任务：

- 触发器：计算机启动时或用户登录时。
- 程序：项目目录中的 `run_fantia.bat`。
- 起始于：项目目录。

如果希望由任务计划程序每天启动一次，可将 `schedule` 设为 `null`，让每次任务完成后自动退出。

## 更新与重复下载

- 已存在且非空的文件不会覆盖。
- 更新代码不会删除个人配置或下载内容，因为它们已经被 Git 忽略。
- 如果 Fantia 上的文件被替换但文件名未改变，需要手动删除本地旧文件后再运行。
- Fantia 页面或 API 改版后，解析逻辑可能需要同步更新。

## 测试

```sh
python -m unittest discover -s tests -v
```

仓库的 GitHub Actions 会在 Python 3.9 和 Python 3.12 上自动运行测试。

## 安全与使用范围

- 本工具不会绕过付费 Plan、商品购买条件或账号权限。
- 只能下载当前 Session 所属账号已经能够访问的帖子内容，或经过 0 日元安全检查后领取的下载商品。
- 请遵守 Fantia 的服务条款以及创作者设定的使用条件。
- 下载内容仅供账号持有人在授权范围内使用，请勿未经许可重新分发。
- 本项目与 Fantia 官方无关。
