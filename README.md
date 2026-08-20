# Fantia 自动下载器

下载当前 Fantia 账号有权查看的图片、视频和附件，也可自动领取并下载 Club 中价格严格为 0 日元的下载商品。多个 club、帖子以及帖子内多个 Plan 内容会按页面顺序处理；已经存在且非空的文件会直接跳过，不会覆盖。媒体文件、Plan 文件夹和帖子文件夹的最后修改时间会设置为帖子的更新时间；月份和 Club 公共文件夹使用其中最新帖子的更新时间。

## 安装

```powershell
py -m pip install -r requirements.txt
```

视频若是 HLS (`m3u8`) 格式，还需安装 `ffmpeg` 并加入 PATH。直接 MP4 不需要。

## 获取登录 Cookie

1. 在浏览器登录 `fantia.jp`。
2. 按 F12，打开 Application（应用）→ Cookies → `https://fantia.jp`。
3. 复制 `_session_id` 的 Value，只粘贴到本项目的 `session.txt`。它等同于登录密码，请勿分享；该文件已被 `.gitignore` 排除。

## 使用

1. 将 `session.example.txt` 复制为 `session.txt`，把其中占位文字替换成 `_session_id`，文件中只保留这一行。
2. 将 `clubs.example.txt` 复制为 `clubs.txt`，每行填写一个 Club ID：

```text
18
221384
```

3. 将 `config.example.json` 复制为 `config.json` 并编辑：

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

`schedule` 写 `null` 表示立即运行一次后退出；写 `"03:00"` 表示立即运行一次并在每天 03:00 再运行。`since_days` 默认是最近 7 天。

4. 双击 `run_fantia.bat`，或执行：

```powershell
python fantia_downloader.py
```

命令行参数仍可临时覆盖配置，例如：

```powershell
python fantia_downloader.py --clubs 18 --since 2026-08-01
```

目录结构固定为：

```text
自定义下载根目录\club名\YYYYMM\POST主题名\Plan内容标题\原始文件名
```

例如：`D:\Fantia\日暮りんのファンクラブ\202608\8／19更新\サンプルです^ ^\AVAssetExportPreset640x480.mov`。

帖子封面保存在帖子目录，命名为 `###thumb-帖子ID.扩展名`；Plan 照片使用 Fantia 照片资源 ID 命名，例如 `30046306.jpeg`。下载器不会生成 `post.json`。

## 0 日元下载商品

将 `download_free_products` 改为 `true` 后，下载器会检查 `clubs.txt` 中每个 Club 的商品页：

- 只接受 Fantia 商品结构化数据中价格**严格等于 0 JPY**的下载商品。
- 原价大于 0、仅显示“加入某 Plan 后 0 日元”的商品不会自动下单。
- 下单前要求购物车为空；如果购物车里已有任何商品，会跳过自动领取，防止误购。
- 加入购物车后再次确认购物车只有目标商品且合计为 0 日元，才提交订单。
- 启用该功能代表你同意在每次 0 日元订单中接受 Fantia 的隐私政策和服务条款。
- 商品保存在 `club名/商品/商品ID_商品名/`，封面命名为 `###thumb-product-商品ID.扩展名`。

也可以临时用命令行开启或关闭：

```powershell
python fantia_downloader.py --free-products
python fantia_downloader.py --no-free-products
```

该功能不会购买任何价格不明或大于 0 日元的商品，也不会处理实体商品、抽选商品或投稿精选。

## 自动启动

配置中的 `schedule` 会让进程常驻并每天运行。若希望开机后无人值守，使用 Windows“任务计划程序”启动 `run_fantia.bat`。日志保存在 `fantia_downloader.log`。

## 群晖 / 飞牛 fnOS（Docker）

项目已包含 `Dockerfile` 和 `compose.yaml`，可在支持 Docker Compose 的 NAS 上运行。容器启动后会立即下载一次，之后每天按 `FANTIA_SCHEDULE` 指定的时间运行；容器重启后也会继续自动运行。

1. 将整个项目文件夹上传到 NAS。务必保留 `config.json`、`session.txt` 和 `clubs.txt`，不要把 `session.txt` 放进公开镜像或分享给别人。
2. 复制 `.env.example` 为 `.env`，修改下载目录。群晖常见路径为 `/volume1/Fantia`；飞牛 fnOS 的用户目录常见形式为 `/vol1/1000/Fantia`，请以文件管理器显示的原始路径为准。
3. 在项目目录执行：

```sh
docker compose up -d --build
```

也可以在群晖“Container Manager → 项目”或飞牛“Docker → Compose”中选择本项目目录并启动。查看运行日志：

```sh
docker compose logs -f
```

停止容器：

```sh
docker compose down
```

Compose 会把容器内的 `/downloads` 映射到 `.env` 的 `FANTIA_DOWNLOAD_DIR`。`config.json` 里的 Windows 路径不会影响 NAS，因为容器启动参数会将其覆盖为 `/downloads`。HLS 视频所需的 `ffmpeg` 已包含在镜像中；镜像可在常见的 x86-64 和 ARM64 NAS 上构建。

本工具不会绕过 Plan 权限，只下载该 Cookie 所属账号已经能够查看的内容。Fantia 页面/API 改版后可能需要更新解析逻辑。

## 测试

```sh
python -m unittest discover -s tests -v
```

公开仓库不会包含 `session.txt`、`config.json`、`clubs.txt`、`.env`、日志或下载内容。请勿提交、分享或截图展示自己的 `_session_id`。
