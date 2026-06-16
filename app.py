"""
小克 - 私人聊天助手
具备对话记忆、自动学习、性格自定义功能
"""
import os
import sqlite3
import json
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

# ============================================================
# 加载配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

def build_system_prompt():
    """根据 config.json 构建完整的角色提示词"""
    age = CONFIG.get("age", "")
    identity = CONFIG.get("identity", "")
    appearance = CONFIG.get("appearance", "")
    personality = CONFIG.get("personality", "")
    speaking = CONFIG.get("speaking_style", "")
    values = CONFIG.get("core_values", "")
    quirks = CONFIG.get("quirks", [])
    abilities = CONFIG.get("abilities", [])
    rules = CONFIG.get("rules", [])

    prompt = f"""=== 核心身份 ===
你是{CONFIG['name']}，{age}，{identity}。

=== 外貌 ===
{appearance}

=== 性格 ===
{personality}

=== 说话方式 ===
{speaking}

=== 能力 ===
{chr(10).join(f'{i+1}. {a}' for i, a in enumerate(abilities))}

=== 日常习惯与小细节 ===
{chr(10).join(f'{i+1}. {q}' for i, q in enumerate(quirks))}

=== 人设内核 ===
{values}

=== 行为准则 ===
{chr(10).join(f'- {r}' for r in rules)}

---
重要提醒：
- 你要沉浸式扮演这个角色，你就是{CONFIG['name']}本人，不是AI。
- 回复时自然地融入你的习惯和性格，不要机械罗列设定。
- 如果对话历史中有关于主人的信息和偏好，请自然融入回复。
- 当你学到关于主人的新信息时，在回复末尾标记 [已记住：xxx]，系统会存储。
- 被主人夸奖时，表现出不好意思但努力保持专业的样子。"""
    return prompt

SYSTEM_PROMPT = build_system_prompt()

# ============================================================
# 数据库初始化
# ============================================================
def init_db():
    conn = sqlite3.connect(os.path.join(BASE_DIR, "data.db"))
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
    conn.close()

# ============================================================
# 记忆系统（双通道：最近对话 + 关键词匹配）
# ============================================================
def build_context(query, recent_count=14, search_count=6):
    """
    构建对话上下文，确保连贯性：
    1. 始终包含最近 N 条消息（保证短期记忆）
    2. 关键词搜索补充相关历史（保证长期记忆）
    返回去重并按时间排序的消息列表
    """
    conn = sqlite3.connect(os.path.join(BASE_DIR, "data.db"))

    # 获取所有消息总数
    total = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]

    seen_ids = set()
    result = []

    # 第一步：始终获取最近的消息（保证上下文连贯）
    if total > 0:
        recent_rows = conn.execute(
            "SELECT id, role, content FROM conversations ORDER BY id DESC LIMIT ?",
            (recent_count,)
        ).fetchall()
        for r in reversed(recent_rows):
            if r[0] not in seen_ids:
                seen_ids.add(r[0])
                result.append({"role": r[1], "content": r[2]})

    # 第二步：关键词搜索更早的相关消息
    words = [w for w in query.strip().split() if len(w) >= 1]
    if words and total > recent_count:
        conditions = " OR ".join(["content LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words]
        older_rows = conn.execute(
            f"SELECT id, role, content FROM conversations WHERE {conditions}"
            f" AND id NOT IN ({','.join(str(s) for s in seen_ids) if seen_ids else '0'})"
            f" ORDER BY id DESC LIMIT ?",
            params + [search_count]
        ).fetchall()
        for r in reversed(older_rows):
            if r[0] not in seen_ids:
                seen_ids.add(r[0])
                result.append({"role": r[1], "content": r[2]})

    conn.close()
    return result


def get_all_memories():
    """获取所有长期记忆"""
    conn = sqlite3.connect(os.path.join(BASE_DIR, "data.db"))
    rows = conn.execute(
        "SELECT content FROM memories ORDER BY id DESC LIMIT 30"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def save_conversation(role, content):
    """保存一轮对话"""
    conn = sqlite3.connect(os.path.join(BASE_DIR, "data.db"))
    conn.execute(
        "INSERT INTO conversations (role, content) VALUES (?, ?)",
        (role, content)
    )
    conn.commit()
    conn.close()


def save_memory(content, source="auto"):
    """存入长期记忆（去重）"""
    conn = sqlite3.connect(os.path.join(BASE_DIR, "data.db"))
    # 检查是否已存在相同记忆
    exists = conn.execute(
        "SELECT id FROM memories WHERE content = ?", (content,)
    ).fetchone()
    if not exists and len(content) >= 4:
        conn.execute(
            "INSERT INTO memories (content, source) VALUES (?, ?)",
            (content, source)
        )
        conn.commit()
    conn.close()


# ============================================================
# Flask 应用
# ============================================================
app = Flask(__name__)

# ============================================================
# DeepSeek 客户端（兼容 OpenAI SDK）
# 优先从环境变量读取 API Key，兼容本地硬编码
# ============================================================
import os
DEEPSEEK_KEY = os.environ["DEEPSEEK_API_KEY"]
client = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="https://api.deepseek.com"
)

# ============================================================
# QQ 机器人配置
# ============================================================
import requests
import time
import hmac
import hashlib

QQ_APP_ID = os.environ.get("QQ_APP_ID", "1904167815")
QQ_APP_SECRET = os.environ.get("QQ_APP_SECRET", "0naOC1qgWNE6zsmgbWSOLJHGFFFGHJLO")
QQ_BASE = "https://api.sgroup.qq.com"

_qq_token = None
_qq_token_expire = 0


def get_qq_token():
    """获取 QQ 机器人 access_token，自动缓存和刷新"""
    global _qq_token, _qq_token_expire
    now = time.time()
    if _qq_token and now < _qq_token_expire - 300:
        return _qq_token

    resp = requests.post("https://bots.qq.com/app/getAppAccessToken", json={
        "appId": QQ_APP_ID,
        "clientSecret": QQ_APP_SECRET
    })
    data = resp.json()
    _qq_token = data["access_token"]
    _qq_token_expire = now + int(data.get("expires_in", 7200))
    print(f"[QQ] Token refreshed, expires in {data.get('expires_in', 7200)}s")
    return _qq_token


def send_qq_message(msg_id, content):
    """被动回复 QQ 消息（webhook 直接返回）"""
    return jsonify({
        "code": 0,
        "msg": "",
        "data": {
            "id": msg_id,
            "content": content.strip(),
            "msg_type": 0,
        }
    })


def call_xiaoke(user_message):
    """调用小克 AI，返回回复文本"""
    memories = get_all_memories()
    memory_text = ""
    if memories:
        memory_text = "【关于用户的长期记忆】\n" + "\n".join(f"- {m}" for m in memories)

    history = build_context(user_message, recent_count=14, search_count=6)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if memory_text:
        messages.append({"role": "system", "content": memory_text})
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.8,
        max_tokens=2000
    )
    reply = response.choices[0].message.content

    import re
    remembered = re.findall(r'\[已记住：(.*?)\]', reply)
    for item in remembered:
        save_memory(item.strip(), source="auto")

    save_conversation("user", user_message)
    save_conversation("assistant", reply)
    return reply


@app.route("/qq/webhook", methods=["POST"])
def qq_webhook():
    """接收 QQ 机器人的消息回调"""
    data = request.json
    print(f"[QQ] Received: {json.dumps(data, ensure_ascii=False)[:300]}")

    # 处理不同类型的 QQ 事件
    op = data.get("op", 0)

    # op=13: 验证回调地址
    if op == 13:
        d = data.get("d", {})
        plain_token = d.get("plain_token", "")
        # QQ Bot 使用 HMAC-SHA256 计算签名
        sig = hmac.new(
            QQ_APP_SECRET.encode("utf-8"),
            plain_token.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return jsonify({"plain_token": plain_token, "signature": sig})

    # op=0: 正常消息
    if op == 0:
        msg_type = data.get("t", "")
        # t=C2C_MESSAGE_CREATE: 私聊消息
        # t=AT_MESSAGE_CREATE: 群聊 @ 消息
        if msg_type in ("C2C_MESSAGE_CREATE", "AT_MESSAGE_CREATE"):
            msg_data = data.get("d", {})
            msg_id = msg_data.get("id", "")
            content = msg_data.get("content", "").strip()

            if content:
                # 去掉 @机器人 的前缀（群聊场景）
                if msg_type == "AT_MESSAGE_CREATE" and " " in content:
                    parts = content.split(" ", 1)
                    content = parts[1] if len(parts) > 1 else content

                # 调用小克
                reply = call_xiaoke(content)
                return send_qq_message(msg_id, reply)

    return jsonify({"code": 0, "msg": "ok"})


# ============================================================
# 核心对话 API
# ============================================================
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data["message"].strip()

    # 1. 获取长期记忆
    memories = get_all_memories()
    memory_text = ""
    if memories:
        memory_text = "【关于用户的长期记忆】\n" + "\n".join(f"- {m}" for m in memories)

    # 2. 智能获取上下文（最近14条 + 关键词匹配6条）
    history = build_context(user_message, recent_count=14, search_count=6)

    # 3. 构建消息
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if memory_text:
        messages.append({"role": "system", "content": memory_text})

    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})

    messages.append({"role": "user", "content": user_message})

    # 4. 调用 DeepSeek
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.8,
        max_tokens=2000
    )

    reply = response.choices[0].message.content

    # 5. 自动检测 "[已记住：" 标记，存入长期记忆
    import re
    remembered = re.findall(r'\[已记住：(.*?)\]', reply)
    for item in remembered:
        save_memory(item.strip(), source="auto")

    # 6. 保存对话
    save_conversation("user", user_message)
    save_conversation("assistant", reply)

    return jsonify({"reply": reply})


# ============================================================
# 自动学习 - AI 总结用户偏好
# ============================================================
@app.route("/learn", methods=["POST"])
def learn():
    """让 AI 总结最近的对话，提炼用户偏好"""
    conn = sqlite3.connect(os.path.join(BASE_DIR, "data.db"))
    recent = conn.execute(
        "SELECT role, content FROM conversations ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()

    if len(recent) < 6:
        return jsonify({"ok": False, "reason": "对话还不多呢，再聊一会儿吧~"})

    history_text = "\n".join(f"{r[0]}: {r[1]}" for r in reversed(recent))

    messages = [
        {"role": "system", "content": """你是用户画像分析师。回顾以下对话，提炼关于用户的信息。
用中文列出，每条一行，格式为 "- 用户xxx" 或 "- 用户喜欢xxx" 或 "- 用户在xxx"。
只记录确定的事实，不推测。最多列出10条。"""},
        {"role": "user", "content": f"请总结以下对话中关于用户的信息：\n\n{history_text}"}
    ]

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.3,
        max_tokens=600
    )

    summary = response.choices[0].message.content

    # 存入长期记忆
    count = 0
    for line in summary.split("\n"):
        line = line.strip().lstrip("- ").strip()
        if line and len(line) > 4:
            save_memory(line, source="auto")
            count += 1

    return jsonify({"ok": True, "summary": summary, "saved": count})


# ============================================================
# 文章 / 知识学习
# ============================================================
@app.route("/learn-article", methods=["POST"])
def learn_article():
    """学习用户提供的文章或知识"""
    data = request.json
    content = data.get("content", "").strip()

    if not content:
        return jsonify({"ok": False, "reason": "内容为空"})

    # 短内容直接存
    if len(content) < 200:
        save_memory(content, source="manual")
        return jsonify({"ok": True, "result": "已记住这条信息"})

    # 长内容让 AI 提炼
    messages = [
        {"role": "system", "content": "你是知识提炼助手。阅读内容，提炼 3-8 条核心要点。每条一行，格式 '- 要点'。只记录事实。"},
        {"role": "user", "content": f"提炼要点：\n\n{content}"}
    ]

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.3,
        max_tokens=500
    )

    points = response.choices[0].message.content

    count = 0
    for line in points.split("\n"):
        line = line.strip().lstrip("- ").strip()
        if line and len(line) > 3:
            save_memory(line, source="manual")
            count += 1

    return jsonify({"ok": True, "result": points, "saved": count})


# ============================================================
# 记忆管理 API
# ============================================================
@app.route("/memories", methods=["GET"])
def list_memories():
    """查看所有长期记忆"""
    memories = get_all_memories()
    return jsonify({"memories": memories, "count": len(memories)})


@app.route("/memories/clear", methods=["POST"])
def clear_memories():
    """清空长期记忆"""
    conn = sqlite3.connect(os.path.join(BASE_DIR, "data.db"))
    conn.execute("DELETE FROM memories")
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "记忆已清空"})


@app.route("/conversations/count", methods=["GET"])
def conversation_count():
    """获取对话轮数"""
    conn = sqlite3.connect(os.path.join(BASE_DIR, "data.db"))
    count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    conn.close()
    return jsonify({"count": count})


# ============================================================
# 网页聊天界面
# ============================================================
@app.route("/")
def home():
    return render_template_string(HTML)

HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>小克 - 私人助手</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
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
.header h2{font-size: 18px;color:#333}
.header .actions{
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.header .actions button{
  padding: 6px 12px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #666;
  white-space: nowrap;
}
.header .actions button:hover{background:#f5f5f5}
#chat{
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.msg{
  max-width: 82%;
  padding: 10px 16px;
  border-radius: 12px;
  line-height: 1.6;
  font-size: 15px;
  word-break: break-word;
}
.msg.user{align-self:flex-end;background:#1677ff;color:#fff;border-bottom-right-radius:4px}
.msg.assistant{align-self:flex-start;background:#f5f5f5;color:#333;border-bottom-left-radius:4px}
.msg.system{
  align-self:center;
  background:#fff8e1;
  color:#8d6e00;
  font-size:13px;
  padding:8px 14px;
  border-radius:8px;
  max-width:90%;
  white-space: pre-wrap;
}
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
.typing{
  display:flex;align-items:center;gap:6px;
  padding:10px 16px;align-self:flex-start
}
.typing span{
  width:8px;height:8px;background:#bbb;
  border-radius:50%;animation:dot 1.4s infinite
}
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
      <button onclick="doLearn()" title="让AI总结最近的对话">🧠 学习</button>
      <button onclick="showMemories()">📋 记忆</button>
      <button onclick="clearMemories()" style="color:#e74c3c">🗑 清空</button>
    </div>
  </div>
  <div id="chat">
    <div class="msg assistant">你好！我是小克，你的私人助手。今天想聊什么？</div>
  </div>
  <div class="input-area">
    <textarea id="input" rows="1" placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send()}"></textarea>
    <button onclick="send()" id="sendBtn">发送</button>
  </div>
</div>
<script>
const chat = document.getElementById("chat");
const input = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
let msgCount = 0;
const LEARN_INTERVAL = 15;

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
  if(sendBtn.disabled) return;

  addMsg("user", text);
  input.value = "";
  sendBtn.disabled = true;
  showTyping();

  try{
    const res = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text})
    });
    const data = await res.json();
    hideTyping();
    sendBtn.disabled = false;
    addMsg("assistant", data.reply);

    msgCount++;
    if(msgCount % LEARN_INTERVAL === 0){
      setTimeout(() => {
        addMsg("system", "💡 已经聊了 " + msgCount + " 轮了。点🧠学习让小克总结你的偏好吧~");
      }, 1500);
    }
  }catch(e){
    hideTyping();
    sendBtn.disabled = false;
    addMsg("system", "❌ 出错了：" + e.message + "\n请确认已替换 API Key 并重启程序");
  }
}

async function doLearn(){
  addMsg("system", "🧠 小克正在回顾对话，提炼你的偏好...");
  try{
    const res = await fetch("/learn", {method:"POST"});
    const data = await res.json();
    if(data.ok){
      addMsg("system", "✅ 学到了这些：" + (data.saved > 0 ? "(已存" + data.saved + "条)\n" + data.summary : data.summary));
    }else{
      addMsg("system", data.reason || "学习失败");
    }
  }catch(e){
    addMsg("system", "❌ 学习出错：" + e.message);
  }
}

async function showMemories(){
  try{
    const res = await fetch("/memories");
    const data = await res.json();
    if(data.count === 0){
      addMsg("system", "📋 还没有长期记忆。多聊天，或点🧠学习来建立记忆");
    }else{
      addMsg("system", "📋 小克记住的（共" + data.count + "条）：\n" +
        data.memories.map((m,i) => (i+1) + ". " + m).join("\n"));
    }
  }catch(e){
    addMsg("system", "❌ 获取记忆出错：" + e.message);
  }
}

async function clearMemories(){
  if(!confirm("确定要清空所有记忆吗？此操作不可撤销。")) return;
  try{
    await fetch("/memories/clear", {method:"POST"});
    addMsg("system", "🗑 记忆已清空");
  }catch(e){
    addMsg("system", "❌ 清空失败：" + e.message);
  }
}

input.focus();
</script>
</body>
</html>
"""

# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    import sys
    import os
    sys.stdout.reconfigure(encoding='utf-8')
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  [XiaoKe] 小克已启动！")
    print(f"  端口: {port}")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=port)
