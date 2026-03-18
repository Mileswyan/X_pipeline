import os
import json
import requests
import time
import sys
import argparse

URL = "http://localhost/v1/workflows/run"
API_filter = "app-nOSyxQnoSPMyH6zxO3Gdpu4g"
API_summarizer = "app-dFS5lmMqVfosD4Wp5kAYc0vv"
MAX_RETRIES = 6
RETRY_DELAY = 120

def dify_request(API_KEY, inputs, user="test_user"):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": inputs,
        "response_mode": "blocking",
        "user": user
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Executing request (Attempt {attempt}/{MAX_RETRIES})...")
            response = requests.post(URL, headers=headers, json=payload, timeout=120)
            
            if response.status_code == 200:
                res_json = response.json()
                data = res_json.get('data', {})
                
                # 打印统计信息
                print(f"Stats -> Elapsed: {data.get('elapsed_time', 'N/A')}s, Tokens: {data.get('total_tokens', 'N/A')}")
                
                status = data.get('status')
                if status == "succeeded":
                    return res_json
                else:
                    error_info = data.get('error', 'No error detail')
                    print(f"Business Alert: Status is '{status}'. Error: {error_info}")
            else:
                print(f"HTTP Error: {response.status_code} - {response.text}")

        except (requests.exceptions.RequestException, Exception) as e:
            print(f"Network/System Exception: {str(e)}")

        if attempt < MAX_RETRIES:
            print(f"Waiting {RETRY_DELAY}s before next attempt...")
            time.sleep(RETRY_DELAY)
        else:
            print("!!! Critical: Request failed after max retries. Exiting. !!!")
            sys.exit(1)

def filtering(tweets):
    print("=========== Filtering ===============")
    
    # 定义内部递归处理函数
    def process_batch(batch, attempt=1):
        # 边界条件处理
        if not batch:
            return []
            
        inputs = {"tweets": "".join([f"""<DAY_TWEET_SEP> {t['text']} </DAY_TWEET_SEP>""" for t in batch])}
        
        print(f"Filtering Logic Check (Attempt {attempt}, Batch Size: {len(batch)})...")
        
        # 调用基础请求函数
        result = dify_request(API_KEY=API_filter, inputs=inputs)
        valid_tweets = result.get('data', {}).get('outputs', {}).get('valid_tweet', [])

        # 核心校验：长度匹配
        if len(batch) == len(valid_tweets):
            print(f"Success: Received {len(valid_tweets)} validation flags for this batch.")
            return valid_tweets
        else:
            print(f"Logic Mismatch: Input {len(batch)} != Output {len(valid_tweets)}")
            
            # --- 核心改动：如果维度不一致，且列表长度 > 1，则对半切分 ---
            if len(batch) > 1:
                print(f"Splitting batch of {len(batch)} into two halves and retrying...")
                mid = len(batch) // 2
                left_batch = batch[:mid]
                right_batch = batch[mid:]
                
                # 短暂延迟避免触发并发限制
                time.sleep(RETRY_DELAY) 
                
                # 分开两次进行筛选（针对新批次重置 attempt 为 1），再将结果合并
                left_result = process_batch(left_batch, 1)
                right_result = process_batch(right_batch, 1)
                
                return left_result + right_result
                
            # --- 如果列表只有 1 个元素仍出错（无法再切分），则执行重试或退出 ---
            else:
                if attempt < MAX_RETRIES:
                    print(f"Retrying single item in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    return process_batch(batch, attempt + 1)
                else:
                    print("!!! Critical: Filtering length mismatch after max retries on single item. Exiting. !!!")
                    sys.exit(1)

    # 触发首次全量处理
    final_valid_tweets = process_batch(tweets)
    
    # 确保合并后的总长度与初始输入完全一致
    if len(final_valid_tweets) == len(tweets):
        print(f"Total Success: Processed and merged all {len(tweets)} items.")
        print("=========== END Filtering ===============")
        return {"status": True, "data": final_valid_tweets}
    else:
        # 理论上递归逻辑会保证要么等长返回，要么 sys.exit(1)，这里作为最终安全兜底
        print(f"!!! Critical: Final merge mismatch. Expected {len(tweets)}, got {len(final_valid_tweets)}. Exiting. !!!")
        sys.exit(1)

def concatenating(tweets, validation):
    chunks = []
    current_text, current_media = [], []

    for tweet, is_valid in zip(tweets, validation):
        is_valid_str = str(is_valid).strip().lower()
        if is_valid_str in ['false', '0', 'no', 'none', ''] or not is_valid:
            continue
        
        media_items = tweet.get("media", [])
        formatted_media = [
            {"transfer_method": "remote_url", "url": item.get("url"), "type": "image"}
            for item in media_items if item.get("kind") == "image"
        ][:5]

        if len(current_media) + len(formatted_media) > 5 and current_media:
            chunks.append({"text": " ".join(current_text), "media": current_media})
            current_text, current_media = [], []

        current_text.append(tweet.get("text", ""))
        current_media.extend(formatted_media)

    if current_text or current_media:
        chunks.append({"text": " ".join(current_text), "media": current_media})

    print(f"The size of chunks = {len(chunks)}")
    return chunks

def summarizing(twitter_text, twitter_media):
    print("=========== Summarizing ===============")
    inputs = {"twitter_text": twitter_text, "twitter_media": twitter_media}
    result = dify_request(API_KEY=API_summarizer, inputs=inputs)
    summary_data = result.get('data', {}).get('outputs', {}).get('summary', {})    
    print("=========== End Summarizing ===============")
    return {"status": True, "data": summary_data}

def X_sentiment_analysis(tweets):
    # 1. 过滤模块（含逻辑重试）
    filter_res = filtering(tweets=tweets)
    
    # 2. 分段模块
    data_chunks = concatenating(tweets=tweets, validation=filter_res['data'])
    
    if not data_chunks:
        return {"status": True, "data": {"summaries": [], "filtering": filter_res['data']}}

    # 3. 汇总模块
    all_summaries = []
    for chunk in data_chunks:
        if chunk["text"] or chunk["media"]:
            summary_res = summarizing(twitter_text=chunk["text"], twitter_media=chunk["media"])
            all_summaries.extend(summary_res["data"].get("items", []))

    return {"status": True, "data": {"summaries": all_summaries, "filtering": filter_res['data']}}

def main():
    parser = argparse.ArgumentParser(description="Twitter Data Processing Tool")
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", default="output.jsonl")
    parser.add_argument("--start", "-s", type=int, default=0)
    parser.add_argument("--end", "-e", type=int, default=999999)
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found."); sys.exit(1)

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir): os.makedirs(output_dir)

    print(f"Starting process: {args.input} -> {args.output}")

    with open(args.input, 'r', encoding='utf-8') as f_in, \
         open(args.output, 'a', encoding='utf-8') as f_out:
        
        for idx, line in enumerate(f_in):
            if idx < args.start: continue
            if idx > args.end: break
            if not line.strip(): continue
                
            try:
                print(f"\n[Row {idx}] Processing...")
                X = json.loads(line)
                summary_res = X_sentiment_analysis(X.get("tweets", []))
                
                result = {
                    "idx": idx,
                    "schema": X.get("schema", ""),
                    "kol": X.get('kol_username', ""),
                    "tweet_ids": X.get("tweet_ids", []),
                    "trading_day": X.get("trading_day", ""),
                    "tweets": X.get("tweets", []),
                    "data": summary_res['data'],
                }
                f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                f_out.flush() 
                
                # 避免触发频率限制
                time.sleep(60) 
            except Exception as e:
                print(f"Error: Row {idx} unexpected error: {e}")
                continue

if __name__ == "__main__":
    main()