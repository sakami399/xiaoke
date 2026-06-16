# 小克聊天智能体 — 设计文档

## 概述

一个本地运行的网页聊天助手，名为"小克"，具备对话记忆、自动学习和可自定义性格的能力。

## 架构

```
浏览器 (localhost:5000)
    ↕ HTTP
Flask 后端 (app.py)
    ↕              ↕
SQLite (data.db)   DeepSeek V4-Pro API
```

## 核心功能

1. **网页聊天界面** — 浏览器打开即用，简洁聊天窗口
2. **对话记忆** — 新消息时自动搜索历史，将相关上下文发给 AI
3. **自动学习** — 定期让 AI 总结用户偏好，存入记忆库
4. **性格设定** — config.json 文件控制名字、语气、规则
5. **文章学习** — 用户可以粘贴文章/链接，让小克记住内容

## 技术栈

- 后端：Python + Flask
- 数据库：SQLite
- AI：DeepSeek API (兼容 OpenAI SDK)
- 前端：原生 HTML/CSS/JS（无需额外框架）

## 文件结构

```
chattry/
├── app.py           # 主程序
├── config.json      # 性格设定（用户编辑）
├── requirements.txt # Python 依赖
├── db/
│   └── (自动生成 data.db)
└── docs/
```

## 花费

- 本地运行：仅 API 费用，¥5-20/月
- 云端部署：API + 服务器，¥30-100/月
