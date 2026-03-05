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


