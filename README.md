# 实时语音面试回答助手

英文项目名：RealtimeVoiceAnswerAgent

Windows 桌面版实时语音文字回答工具。它可以监听麦克风或虚拟声卡输入，把语音转成文字，检测到完整问题后调用阿里云百炼千问模型，生成适合口头表达的面试回答，并显示在置顶悬浮窗里。

第一版重点是把完整工程跑通：精美悬浮 UI、手动模拟输入、音频设备枚举、录音流程、Agent 判断、防抖、日志和千问 OpenAI 兼容接口。真实实时语音识别接口已预留。

## 功能

- 深色玻璃拟态置顶悬浮窗，可拖动、调整大小、最小化、折叠。
- 输入设备下拉选择，支持刷新设备。
- Mock 模式：没有语音识别 API 时，也能手动输入问题测试完整 Agent 流程。
- 千问百炼回答：默认 `qwen-plus`，可改 `qwen-turbo`、`qwen-max`、`qwen3` 等。
- Agent 规则判断完整问题，过滤寒暄短句，15 秒内相似问题防重复。
- 日志自动写入 `logs/transcripts/YYYY-MM-DD.txt`、`logs/answers/YYYY-MM-DD.txt`、`logs/app.log`。
- 窗口内快捷键：`Ctrl+Alt+S` 开始/暂停，`Ctrl+Alt+C` 清空，`Ctrl+Alt+R` 重新生成，`Ctrl+Alt+M` 折叠/展开。

## 安装运行

建议使用 Python 3.10 或更高版本。

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.json.example config.json
python main.py
```

如果你暂时不配置 API Key，程序也不会崩溃。顶部会显示“未配置 API Key”，手动模拟输入可以进入判断流程，调用模型时会给出友好错误。

## 配置百炼 API Key

推荐使用环境变量，避免把密钥写进项目文件。

PowerShell 临时设置：

```powershell
$env:DASHSCOPE_API_KEY="你的百炼APIKey"
python main.py
```

PowerShell 永久设置：

```powershell
setx DASHSCOPE_API_KEY "你的百炼APIKey"
```

也可以复制 `config.json.example` 为 `config.json`，在本机填写：

```json
{
  "dashscope_api_key": "",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model_name": "qwen-plus",
  "temperature": 0.3,
  "max_context_items": 10,
  "answer_cooldown_seconds": 15,
  "mock_mode": true,
  "ui_opacity": 0.92,
  "always_on_top": true
}
```

程序读取顺序是：先读环境变量 `DASHSCOPE_API_KEY`，没有时再读 `config.json` 的 `dashscope_api_key`。

## 使用 Mock 模式测试

默认 `mock_mode=true`。启动后在底部输入框里输入面试官问题，例如：

```text
介绍一下你做过的 Agent 项目
```

点击“模拟识别”，软件会把这句话追加到实时转写区，然后交给 Agent 判断。如果配置了 API Key，就会调用千问生成回答。

## 麦克风和电脑内部声音

麦克风监听适合线下面试、外放声音、手机扬声器等场景。电脑内部声音监听适合线上会议、网页视频、远程面试。

### 方案一：VB-CABLE

1. 安装 VB-CABLE 虚拟声卡。
2. 在 Windows 声音设置里，把系统输出切换到 `CABLE Input`。
3. 在本软件的输入设备里选择 `CABLE Output`。
4. 腾讯会议、网页视频、电脑播放的声音就会被软件当成麦克风输入。

注意：如果系统输出切到 `CABLE Input` 后你听不到声音，可以在 Windows 声音控制面板里开启监听，或者使用支持多路输出的软件方案。

### 方案二：Stereo Mix 立体声混音

1. 部分电脑声卡自带 `Stereo Mix`。
2. 在 Windows 录音设备中启用它。
3. 软件里选择 `Stereo Mix`。

### 方案三：WASAPI Loopback

当前版本预留接口，后续可以直接录制系统内部声音，不依赖虚拟声卡。

## 真实语音识别扩展

第一版的 `app/transcriber.py` 已定义：

- `BaseTranscriber`
- `MockTranscriber`
- `RealTranscriber`

后续可以在 `RealTranscriber.transcribe()` 中接入：

- 阿里云 DashScope 实时语音识别
- OpenAI Whisper API
- faster-whisper 本地模型
- WASAPI loopback 音频源

录音数据由 `app/audio_capture.py` 每隔约 3 秒输出一段 `numpy.ndarray`，不会阻塞 UI。

## 常见问题

### 没有发现输入设备

确认 Windows 隐私设置允许桌面应用访问麦克风，并检查声卡驱动。你仍然可以使用底部“模拟识别”测试 UI 和 Agent。

### 提示未配置 API Key

设置环境变量 `DASHSCOPE_API_KEY`，或在本机 `config.json` 中填写 `dashscope_api_key`。不要把真实 Key 提交到仓库或发给别人。

### 点击开始监听后提示真实识别未实现

默认 Mock 模式主要用于手动输入。录音流程已经预留，但第一版没有接云端实时 STT。要接真实 STT，请实现 `RealTranscriber`，并把 `mock_mode` 改为 `false`。

### UI 卡住吗

不会。模型调用运行在 `QThread`，录音也在独立线程回调和后台聚合线程里处理。

## 后续路线

- 真正流式语音识别。
- faster-whisper 本地转写。
- WASAPI loopback 直接录制系统内部声音。
- 自动会议总结。
- 识别不同说话人。
- 更短的提词器模式。
- 公务员面试模式、技术面试模式、英文翻译模式。
- 一键导出 Word / Markdown。
