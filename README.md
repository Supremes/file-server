# 📂 Kunm File Manager — 轻量级 Web 文件管理器

一个基于 FastAPI 的 Web 文件管理器，提供文件浏览、上传、下载、在线预览等功能，并内置服务器监控面板。

## ✨ 功能特性

- **文件浏览** — 目录导航，支持文件图标、大小、修改时间展示
- **文件搜索** — 递归搜索文件和目录
- **文件上传** — 支持最大 200MB 文件上传
- **文件下载** — 流式下载，支持大文件
- **在线预览** — 支持文本文件在线查看，图片/HTML 等内联预览
- **目录管理** — 创建目录、删除文件/目录、移动文件
- **路径安全** — 防止目录遍历攻击
- **服务器监控** — 内置 `/db` 仪表盘，查看 CPU、内存、磁盘、网络、进程状态
- **Token 统计** — 通过 `/api/tokens` 查看 Hermes Agent 的 token 使用量
- **CORS 支持** — 已配置跨域访问

## 🛠 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3 + FastAPI |
| 服务器 | Uvicorn |
| 前端 | 单页应用 (SPA)，深色主题 UI |
| 监控 | 读取 /proc 文件系统获取系统信息 |

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip

### 安装

```bash
# 克隆项目
git clone <repo-url> file-server
cd file-server

# 安装依赖
pip install fastapi uvicorn

# 运行
python main.py
```

服务启动后访问 `http://127.0.0.1:5800`。

### 配置

在 `main.py` 顶部可修改以下配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FILES_ROOT` | `./wwwroot/files` | 文件服务根目录 |
| `MAX_UPLOAD_SIZE` | 200MB | 最大上传文件大小 |
| `HOST` | `127.0.0.1` | 监听地址 |
| `PORT` | `5800` | 监听端口 |

## 📁 项目结构

```
file-server/
├── main.py                 # 主程序（FastAPI 后端 + API）
├── templates/
│   ├── index.html          # 文件管理前端页面
│   └── dashboard.html      # 服务器监控仪表盘
├── wwwroot/
│   └── files/              # 文件服务根目录
├── .gitignore
└── README.md
```

## 📡 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/list?path=&search=` | 列出目录内容或搜索文件 |
| GET | `/api/download?path=` | 下载文件 |
| GET | `/api/view?path=` | 在线预览文件（内联） |
| GET | `/api/read?path=&max_bytes=` | 读取文本文件内容 |
| POST | `/api/upload` | 上传文件（Header `X-Upload-Path` 指定目标目录）|
| POST | `/api/mkdir` | 创建目录 |
| DELETE | `/api/delete` | 删除文件或目录 |
| POST | `/api/move` | 移动文件/目录 |
| GET | `/api/status` | 服务器状态（CPU、内存、磁盘、网络等）|
| GET | `/api/tokens` | Hermes Agent token 使用统计 |

### 页面路由

| 路径 | 说明 |
|------|------|
| `/` | 文件管理器主页 |
| `/db` | 服务器监控仪表盘 |

## 🔒 安全说明

- 内置路径遍历防护，所有文件路径均经过安全校验
- 认证功能已预留接口（PAM 认证），当前默认关闭
- 建议在生产环境中通过 Nginx 反向代理并启用认证

## 📝 备注

- `wwwroot/files/` 为默认的文件服务根目录，存放需要管理的文件
- 监控仪表盘通过读取 Linux `/proc` 文件系统获取实时数据，仅支持 Linux
