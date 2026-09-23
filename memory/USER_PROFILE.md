# User Profile

## Preferences
- 语言：中文交流
- 成本敏感：优先使用免费额度 / 低价模型，避免无意义的多模型调用
- 开发偏好：优先 Python 标准库；不引入重型框架，除非明确必要
- 依赖策略：只安装确实需要的依赖
- 工程优先级：稳定运行 > 简单易维护 > 低成本 > 实际有用

## Learning directions
- 数学：数学分析、高等代数、常微分方程
- 编程与 AI：Python、数据科学、AI / Machine Learning
- 英语学习

## Long-term projects
- Aster Voss：个人 AI Agent
- AI 信息聚合 / AI News Radar
- Flashcard / PaperCard 类学习产品
- AI English Practice

## Settled technical decisions
- Aster Voss 的 LLM 层采用统一 LLMProvider 接口，默认 DeepSeek
- 模型名与 API Key 一律通过环境变量配置，不硬编码
- Jev 仅作为结构化决策层，不作为主聊天模型，普通聊天不调用
- Web 入口：FastAPI + Uvicorn + 原生 HTML/CSS/JS；CLI 保留
- 工具采用注册表结构，当前主要为 file_tool

## Notes
- 项目虚拟环境：.venv（Windows）
