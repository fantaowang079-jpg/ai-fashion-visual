# 衣镜 Studio · 电商服饰 AI 视觉工作台

一个可运行的电商服饰 AI 视觉演示项目：**AI 换装 / 虚拟试衣 / 智能穿搭 / 图生视频 / 历史记录 / Lookbook 导出**。

> 个人全栈演示项目，重点不是「调通一个生图 API」，而是把多模型接入、路由降级、任务持久化、SSE 进度、成本台账和失败兜底做成一条完整链路。

## 功能

- **AI 换装**：人物图 + 自然语言指令，换色 / 换款 / 加外套；支持按目标服装图换衣
- **虚拟试衣**：人物图 + 服装图，默认 qwen-image 图像编辑；可选专用试衣引擎
- **智能穿搭**：LLM 只从 22 件内置衣橱选品，输出 3 套结构化方案
- **图生视频**：首帧图 → 5/10 秒短视频（百炼万相）
- **内置模特库**：45 个模特，按女 / 男 / 童筛选
- **历史记录**：缩略图、单张/整条删除、SQLite 持久化
- **Lookbook**：ZIP 导出主图 3:4、详情图 1:1、原图、文案、Prompt、成本清单
- **成本台账**：图片按张、视频按秒，预估费用 + JSONL 台账
- **多模型路由**：主模型 + 备选链，模型不可用时自动降级

## 演示素材

截图与视频在独立仓库：

**https://github.com/fantaowang079-jpg/ai-fashion-visual-demo**

（Gitee 镜像：`https://gitee.com/zjlhslyjsf0036/ai-fashion-visual-demo`）

## 技术栈

- **后端**：Python 3.12、FastAPI、Uvicorn、Pydantic、SQLite、Pillow
- **前端**：原生 HTML / CSS / JavaScript、Fetch、SSE、File API（无构建步骤）
- **模型**：阿里云百炼 qwen-image / qwen-vl / wan2.5-i2v；可选火山方舟 Seedream / Seedance
- **工程**：Provider 抽象、模型路由与降级、SSE、SQLite 任务持久化、成本台账、73 项单元测试

## 快速开始

```bash
cd replica
python -m pip install -r requirements.txt
copy .env.example .env   # 填写 DASHSCOPE_API_KEY
python app.py
```

浏览器打开：<http://127.0.0.1:8000>

Windows 也可以双击 `replica/launch_workbench.bat`，脚本会自动检查 Python、依赖和端口。

## 文档

- [replica 使用说明](replica/README.md)

## 说明

- 仓库只保留项目本体；演示截图/视频在独立仓库，需求文档与技术笔记不上传。
- 仓库不包含 `.env`、上传素材、生成结果和本地数据库；克隆后需自行配置 Key。
- 项目为演示用途，模型 ID、价格与配额以阿里云 / 火山控制台为准。
- 参考项目与 MIT 许可证说明见 [replica/README.md](replica/README.md) 第 9 节。
