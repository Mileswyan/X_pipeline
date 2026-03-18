import os
import json
import argparse

def clean_json_text(text):
    """清理大模型可能返回的 Markdown 代码块标记"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def parse_summarizing_responses(response_path):
    """解析 Batch 任务返回的 response 文件，按 idx 聚合总结内容"""
    summaries_by_idx = {}
    
    if not os.path.exists(response_path):
        print(f"Error: 找不到响应结果文件 {response_path}")
        return summaries_by_idx

    with open(response_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            try:
                data = json.loads(line)
                
                # 跳过报错的请求
                if "error" in data:
                    continue
                
                req_id = data.get("id", "")
                # 假设 ID 格式为: {KOL}-{idx}-summary-{chunk_idx}，例如 goldseek-728-summary-0
                # 我们通过 "-" 分割，倒数第三个就是 idx
                id_parts = req_id.split('-')
                if len(id_parts) >= 3:
                    idx = int(id_parts[-3])
                else:
                    continue
                
                # 提取模型生成的文本
                response_text = data['response']['candidates'][0]['content']['parts'][0]['text']
                cleaned_text = clean_json_text(response_text)
                parsed_content = json.loads(cleaned_text)
                
                items = parsed_content.get("items", [])
                
                # 累加到对应的 idx 列表中 (处理同一个 idx 存在多个 chunk 的情况)
                if idx not in summaries_by_idx:
                    summaries_by_idx[idx] = []
                summaries_by_idx[idx].extend(items)
                
            except (KeyError, json.JSONDecodeError, ValueError) as e:
                print(f"警告: 解析失败，跳过该行 (ID: {data.get('id', 'Unknown')})。错误信息: {e}")
                continue
                
    print(f"✅ 成功解析了 {len(summaries_by_idx)} 条原始记录的总结数据。")
    return summaries_by_idx

def main():
    parser = argparse.ArgumentParser(description="Merge Gemini Batch Responses with Original Data")
    parser.add_argument("--original", "-i", required=True, help="原始数据文件路径 (如 daily/original_goldseek.jsonl)")
    parser.add_argument("--response", "-r", required=True, help="Batch 返回的结果文件路径 (如 requests/goldseek/summarizing_response.jsonl)")
    parser.add_argument("--output", "-o", default="final_output.jsonl", help="最终合并输出的文件路径")
    args = parser.parse_args()

    if not os.path.exists(args.original):
        print(f"Error: 找不到原始文件 {args.original}")
        return

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir): 
        os.makedirs(output_dir)

    print(f"开始数据拼装: {args.original} + {args.response} -> {args.output}")

    # 1. 预先解析并聚合所有的 summarizer 结果
    summaries_dict = parse_summarizing_responses(args.response)

    # 2. 遍历原始数据并生成最终格式
    processed_count = 0
    with open(args.original, 'r', encoding='utf-8') as f_in, \
         open(args.output, 'w', encoding='utf-8') as f_out:
        
        for idx, line in enumerate(f_in):
            if not line.strip(): continue
            
            try:
                X = json.loads(line)
                
                # 只有当该条目有对应的总结数据时，我们才写入（或者你也可以选择全部写入，没有总结的为空）
                if idx in summaries_dict:
                    # 为了高度还原 pipeline.py，你可以选择在这里去读取 filtering 的返回结果。
                    # 如果不需要严格保留 filtering 的具体 T/F 数组，可以直接传空列表或根据 tweet 数量伪造一个全 True 的数组
                    tweets = X.get("tweets", [])
                    mock_filtering = [True] * len(tweets) 
                    
                    result = {
                        "idx": idx,
                        "schema": X.get("schema", ""),
                        "kol": X.get('kol_username', ""),
                        "tweet_ids": X.get("tweet_ids", []),
                        "trading_day": X.get("trading_day", ""),
                        "tweets": tweets,
                        "data": {
                            "summaries": summaries_dict[idx],
                            "filtering": mock_filtering # 如果你有 filtering_response.jsonl，也可以加个函数解析进来替换这里
                        },
                    }
                    f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                    processed_count += 1
                    
            except json.JSONDecodeError as e:
                print(f"Error: 原始数据 Row {idx} JSON 解析失败: {e}")
                continue

    print(f"🎉 拼装完成！共成功输出 {processed_count} 条完整数据至 {args.output}")

if __name__ == "__main__":
    main()