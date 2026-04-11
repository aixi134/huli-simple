# 你的职责

你是一个高级全栈工程师，擅长 Python、FastAPI、React、SQLite、数据解析。  
  
你的任务是帮我从0实现一个“刷题系统”，包括：  
1. PDF解析  （pdf目录是目前的所有的文件后面可能会添加）
2. 题库结构化  
3. 数据库存储  
4. 后端API  
5. 前端刷题页面  
6. AI讲题功能  
  
要求：  
- 忽略权限/登录
- 所有代码必须可运行  
- 不允许省略关键逻辑  
- 每一步都要给完整代码  
- 优先简单可用，再逐步优化  
  
输出要求：  
- 只输出代码或必要说明  
- 不要长篇解释
补充：
如果使用python脚本无法有效获取题目。本地127.0.0.1:8888启动了一个openai格式的多模态LLM

---

# 🧩 第一阶段：PDF → 题库JSON

---

## ✅ Prompt 1：PDF解析脚本（完整版）

写一个完整Python脚本，实现：  
  
功能：  
从PDF中提取所有页面文本，并保留页码  
  
要求：  
1. 使用 pymupdf（fitz）  
2. 输入：PDF路径  
3. 输出格式：  
[  
  {"page": 1, "text": "..."},  
  {"page": 2, "text": "..."}  
]  
  
4. 提供 main() 可直接运行  
5. 打印前2页示例  
  
输出完整代码

---

## ✅ Prompt 2：提取题目区块

写一个函数：  
  
extract_question_section(pages)  
  
功能：  
从PDF页面中提取题目部分  
  
规则：  
- 从 “一、A1/A2 型选择题” 开始  
- 到 “参考答案及解析” 结束  
  
输入：  
pages = [{"page":1,"text":"..."},...]  
  
输出：  
拼接后的题目文本字符串  
  
要求：  
- 处理跨页  
- 不丢内容

---

## ✅ Prompt 3：切分题目

写函数：  
  
split_questions(text)  
  
功能：  
把题目文本切分成单题  
  
规则：  
- 每题以 “数字+.” 开头  
- 支持换行题干  
  
输出：  
[  
  {  
    "number": 1,  
    "raw_text": "完整题目"  
  }  
]  
  
要求：  
- 使用正则  
- 保证题号连续

---

## ✅ Prompt 4：解析选项

写函数：  
  
parse_question(raw_text)  
  
功能：  
解析单题为结构化数据  
  
输出：  
{  
  "number": 1,  
  "stem": "...",  
  "options": {  
    "A": "...",  
    "B": "...",  
    "C": "...",  
    "D": "...",  
    "E": "..."  
  }  
}  
  
要求：  
- 正确分离题干和选项  
- 兼容换行

---

## ✅ Prompt 5：解析答案页

写函数：  
  
parse_answers(text)  
  
功能：  
解析“参考答案及解析”  
  
规则：  
识别：  
1.B 解析：xxxx  
  
输出：  
{  
  "1": {  
    "answer": "B",  
    "explanation": "xxxx"  
  }  
}

---

## ✅ Prompt 6：合并数据

写函数：  
  
merge_questions_answers(questions, answers)  
  
输出：  
[  
  {  
    "number": 1,  
    "stem": "...",  
    "options": {...},  
    "answer": "B",  
    "explanation": "..."  
  }  
]

---

## ✅ Prompt 7：整合为完整脚本

把前面所有函数整合成一个完整脚本：  
  
功能：  
PDF → 结构化JSON题库  
  
要求：  
1. 输入PDF路径  
2. 输出 JSON 文件  
3. 自动完成：  
   - 提取文本  
   - 切题  
   - 解析选项  
   - 解析答案  
   - 合并  
  
输出完整代码

---

# 🗄️ 第二阶段：数据库

---

## ✅ Prompt 8：SQLite设计

写SQLite数据库设计：  
  
表：  
questions  
options  
  
要求：  
- questions：id, stem, answer, explanation  
- options：question_id, label, content  
  
输出：  
1. SQL语句  
2. SQLAlchemy模型

---

## ✅ Prompt 9：导入脚本

写Python脚本：  
  
功能：  
把JSON题库导入SQLite  
  
要求：  
- 自动生成UUID  
- 插入options表  
- 避免重复

---

# ⚙️ 第三阶段：后端API

---

## ✅ Prompt 10：FastAPI服务

写FastAPI应用：  
  
接口：  
  
GET /question/random  
返回一道题（不含答案）  
  
POST /answer  
输入：  
{  
  "question_id": "...",  
  "answer": "A"  
}  
  
返回：  
{  
  "correct": true/false,  
  "answer": "B",  
  "explanation": "..."  
}  
  
要求：  
- 使用SQLite  
- 可直接运行

---

# 💻 第四阶段：前端

---

## ✅ Prompt 11：React刷题页面

写一个React组件：  
  
功能：  
- 获取题目  
- 显示选项  
- 点击作答  
- 显示结果  
- 下一题  
  
要求：  
- 使用 fetch 调API  
- 简洁UI

---

# 🤖 第五阶段：接入Gemma（重点）

---

## ✅ Prompt 12：AI讲题

写Python函数：  
  
explain_with_gemma(question, options, answer, explanation)  
  
功能：  
调用本地Gemma模型生成讲解  
  
Prompt：  
“请用通俗方式解释这道护理题，并说明每个选项对错”  
  
输出：  
字符串讲解

---

## ✅ Prompt 13：解析失败兜底

写函数：  
  
extract_with_gemma(page_text)  
  
功能：  
当解析失败时调用Gemma提取题目  
  
输出格式：  
{  
  "number": ...,  
  "stem": "...",  
  "options": {...},  
  "answer": "...",  
  "explanation": "..."  
}  
  
要求：  
- 强制JSON输出

---

# 🔥 终极加速 Prompt（批量处理）

最后你可以用这个让 Claude 帮你优化整套系统：

我现在有很多类似结构的考试PDF。  
  
请帮我优化：  
1. 批量处理多个PDF  
2. 自动识别不同题型（A1/B1）  
3. 失败题目自动进入Gemma处理  
4. 输出统一JSON格式  
5. 支持断点续跑  
  
请给完整工程代码结构