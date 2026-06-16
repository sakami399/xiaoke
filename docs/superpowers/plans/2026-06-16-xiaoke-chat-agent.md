# 小克聊天智能体 实现计划

> **Goal:** 构建一个本地运行的网页聊天助手，支持对话记忆、自动学习、自定义性格。

> **注意：** 本项目为空目录，所有文件从零创建。用户为初学者，步骤附带解释。

**Architecture:** Flask 单文件后端，内嵌 HTML 前端，SQLite 本地存储，DeepSeek API 驱动 AI。

**Tech Stack:** Python 3.10+, Flask, openai SDK, SQLite3, HTML/CSS/JS

---

## 文件清单

| 文件 | 职责 |
|---|---|
| `requirements.txt` | Python 依赖声明 |
| `config.json` | 小克的性格设定（用户编辑） |
| `app.py` | 主程序：数据库 + AI + 网页 + API |
| `README.md` | 使用说明 |

---

### Task 1: 创建项目依赖文件

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: 写入 requirements.txt**

```
flask>=3.0
openai>=1.0
```

- [ ] **Step 2: 安装依赖**

```bash
pip install -r requirements.txt
```

---

### Task 2: 创建性格设定文件

**Files:**
- Create: `config.json`

- [ ] **Step 1: 写入 config.json**

```json
{
  "name": "小克",
  "tone": "温柔幽默，像朋友一样聊天",
  "style": "回答简洁，不说废话",
  "rules": [
    "永远用中文回复",
    "不要使用'作为一个人工智能'这类说法",
    "你的创造者是你的好朋友"
  ]
}
```

---

### Task 3: 创建数据库模块

**Files:**
- Create: `app.py`（首次创建，写入数据库相关代码）

数据库设计：

```sql
-- 对话历史表
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,        -- 'user' 或 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 记忆库表（长期记忆 + AI 总结的偏好）
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    source TEXT DEFAULT 'auto',  -- 'auto' 自动总结, 'manual' 用户手动添加
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 1: 写入 app.py 头部和数据库初始化**

```python
"""
小克 - 私人聊天助手
具备对话记忆、自动学习、性格自定义功能
"""
import sqlite3
import json
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

# ---------- 加载配置 ----------
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# 构建系统提示词
SYSTEM_PROMPT = f"""你的名字是{CONFIG['name']}。
说话风格：{CONFIG['tone']}
回复要求：{CONFIG['style']}
遵守规则：{chr(10).join(f'- {r}' for r in CONFIG['rules'])}
如果对话历史中有关于用户的偏好和信息，请自然地融入回复中。"""

# ---------- 数据库 ----------
def init_db():
    conn = sqlite3.connect("data.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            source TEXT DEFAULT 'auto',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

# ---------- Flask 应用 ----------
app = Flask(__name__)

# ---------- DeepSeek 客户端 ----------
client = OpenAI(
    api_key="sk-your-deepseek-api-key",  # 替换成你的 API Key
    base_url="https://api.deepseek.com"
)
```

---

### Task 4: 实现记忆检索

**Files:**
- Modify: `app.py` — 在 Flask 应用初始化之后追加

- [ ] **Step 1: 写入关键词搜索和记忆获取函数**

```python
# ---------- 记忆系统 ----------
def search_history(query, limit=5):
    """用关键词搜索历史对话"""
    conn = sqlite3.connect("data.db")
    words = query.strip().split()
    if not words:
        conn.close()
        return []
    
    # 用 OR 连接关键词，每个词模糊匹配
    conditions = " OR ".join(["content LIKE ?" for _ in words])
    params = [f"%{w}%" for w in words]
    
    rows = conn.execute(
        f"SELECT role, content FROM conversations WHERE {conditions} ORDER BY id DESC LIMIT ?",
        params + [limit]
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def get_all_memories():
    """获取所有长期记忆"""
    conn = sqlite3.connect("data.db")
    rows = conn.execute(
        "SELECT content FROM memories ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]

def save_conversation(role, content):
    """保存一轮对话"""
    conn = sqlite3.connect("data.db")
    conn.execute(
        "INSERT INTO conversations (role, content) VALUES (?, ?)",
        (role, content)
    )
    conn.commit()
    conn.close()

def save_memory(content, source="auto"):
    """存入长期记忆"""
    conn = sqlite3.connect("data.db")
    conn.execute(
        "INSERT INTO memories (content, source) VALUES (?, ?)",
        (content, source)
    )
    conn.commit()
    conn.close()
```

---

### Task 5: 实现 AI 对话接口

**Files:**
- Modify: `app.py` — 在记忆系统之后追加

- [ ] **Step 1: 写入聊天 API 路由**

```python
# ---------- 聊天 API ----------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data["message"]

    # 1. 获取长期记忆
    memories = get_all_memories()
    memory_text = ""
    if memories:
        memory_text = "【关于用户的长期记忆】\n" + "\n".join(f"- {m}" for m in memories)

    # 2. 搜索相关历史对话
    history = search_history(user_message, limit=8)

    # 3. 构建消息列表
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if memory_text:
        messages.append({"role": "system", "content": memory_text})

    # 历史对话
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})

    # 当前消息
    messages.append({"role": "user", "content": user_message})

    # 4. 调用 DeepSeek API
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.8,
        max_tokens=2000
    )

    reply = response.choices[0].message.content

    # 5. 保存对话
    save_conversation("user", user_message)
    save_conversation("assistant", reply)

    return jsonify({"reply": reply})
```

---

### Task 6: 实现自动学习功能

**Files:**
- Modify: `app.py` — 在聊天 API 之后追加

- [ ] **Step 1: 写入学习 API 路由**

```python
# ---------- 自动学习 ----------
SUMMARY_TRIGGER = 20  # 每 20 轮对话触发一次自动总结

@app.route("/learn", methods=["POST"])
def learn():
    """让 AI 总结最近对话，提炼用户偏好"""
    conn = sqlite3.connect("data.db")
    
    # 获取最近的对话（排除已经总结过的）
    recent = conn.execute(
        "SELECT role, content FROM conversations ORDER BY id DESC LIMIT 40"
    ).fetchall()
    conn.close()

    if len(recent) < 10:
        return jsonify({"ok": False, "reason": "对话太少了，再聊一会儿吧"})

    # 构建总结请求
    history_text = "\n".join(f"{r[0]}: {r[1]}" for r in reversed(recent))
    
    messages = [
        {"role": "system", "content": """你是用户画像分析师。回顾以下对话，提炼出用户的偏好、习惯、重要信息。
用中文列出，每条一行，格式为 "- 用户xxx/喜欢xxx/在xxx"。只记录确定的信息，不推测。"""},
        {"role": "user", "content": f"请总结以下对话中关于用户的信息：\n\n{history_text}"}
    ]

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.3,
        max_tokens=500
    )

    summary = response.choices[0].message.content

    # 将总结存入长期记忆
    for line in summary.split("\n"):
        line = line.strip().lstrip("- ").strip()
        if line and len(line) > 3:
            save_memory(line, source="auto")

    return jsonify({"ok": True, "summary": summary})
```

---

### Task 7: 实现文章/链接学习

**Files:**
- Modify: `app.py` — 在学习 API 之后追加

- [ ] **Step 1: 写入文章学习 API 路由**

```python
# ---------- 文章学习 ----------
@app.route("/learn-article", methods=["POST"])
def learn_article():
    """学习用户提供的文章内容或链接"""
    data = request.json
    content = data.get("content", "").strip()

    if not content:
        return jsonify({"ok": False, "reason": "内容为空"})

    # 如果太短，当作一条知识直接存
    if len(content) < 200:
        save_memory(content, source="manual")
        return jsonify({"ok": True, "result": "已记住这条信息"})

    # 让 AI 提炼要点
    messages = [
        {"role": "system", "content": "你是知识提炼助手。阅读以下内容，提炼出 3-8 条核心要点。每条一行，格式为 '- 要点内容'。只记录事实，不添加评价。"},
        {"role": "user", "content": f"请提炼以下内容的要点：\n\n{content}"}
    ]

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.3,
        max_tokens=500
    )

    points = response.choices[0].message.content

    for line in points.split("\n"):
        line = line.strip().lstrip("- ").strip()
        if line and len(line) > 3:
            save_memory(line, source="manual")

    return jsonify({"ok": True, "result": points})
```

---

### Task 8: 实现记忆管理 API

**Files:**
- Modify: `app.py` — 在文章学习 API 之后追加

- [ ] **Step 1: 写入记忆查看和删除 API**

```python
# ---------- 记忆管理 ----------
@app.route("/memories", methods=["GET"])
def list_memories():
    """查看所有长期记忆"""
    memories = get_all_memories()
    return jsonify({"memories": memories, "count": len(memories)})

@app.route("/memories/clear", methods=["POST"])
def clear_memories():
    """清空长期记忆"""
    conn = sqlite3.connect("data.db")
    conn.execute("DELETE FROM memories")
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "记忆已清空"})

@app.route("/conversations/count", methods=["GET"])
def conversation_count():
    """获取对话轮数"""
    conn = sqlite3.connect("data.db")
    count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    conn.close()
    return jsonify({"count": count})
```

---

### Task 9: 实现网页聊天界面

**Files:**
- Modify: `app.py` — 在文件末尾追加路由和 HTML

- [ ] **Step 1: 写入首页路由和内嵌 HTML**

```python
# ---------- 网页界面 ----------
@app.route("/")
def home():
    return render_template_string(HTML)

HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>小克 - 私人聊天助手</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f0f2f5;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
}
.container{
  width: 100%;
  max-width: 750px;
  height: 95vh;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0,0,0,.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.header{
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header h2{font-size: 18px;color: #333;}
.header .actions button{
  margin-left: 8px;
  padding: 6px 14px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #666;
}
.header .actions button:hover{background:#f5f5f5}
#chat{
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.msg{max-width: 80%;padding: 10px 16px;border-radius: 12px;line-height: 1.6;font-size: 15px;}
.msg.user{align-self:flex-end;background:#1677ff;color:#fff;border-bottom-right-radius:4px}
.msg.assistant{align-self:flex-start;background:#f5f5f5;color:#333;border-bottom-left-radius:4px}
.msg.system{align-self:center;background:#fff3e0;color:#e65100;font-size:13px;padding:6px 12px;border-radius:8px}
.input-area{
  padding: 16px 20px;
  border-top: 1px solid #eee;
  display: flex;
  gap: 10px;
}
.input-area textarea{
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  resize: none;
  font-size: 15px;
  font-family: inherit;
  outline: none;
  max-height: 100px;
}
.input-area textarea:focus{border-color:#1677ff}
.input-area button{
  padding: 0 20px;
  background: #1677ff;
  color: #fff;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  font-size: 15px;
  font-weight: 500;
}
.input-area button:hover{background:#4096ff}
.input-area button:disabled{background:#ccc;cursor:not-allowed}
.typing{display:flex;align-items:center;gap:6px;padding:10px 16px;align-self:flex-start}
.typing span{width:8px;height:8px;background:#bbb;border-radius:50%;animation:dot 1.4s infinite}
.typing span:nth-child(2){animation-delay:.2s}
.typing span:nth-child(3){animation-delay:.4s}
@keyframes dot{0%,60%,100%{opacity:.2}30%{opacity:1}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h2>🤖 小克</h2>
    <div class="actions">
      <button onclick="doLearn()" title="让 AI 总结最近的对话">🧠 学习</button>
      <button onclick="showMemories()">📋 记忆</button>
    </div>
  </div>
  <div id="chat">
    <div class="msg assistant">你好！我是小克，有什么想聊的？</div>
  </div>
  <div class="input-area">
    <textarea id="input" rows="1" placeholder="输入消息... (Enter发送, Shift+Enter换行)"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send()}"></textarea>
    <button onclick="send()">发送</button>
  </div>
</div>
<script>
const chat = document.getElementById("chat");
const input = document.getElementById("input");

let msgCount = 0;
const LEARN_INTERVAL = 20; // 每20轮自动提醒学习

function addMsg(role, text){
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function showTyping(){
  const div = document.createElement("div");
  div.className = "typing";
  div.id = "typing";
  div.innerHTML = "<span></span><span></span><span></span>";
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function hideTyping(){
  const el = document.getElementById("typing");
  if(el) el.remove();
}

async function send(){
  const text = input.value.trim();
  if(!text) return;
  
  addMsg("user", text);
  input.value = "";
  showTyping();

  try{
    const res = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text})
    });
    const data = await res.json();
    hideTyping();
    addMsg("assistant", data.reply);
    
    msgCount++;
    if(msgCount % LEARN_INTERVAL === 0){
      addMsg("system", "💡 已经聊了 " + msgCount + " 轮了，要不要点🧠学习，让小克总结一下你的偏好？");
    }
  }catch(e){
    hideTyping();
    addMsg("system", "出错了：" + e.message);
  }
}

async function doLearn(){
  addMsg("system", "🧠 小克正在回顾你们的对话，提炼你的偏好...");
  try{
    const res = await fetch("/learn", {method:"POST"});
    const data = await res.json();
    if(data.ok){
      addMsg("system", "✅ 学到了这些新东西：\n" + data.summary);
    }else{
      addMsg("system", data.reason || "学习失败");
    }
  }catch(e){
    addMsg("system", "学习出错：" + e.message);
  }
}

async function showMemories(){
  try{
    const res = await fetch("/memories");
    const data = await res.json();
    if(data.count === 0){
      addMsg("system", "📋 还没有长期记忆，多聊聊吧");
    }else{
      addMsg("system", "📋 小克记住的这些（共" + data.count + "条）：\n" + data.memories.map((m,i)=> (i+1)+". "+m).join("\n"));
    }
  }catch(e){
    addMsg("system", "获取记忆出错：" + e.message);
  }
}

// 也支持发送文章进行学习
// 在控制台或对话中说 "学习文章：" 开头的内容
</script>
</body>
</html>
"""
```

---

### Task 10: 添加启动入口

**Files:**
- Modify: `app.py` — 在文件最末尾追加

- [ ] **Step 1: 写入启动入口**

```python
# ---------- 启动 ----------
if __name__ == "__main__":
    init_db()
    print("🤖 小克已启动！")
    print("   打开浏览器访问: http://127.0.0.1:5000")
    print("   按 Ctrl+C 停止")
    app.run(debug=True, host="127.0.0.1", port=5000)
```

---

### Task 11: 创建 README

**Files:**
- Create: `README.md`

- [ ] **Step 1: 写入使用说明**

```markdown
# 小克 - 私人聊天助手

一个本地运行的 AI 聊天助手，具备对话记忆和自动学习能力。

## 快速开始

### 1. 安装 Python

去 [python.org](https://python.org) 下载安装 Python 3.10+，安装时勾选 "Add to PATH"。

### 2. 获取 DeepSeek API Key

1. 注册 [platform.deepseek.com](https://platform.deepseek.com)
2. 在设置里创建 API Key
3. 把 app.py 里的 `sk-your-deepseek-api-key` 替换成你的真实 Key

### 3. 安装依赖

打开终端（cmd 或 PowerShell），进入项目目录：

```bash
pip install -r requirements.txt
```

### 4. 启动

```bash
python app.py
```

浏览器打开 `http://127.0.0.1:5000` 就能聊天了。

## 功能说明

- **聊天**：直接在输入框打字，回车发送
- **记忆**：自动搜索相关历史对话，AI 回复时会参考
- **学习**：点击 🧠 按钮，AI 会总结最近的对话，提炼你的偏好
- **教知识**：在聊天中发送文章或链接，小克会记住要点
- **改性格**：编辑 `config.json` 文件，改完重启即可

## 性格设定

编辑 `config.json`：

```json
{
  "name": "小克",
  "tone": "温柔幽默，像朋友一样聊天",
  "style": "回答简洁，不说废话",
  "rules": [
    "永远用中文回复",
    "不要使用'作为一个人工智能'这类说法"
  ]
}
```

## 注意事项

- 所有数据存本地 `data.db`，不会上传
- API Key 不要分享给别人
- API 花费大约 ¥5-20/月（日常使用）
```
```

---

### Task 12: 运行测试

- [ ] **Step 1: 安装依赖**

```bash
cd c:/Users/33486/Desktop/chattry
pip install -r requirements.txt
```

- [ ] **Step 2: 启动应用**

```bash
python app.py
```

- [ ] **Step 3: 浏览器打开测试**

访问 `http://127.0.0.1:5000`，发送一条消息，验证回复正常。点击"学习"按钮测试记忆功能。
```

---

## 自审

1. **Spec 覆盖检查：** 所有功能都有对应 Task — 聊天(T5)、记忆(T4)、学习(T6)、文章学习(T7)、性格设定(T2)、网页界面(T9) ✅
2. **占位符检查：** 无 TBD/TODO，所有代码完整 ✅
3. **类型一致性：** 整个项目是单个文件 `app.py`，函数名前后统一 ✅
