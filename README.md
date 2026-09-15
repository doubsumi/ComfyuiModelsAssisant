# ComfyUI Models Assistant · ComfyUI 本地模型管理器

一个**本地运行、零第三方依赖**的 ComfyUI 模型组合探索与工作流生成工具。扫描本地模型目录，识别模型架构与角色，实时校验组合兼容性，并从兼容组合一键生成可在 ComfyUI 中加载的工作流 JSON。

- 纯 Python 标准库后端（`http.server`），无需 pip install
- 单文件原生 HTML/JS 前端，无需构建
- 所有数据保存在本地 `data/` 目录，不上传任何模型或文件信息

## 功能特性

| 模块 | 能力 |
| --- | --- |
| 模型文件管理 | 递归扫描 `models` 目录，按子目录分类、搜索过滤、自定义备注、打开所在文件夹 |
| 模型注册表 | 三层架构识别：safetensors 元数据 → tensor 名称启发式 → LLM Patch 兜底；记录架构、角色、置信度与推断依据 |
| 组合推荐引擎 | 勾选模型即时校验：缺失配套（encoder/VAE）提示、冲突诊断、LoRA 权重建议 |
| 工作流生成器 | 基于**图谱模式（Graph Pattern）**实例化节点，动态插入 LoRA、注入参数与提示词，预览 / 下载 / 保存工作流 JSON |
| 预设与收藏 | 保存常用模型组合、LoRA 权重、参数与提示词，一键恢复 |
| 提示词助手 | 内置国漫向提示词模板（水墨 / 工笔 / 动作 / 情绪 / 场景等），支持自定义模板 |
| LLM Patch 机制 | 一键复制"更新模型库"提示词，将 LLM 输出的 Patch 校验后字段级合并入注册表，全程留痕可审计 |

## 快速开始

### 环境要求

- Python 3.10+（仅使用标准库）
- Windows / macOS / Linux

### 启动

```bash
python comfyui-server.py
```

启动后自动打开浏览器（默认地址 `http://127.0.0.1:17890`，端口被占用时自动顺延）。

### 配置模型目录

首次启动后，在页面设置中把 **模型目录** 和 **ComfyUI 根目录** 改为你本机的实际路径，例如：

```
ComfyUI 根目录：E:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI
模型目录：    E:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI\models
```

配置保存在 `data/config.json`。

## 项目结构

```
ComfyuiModelsAssisant/
├── comfyui-server.py        # 入口：启动 HTTP 服务并打开浏览器
├── backend/
│   ├── config.py            # 配置管理
│   ├── routes/              # 路由层：HTTP 分发（models/registry/workflow/preset）
│   ├── services/            # 服务层：扫描、注册表、兼容性引擎、图谱构建、Patch 校验等
│   └── storage/             # 存储层：JSON 持久化、扫描缓存、预设、Patch 历史
├── frontend/
│   └── index.html           # 单页前端（原生 JS）
├── data/                    # 运行时数据（见下方说明）
│   ├── architectures.json   # 架构定义（随仓库分发）
│   └── graph_patterns/builtin/  # 各架构的图谱模式（随仓库分发）
├── docs/                    # 设计文档与接口文档
└── test/                    # 测试用 Patch JSON
```

分层约束：路由层不直接操作存储，必须经过服务层；服务层不感知 HTTP；模块间无循环依赖。

## 数据目录说明

- **随仓库分发**：`data/architectures.json`（架构定义）、`data/graph_patterns/builtin/`（内置图谱模式与提示词模板）。
- **运行时自动生成、已被 .gitignore 忽略**（含本机路径与个人内容，请勿提交）：
  - `config.json`、`scan_cache.json`、`model_registry.json`、`notes.json`、`presets.json`
  - `patches/`（LLM Patch 历史）
- 备份整个 `data/` 目录即可迁移全部注册表、预设与补丁记录。

## 扩展新架构

无需修改 Python 代码，只需两步：

1. 在 `data/architectures.json` 中添加架构定义（编码器、VAE、LoRA 兼容性等）；
2. 在 `data/graph_patterns/builtin/` 下新增对应架构的图谱模式 JSON。

新增 tensor 启发式识别规则时，在 `backend/services/model_scanner.py` 的 `ARCH_SIGNATURES` 中追加 `(正则, 权重)` 即可。

## API 概览

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/api/registry/scan` | 扫描模型目录并返回未注册模型 |
| GET | `/api/registry/update-prompt` | 生成 LLM 更新模型库提示词 |
| POST | `/api/registry/patch` | 校验并合并 LLM Patch |
| POST | `/api/compatibility/check` | 检查模型组合兼容性 |
| POST | `/api/workflow/generate` | 生成 ComfyUI 工作流 JSON |
| GET/POST/DELETE | `/api/presets` | 预设管理 |
| GET | `/api/prompts/templates` | 提示词模板列表 |

详细数据结构与接口约定见 [docs/项目接口设计文档.md](docs/项目接口设计文档.md)。

## 文档

- [项目设计文档](docs/项目设计文档.md)：背景、功能需求、数据模型、技术决策与路线图
- [项目接口设计文档](docs/项目接口设计文档.md)：数据结构与 API 契约
- [项目实现设计](docs/项目实现设计.md)：实现层面的设计细节

## 说明

本工具只生成工作流 JSON，**不会自动执行** ComfyUI 任务，也不会下载或修改任何模型文件；生成的 JSON 请在 ComfyUI 中加载后自行运行。
