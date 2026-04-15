
# Dify Installation & Configuration Guide

## 1. Install Dify

```bash
git clone https://github.com/langgenius/dify.git
```

---

## 2. Configure Environment Variables

```bash
cd dify/docker
cp .env.example .env
```

Update the following fields in `.env`:

* `SERVER_WORKER_AMOUNT = (CPU cores * 2 + 1)`

---

## 3. Start Services

```bash
docker compose up -d
```

---

## 4. Create Admin Account

Open: [http://localhost/install](http://localhost/install)
Register an administrator account.

---

## 5. Configure Gemini API

1. Navigate to **Account → Settings → Model Providers**
2. Select **Gemini**
3. Add your Gemini API key
4. Install the required model plugins

---

## 6. Import DSL Workflows

* **X Filtering** — tweet filtering
* **X Summarizer** — tweet summarization

---

## 7. Final Setup

### 7.1 Publish Workflow

* Go to **Orchestration → Publish**
* Resolve any validation errors if publishing fails

### 7.2 Create API Keys

* Navigate to **API Keys**
* Generate keys for both workflows

---

## 8. Update `pipeline.py`

Replace the following variables with your API keys:

* `API_filter`
* `API_summarizer`

Run:

```bash
python pipeline.py -i daily/original_bespokeinvest.jsonl -o results/bespokeinvest/2.jsonl -s 201 -e 400
```

**Arguments:**

* `-i` Input file path
* `-o` Output file path
* `-s` Start index
* `-e` End index

You can run multiple instances in parallel.

---

# BatchSubmit Usage Guide

## 📦 Batch Tweet Processing Pipeline

A pipeline powered by **Gemini Batch API** for processing Twitter (X) data:

* ✅ Filtering
* ✅ Chunked summarization
* 🔁 Automatic retry

---

## 🚀 Overview

```
Raw Data → Filtering → Summarizing → Retry → Final Output
```

### Key Features

* Batch processing (Batch API)
* Multimodal support (text + images)
* Automatic error detection and retry
* Scalable for large datasets

---

## 📂 Project Structure

```
.
├── batchSubmit.py
├── daily/
│   └── original_xxx.jsonl
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

## ⚙️ Setup

### 1. Install Dependencies

```bash
pip install google-genai pydantic
```

### 2. Configure API Key

In `batchSubmit.py`:

```python
GEMINI_API_KEY = "YOUR_API_KEY"
```

---

## 📥 Input Format

Each line is a JSON object:

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

## 🧠 Workflow

### 1. Filtering

* Input: tweets
* Output: valid tweet flags

Output file:

```
filtering_response.jsonl
```

---

### 2. Summarizing

* Processes only valid tweets
* Automatically chunks data (max 5 images per chunk)

Output file:

```
summarizing_response.jsonl
```

---

### 3. Retry Mechanism

| Error Count | Strategy     |
| ----------- | ------------ |
| ≤ 50        | Single retry |
| > 50        | Batch retry  |

---

## ▶️ Usage

### Command

```bash
python batchSubmit.py <KOL> <start> <end> <mode> <download>
```

---

### Parameters

| Parameter  | Description                     |
| ---------- | ------------------------------- |
| `KOL`      | Data identifier (e.g. username) |
| `start`    | Start index                     |
| `end`      | End index                       |
| `mode`     | Execution mode                  |
| `download` | Manual task selection flag      |

---

### Modes

| Mode | Description                    |
| ---- | ------------------------------ |
| 0    | 🚀 Full pipeline (recommended) |
| 1    | 👀 Monitor filtering           |
| 2    | 👀 Monitor summarizing         |
| 3    | 🔁 Auto retry                  |
| 4    | 🔨 Force single retry          |

---

### Examples

**Full run:**

```bash
python batchSubmit.py musk 0 1000 0 0
```

**Monitor only:**

```bash
python batchSubmit.py musk 0 1000 1 1
```

**Force retry:**

```bash
python batchSubmit.py musk 0 1000 4 0
```

---

## ⚠️ Notes

1. Input file must exist:

```
daily/original_<KOL>.jsonl
```

2. Filtering and summarizing results must align, otherwise errors may occur:

* `dimension_mismatch`
* `unmatched_validation_data`

3. Image limit:

* Max 5 images per request

4. Batch API latency:

* Jobs may take several minutes

5. Error logs:

```
filtering_error.jsonl
```

