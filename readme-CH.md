# Dify 安装和配置指南

## 1. 安装 Dify

```shell
git clone https://github.com/langgenius/dify.git
````

## 2. 配置 `.env` 文件

```shell
cd dify
cd docker
cp .env.example .env
```

修改 `.env` 文件中的以下配置：

* `SERVER_WORKER_AMOUNT = # number of CPU cores * 2 + 1`
* `SERVER_WORKER_CLASS = sync`
* `CELERY_WORKER_CLASS = sync`

## 3. 启动 Docker

```shell
docker compose up -d
```

## 4. 注册管理员账号

打开 [http://localhost/install](http://localhost/install) 注册管理员账号。

## 5. 配置 Gemini 密钥

1. 进入 `账户 - 设置 - 模型供应商`。
2. 选择 `Gemini`，并绑定 Gemini API 密钥。

安装好对应的模型插件。

## 6. 导入 DSL 文件

* **X filtering** - 过滤推文
* **X Summarizer** - 提取推文

## 7. 完成项目导入后，依次执行以下流程：

### 1. 编排 - 发布

* 如果发布不成功，请解决所有对应的问题。

### 2. 访问 API - 创建 API 密钥

* 进入 `API密钥` 页面，创建新的密钥。

## 8. 修改 `pipeline.py`

* 替换变量为（第 6 步）中创建的密钥：

  * `API_filter`
  * `API_summarizer`

运行命令：

```shell
python pipeline.py -i daily/original_bespokeinvest.jsonl -o results/bespokeinvest/2.jsonl -s 201 -e 400
```

其中：

* `-i` 文件输入路径
* `-o` 文件输出路径
* `-s` 起始索引
* `-e` 终止索引

你可以启动多个终端进行并发访问。




# BatchSubmit使用指南


## 📦 Batch Tweet Processing Pipeline

一个基于 **Gemini Batch API** 的数据处理流水线，用于对 Twitter（X）数据进行：

* ✅ 内容过滤（Filtering）
* ✅ 分块总结（Summarizing）
* 🔁 自动错误重试（Retry）

---

## 🚀 功能概览

```text
原始数据 → Filtering → Summarizing → Retry修复 → 最终结果
```

### 核心能力：

* 批量请求（Batch API）
* 图片 + 文本多模态处理
* 自动错误检测与重试
* 大规模数据处理支持

---

# 📂 项目结构

```text
.
├── batchSubmit.py              # 主程序
├── daily/
│   └── original_xxx.jsonl      # 原始数据
├── requests/
│   └── xxx/
│       ├── filter_request.jsonl
│       ├── filtering_response.jsonl
│       ├── summarizing_request.jsonl
│       ├── summarizing_response.jsonl
│       ├── summarizing_retry_request.jsonl
│       └── summarizing_retry_response.jsonl
```

---

## ⚙️ 环境准备

### 1️⃣ 安装依赖

```bash
pip install google-genai pydantic
```

### 2️⃣ 配置 API Key

在 `batchSubmit.py` 中填写：

```python
GEMINI_API_KEY = "你的API_KEY"
```

---

## 📥 输入数据格式

每行 JSON（jsonl）示例：

```json
{
  "tweets": [
    {
      "text": "example tweet",
      "media": [
        {"url": "...", "type": "image"}
      ]
    }
  ],
  "texts": ["tweet1", "tweet2"]
}
```

---

## 🧠 工作流程

### 1️⃣ Filtering（筛选）

* 输入：tweets
* 输出：有效 tweet 标记

👉 文件：

```
filtering_response.jsonl
```

---

### 2️⃣ Summarizing（总结）

* 仅处理有效 tweet
* 自动分块（最多 5 张图片 / chunk）

👉 文件：

```
summarizing_response.jsonl
```

---

### 3️⃣ Retry（错误修复）

自动执行：

| 错误数  | 处理方式 |
| ---- | ---- |
| ≤ 50 | 单条重试 |
| > 50 | 批量重试 |

---

## ▶️ 使用方法

### 命令格式

```bash
python batchSubmit.py <KOL> <start> <end> <mode> <download>
```

---

### 参数说明

| 参数         | 说明         |
| ---------- | ---------- |
| `KOL`      | 数据标识（用户名等） |
| `start`    | 起始行        |
| `end`      | 结束行        |
| `mode`     | 执行模式       |
| `download` | 是否手动选择任务   |

---

### 🧩 mode 模式

| mode | 功能                |
| ---- | ----------------- |
| 0    | 🚀 全流程执行（推荐）      |
| 1    | 👀 监控 filtering   |
| 2    | 👀 监控 summarizing |
| 3    | 🔁 自动 retry       |
| 4    | 🔨 强制单条 retry     |

---

### 🎯 示例

#### ✅ 全流程运行

```bash
python batchSubmit.py musk 0 1000 0 0
```

---

#### ✅ 仅监控任务

```bash
python batchSubmit.py musk 0 1000 1 1
```

---

#### ✅ 强制修复错误

```bash
python batchSubmit.py musk 0 1000 4 0
```

---

## ⚠️ 注意事项

### 1. 输入文件必须存在

```
daily/original_<KOL>.jsonl
```

---

### 2. Filtering 与 Summarizing 必须匹配

否则会产生：

* `dimension_mismatch`
* `unmatched_validation_data`

---

### 3. 图片限制

* 每个请求最多 5 张图片

---

### 4. Batch API 有延迟

* 任务执行可能需要几分钟

---

### 5. 错误日志位置

```
filtering_error.jsonl
```




