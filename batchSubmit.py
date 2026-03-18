from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import json
import os
import sys
import time
from prepared_prompts import filtering, filtering_schema, summarizing, summarizing_schema
import mimetypes

GEMINI_API_KEY = ""


def get_mime_type(uri):
    mime_type, _ = mimetypes.guess_type(uri)
    return mime_type or "image/jpeg"

def generate_request(system_prompt, user_prompt, output_schema, image_list):
    user_parts = [{"text": user_prompt}]

    # 修复：将下划线命名改为 Gemini API 要求的驼峰命名
    if image_list:
        for image_uri in image_list:
            user_parts.append({
                "fileData": { 
                    "mimeType": get_mime_type(image_uri), 
                    "fileUri": image_uri 
                }
            })

    return {
        "systemInstruction": {
            "parts": [
                {"text": system_prompt}
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": user_parts
            }
        ],
        "generationConfig": output_schema
    }

def monitoring(client, JOB_NAME, output_path):
    while True:
        # 1. 向服务器请求当前任务信息
        job_info = client.batches.get(name=JOB_NAME)
        
        # 兼容 SDK 版本差异：获取状态名称
        state = job_info.state.name if hasattr(job_info.state, 'name') else str(job_info.state)
        
        print(f"[{time.strftime('%H:%M:%S')}] 当前状态: {state}")
        
        # 2. 如果任务成功完成
        if state in ['JOB_STATE_SUCCEEDED', 'SUCCEEDED']:
            print("\n✅ 任务已成功完成！开始下载结果文件...")
            
            # 获取结果文件在 Google File API 里的引用名称
            result_file_name = job_info.dest.file_name
            
            # 使用 SDK 下载文件内容 (返回 bytes)
            file_content_bytes = client.files.download(file=result_file_name)
            file_content = file_content_bytes.decode('utf-8')
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(file_content)
                
            print(f"🎉 结果已保存至本地: {output_path}")
            break
            
        elif state in ['JOB_STATE_FAILED', 'FAILED', 'JOB_STATE_CANCELLED', 'CANCELLED']:
            print("\n❌ 任务未成功执行。")
            # 如果有明确的错误日志文件 URI，打印出来方便去排查
            if hasattr(job_info, 'error_uri') and job_info.error_uri:
                print(f"详细错误日志位置: {job_info.error_uri}")
            
            sys.exit(1)
            
        time.sleep(1200)

def submitTasks(client: genai.Client, model: str, display_name: str, input_path: str, output_path: str):
    uploaded_file = client.files.upload(
        file=input_path,
        config=types.UploadFileConfig(display_name=display_name, mime_type='jsonl')
    )

    file_batch_job = client.batches.create(
        model=model,
        src=uploaded_file.name,
        config={
            'display_name': display_name,
        },
    )

    JOB_NAME = file_batch_job.name
    print(JOB_NAME)
    monitoring(client, JOB_NAME, output_path)


def generate_filtering_requests(KOL, input_path, output_path, start, end):
    # 假设 filtering 和 filtering_schema 已在外部定义
    system_instruction = filtering
    structured_output = filtering_schema
    
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        sys.exit(1)

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir): 
        os.makedirs(output_dir)

    with open(input_path, 'r', encoding='utf-8') as f_in, \
         open(output_path, 'a', encoding='utf-8') as f_out:
        
        for idx, line in enumerate(f_in):
            if idx < start: continue
            if idx > end: break
            if not line.strip(): continue
        
            texts = json.loads(line).get('texts', [])
            user_prompt = "".join([f"<DAY_TWEET_SEP> {t} </DAY_TWEET_SEP>" for t in texts])
            
            result = {
                "id": f"{KOL}-{idx}-filter", 
                "request": generate_request(system_instruction, user_prompt, structured_output, None)
            }
            
            f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
            f_out.flush()



def generating_summarizer_requests(KOL, raw_path, validation_path, output_path, error_path, start, end):
    system_instruction = summarizing
    structured_output = summarizing_schema

    if not os.path.exists(validation_path):
        print(f"Error: Validation file not found: {validation_path}")
        sys.exit(1)

    validation_dict = {}
    with open(validation_path, 'r', encoding='utf-8') as f_val:
        for line in f_val:
            if not line.strip(): continue
            val_data = json.loads(line)
            req_id = val_data.get("id")
            
            try:
                response_text = val_data['response']['candidates'][0]['content']['parts'][0]['text']
                parsed_response = json.loads(response_text)
                validation_dict[req_id] = parsed_response.get("valid_tweet", [])
            except (KeyError, json.JSONDecodeError):
                # 遇到解析错误静默跳过，因为后续在数据匹配环节会自动被归类为“未匹配数据”并被记录
                pass

    # 2. 遍历原始数据并处理
    if not os.path.exists(raw_path):
        print(f"Error: Raw file not found: {raw_path}")
        sys.exit(1)

    # 确保输出目录和错误日志目录存在
    for path in [output_path, error_path]:
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory): 
            os.makedirs(directory)

    # 同时打开三个文件：读入 raw，追加写入 output，追加写入 error
    with open(raw_path, 'r', encoding='utf-8') as f_raw, \
         open(output_path, 'a', encoding='utf-8') as f_out, \
         open(error_path, 'a', encoding='utf-8') as f_err:
        
        for idx, line in enumerate(f_raw):
            if idx < start: continue
            if idx > end: break
            if not line.strip(): continue

            raw_data = json.loads(line)
            filter_target_id = f"{KOL}-{idx}-filter" 
            # filter_target_id = f"{KOL}-{idx}" 

            
            validation_array = validation_dict.get(filter_target_id) or validation_dict.get(f"{KOL}-{idx}")
            
            # --- 异常处理 1：未匹配的数据 ---
            if validation_array is None:
                error_record = {
                    "id": filter_target_id,
                    "error_type": "unmatched_validation_data",
                    "raw_data": raw_data
                }
                f_err.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                continue

            tweets = raw_data.get("tweets", [])
            
            # --- 异常处理 2：数据维度不一致 ---
            if len(tweets) != len(validation_array):
                error_record = {
                    "id": filter_target_id,
                    "error_type": "dimension_mismatch",
                    "tweets_length": len(tweets),
                    "validation_length": len(validation_array),
                    "raw_data": raw_data,
                    "validation_array": validation_array
                }
                f_err.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                continue

            # --- 开始拼接的 concatenating 逻辑 ---
            chunks = []
            current_text, current_media_urls = [], []

            for tweet, is_valid in zip(tweets, validation_array):
                if str(is_valid).lower() not in ['true', '1']: continue
                
                media_items = tweet.get("media", [])
                formatted_media_urls = [
                    item.get("url") for item in media_items 
                    if item.get("kind") == "image" or item.get("type") == "image"
                ][:5]

                if len(current_media_urls) + len(formatted_media_urls) > 5 and current_media_urls:
                    chunks.append({"text": "\n---\n".join(current_text), "media": current_media_urls})
                    current_text, current_media_urls = [], []

                current_text.append(tweet.get("text", ""))
                current_media_urls.extend(formatted_media_urls)

            if current_text or current_media_urls:
                chunks.append({"text": "\n---\n".join(current_text), "media": current_media_urls})

            # --- 将合并后的 chunks 转换为 Batch 任务请求 ---
            for chunk_idx, chunk in enumerate(chunks):
                summary_req_id = f"{KOL}-{idx}-summary-{chunk_idx}"
                user_prompt = f"twitter_text: {chunk['text']}"

                request_body = generate_request(
                    system_prompt=system_instruction,
                    user_prompt=user_prompt,
                    output_schema=structured_output,
                    image_list=chunk['media']  # 这里直接传入包含图片 Google File URI 的列表
                )

                result = {
                    "id": summary_req_id,
                    "request": request_body
                }
                f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                f_out.flush()

    print(f"处理完成！")
    print(f"✅ 正常的请求已保存至: {output_path}")
    print(f"⚠️ 异常的数据已保存至: {error_path}")
            


def run_workflow(KOL, start, end, mode, download):
    client = genai.Client(api_key=GEMINI_API_KEY)
    display_name = f"{KOL}-{start}-{end}-{int(time.time())}"

    raw_path = os.path.join("daily","original_" + KOL + ".jsonl")  
    filtering_requests_path = os.path.join("requests", KOL, "filter_request.jsonl")
    filtering_response_path = os.path.join("requests", KOL, "filtering_response.jsonl" )

    if mode == 0:
        generate_filtering_requests(KOL, raw_path, filtering_requests_path, start, end)
        submitTasks(client, "models/gemini-2.5-flash", display_name + "-filtering",  filtering_requests_path, filtering_response_path)
    
    elif mode == 1 and download == 0:
        name_prefix = f"{KOL}-{start}-{end}"  # 或者是完整的 {KOL}-{start}-{end}-?-{filtering}
        matched_jobs = []
        for job in client.batches.list():
            if job.display_name and name_prefix in job.display_name and 'filtering' in job.display_name:
                matched_jobs.append({
                    "name": job.name,             # 系统 ID (batches/xxxx)
                    "display_name": job.display_name,
                    "state": job.state,
                    "create_time": job.create_time
                })
        if matched_jobs:
            # 根据 create_time 字段找到最大值（即最近的时间）
            latest_job = max(matched_jobs, key=lambda x: x["create_time"])
            
            print(f"最近的任务名称: {latest_job["display_name"]}")
            print(f"创建时间: {latest_job["create_time"]}")
            print(f"系统 ID: {latest_job["name"]}")
            monitoring(client, latest_job["name"], filtering_response_path)
        else:
            print(f"No matched job prefix by {name_prefix}")
            return
    filtering_error_path = os.path.join("requests", KOL, "filtering_error.jsonl")
    summarizing_requests_path = os.path.join("requests", KOL, "summarizing_request.jsonl")
    summarizing_response_path = os.path.join("requests", KOL, "summarizing_response.jsonl")

    if mode < 2:
        generating_summarizer_requests(KOL, raw_path, filtering_response_path, summarizing_requests_path, filtering_error_path, start, end)
        
        submitTasks(client, "models/gemini-3-flash-preview", display_name + "-summarizing", summarizing_requests_path, summarizing_response_path)
    elif mode == 2 and download == 0:
        name_prefix = f"{KOL}-{start}-{end}"  
        matched_jobs = []
        for job in client.batches.list():
            if job.display_name and name_prefix in job.display_name and 'summarizing' in job.display_name:
                matched_jobs.append({
                    "name": job.name,             # 系统 ID (batches/xxxx)
                    "display_name": job.display_name,
                    "state": job.state,
                    "create_time": job.create_time
                })
        if matched_jobs:
            # 根据 create_time 字段找到最大值（即最近的时间）
            latest_job = max(matched_jobs, key=lambda x: x["create_time"])
            
            print(f"最近的任务名称: {latest_job["display_name"]}")
            print(f"创建时间: {latest_job["create_time"]}")
            print(f"系统 ID: {latest_job["name"]}")
            monitoring(client, latest_job["name"], summarizing_response_path)
        else:
            print(f"No matched job prefix by {name_prefix}")
            return
        
        

import sys

KOL = sys.argv[1]
start = int(sys.argv[2])
end = int(sys.argv[3])
mode = int(sys.argv[4])
download = int(sys.argv[5])

run_workflow(KOL, start, end, mode, download)