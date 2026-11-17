# 知识切片 · 视频转文字（knowledge-slice-als）

上传视频 → 服务端用 ffmpeg 分离音轨 → 调用讯飞 / 腾讯云语音识别 → 生成带时间轴的文字稿。

- **后端**：Python + Flask（任务队列、SQLite 持久化、ffmpeg 封装）
- **前端**：Vue 3 + Vuetify 3（上传、进度轮询、视频播放联动时间轴、搜索、SRT/VTT/TXT 导出）

## 功能

- 视频上传（MP4 / MOV / MKV / AVI / WEBM 等），上传上限可配置
- ffmpeg 自动提取音轨，统一转为 16kHz 单声道 PCM，并带进度回报
- 两种转写服务商可切换：
  - **讯飞开放平台 · 语音听写（流式版 WebSocket）**：长音频自动按静音点切成 ≤55s 小段逐段转写
  - **腾讯云 · 录音文件识别**：base64 直接提交（无需公网 URL），长音频按静音点切成 ≤280s 的 mp3 片（约 1.2MB/片，低于接口 5MB 限制）逐片转写，支持词级时间戳与说话人分离
  - **模拟转写（开发调试）**：无需任何密钥即可跑通全流程
- 带时间轴的文字稿：点击任意一句跳转视频对应位置，播放时高亮并自动跟随
- 全文搜索、复制全部文字稿、导出 SRT / VTT / 纯文本
- 深浅色主题

## 环境要求

- Python 3.10+，Node 18+，ffmpeg（`ffmpeg`、`ffprobe` 在 PATH 中）

## 快速开始

### 1. 后端

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # 按需填写密钥（见下方配置说明）
.venv/bin/python app.py       # 默认 http://127.0.0.1:5000
```

### 2. 前端

开发模式（Vite 热更新，/api 自动代理到 5000 端口）：

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

生产模式（构建后由 Flask 直接托管，只启动后端即可）：

```bash
cd frontend && npm run build
# 然后访问 http://127.0.0.1:5000
```

## 配置（backend/.env）

### 讯飞开放平台

1. 注册 [讯飞开放平台](https://console.xfyun.cn/)，创建应用
2. 开通「语音听写（流式版）」服务
3. 在应用详情中获取 `APPID` / `APIKey` / `APISecret` 填入：

```ini
XFYUN_APP_ID=你的APPID
XFYUN_API_KEY=你的APIKey
XFYUN_API_SECRET=你的APISecret
```

可选调优：

- `XFYUN_CHUNK_SECONDS=55` — 每段音频上限（接口每会话约 60s）
- `XFYUN_FRAME_SLEEP=0.01` — 发帧间隔，约 4 倍速发送；调大更稳，`0` 为全速

### 腾讯云

1. [腾讯云](https://console.cloud.tencent.com/asr) 开通「录音文件识别」
2. 在 [API 密钥管理](https://console.cloud.tencent.com/cam/capi) 获取 `SecretId` / `SecretKey` 填入：

```ini
TENCENT_SECRET_ID=你的SecretId
TENCENT_SECRET_KEY=你的SecretKey
TENCENT_ENGINE=16k_zh        # 可选 16k_zh / 16k_zh_video / 16k_zh_large / 8k_zh
```

### 开发调试

```ini
ENABLE_MOCK_PROVIDER=1        # 前端出现「模拟转写」选项，无需密钥
```

未配置任何密钥时，前端会上传区提示；配置完成后重启后端生效。

## 时间轴说明

| 服务商 | 时间戳来源 |
| --- | --- |
| 腾讯云 | 优先解析 `ResultDetail` 的句级 `StartMs` / `EndMs`（毫秒）+ 分片偏移；兼容 `Result` 的 JSON / 纯文本格式 |
| 讯飞语音听写 | 按静音点切分的小段内，按标点切句、按字数比例分摊时间 |
| 模拟转写 | 固定间隔生成的演示句 |

长音频切分优先落在**静音中点**（ffmpeg silencedetect），尽量避免切断句子；若整段没有静音，按固定上限硬切。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/transcriptions` | 上传视频创建转写任务（multipart：`file`、`provider`、`options` JSON） |
| GET | `/api/transcriptions` | 任务列表 |
| GET | `/api/transcriptions/<id>` | 任务状态与进度 |
| GET | `/api/transcriptions/<id>/result` | 带时间轴的文字稿 |
| GET | `/api/transcriptions/<id>/export?format=srt\|vtt\|txt` | 导出字幕 |
| GET | `/api/transcriptions/<id>/video` | 视频回放（支持 Range） |
| POST | `/api/transcriptions/<id>/retry` | 失败任务重试（复用已上传视频，无需重新上传） |
| DELETE | `/api/transcriptions/<id>` | 删除任务及文件 |
| GET | `/api/config` | 服务商可用性、上传限制等 |

腾讯云 `options` 示例：`{"engine": "16k_zh", "speaker_diarization": true}`

## 测试

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -v
```

覆盖：任务全流程（模拟转写）、上传校验、无音轨视频拒绝、SRT/VTT/TXT 导出、视频 Range 请求、静音检测、分片规划、切句。

## 目录结构

```
backend/
  app.py              Flask 入口与 API 路由
  config.py           环境变量配置
  db.py               SQLite 任务存储
  jobs.py             后台任务：抽音轨 -> 转写 -> 生成文字稿
  media.py            ffmpeg 封装：探测 / 抽音轨 / 静音检测 / 切分
  utils.py            切句、时间格式、字幕导出
  providers/          转写服务商（xfyun / tencent / mock，统一接口）
  tests/              unittest 测试
  storage/            上传视频、音轨、数据库（自动生成）
frontend/
  src/views/HomeView.vue   上传 + 任务列表
  src/views/JobView.vue    播放器 + 时间轴文字稿联动
```

## 常见问题

- **浏览器放不了 MKV / HEVC 视频**：文字稿与时间轴不受影响，页面会提示可本地播放对照。
- **上传超时 / 文件过大**：调大 `MAX_UPLOAD_MB`；如经 nginx 反代需同步调大 `client_max_body_size`。
- **服务重启后任务中断**：重启时后端会自动把未完成任务重新排队。
- **任务失败**：在任务详情页点击「重新转写」，会复用已上传的视频重新执行，无需再次上传。
- **讯飞转写速度**：IAT 按帧间隔发送音频，`XFYUN_FRAME_SLEEP` 越小越快，过快可能被服务端限流，请按账号配额调整。
