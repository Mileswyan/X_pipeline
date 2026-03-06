import os
import json
import requests
import time
import sys
import argparse

URL = "http://localhost/v1/workflows/run"
API_filter = "app-WT2G8qiOoaAWoPGJpu7Ja9OU"
API_summarizer = "app-PyJG68gbM8ZNFYSLktsBEgnu"
MAX_RETRIES = 3
RETRY_DELAY = 2

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
    inputs = {
        "tweets": "".join([f"""<DAY_TWEET_SEP> {t['text']} </DAY_TWEET_SEP>""" for t in tweets])
    }    
    # --- 针对 Filtering 逻辑不匹配的重试循环 ---
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"Filtering Logic Check (Attempt {attempt}/{MAX_RETRIES})...")
        
        # 调用基础请求函数（内部已有 3 次 HTTP/Business 重试）
        result = dify_request(API_KEY=API_filter, inputs=inputs)
        valid_tweets = result.get('data', {}).get('outputs', {}).get('valid_tweet', [])

        # 核心校验：长度匹配
        if len(tweets) == len(valid_tweets):
            print(f"Success: Received {len(valid_tweets)} validation flags.")
            print("=========== END Filtering ===============")
            return {"status": True, "data": valid_tweets}
        else:
            print(f"Logic Mismatch: Input {len(tweets)} != Output {len(valid_tweets)}")
            
            if attempt < MAX_RETRIES:
                print(f"Retrying Filtering logic in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print("!!! Critical: Filtering length mismatch after max retries. Exiting. !!!")
                sys.exit(1)

def concatenating(tweets, validation):
    chunks = []
    current_text, current_media = [], []

    for tweet, is_valid in zip(tweets, validation):
        if not is_valid: continue
        
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