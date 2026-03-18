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
        job_info = client.batches.get(name=JOB_NAME)
        state = job_info.state.name if hasattr(job_info.state, 'name') else str(job_info.state)
        
        print(f"[{time.strftime('%H:%M:%S')}] 当前状态: {state}")
        
        if state in ['JOB_STATE_SUCCEEDED', 'SUCCEEDED']:
            print("\n✅ 任务已成功完成！开始下载结果文件...")
            result_file_name = job_info.dest.file_name
            file_content_bytes = client.files.download(file=result_file_name)
            file_content = file_content_bytes.decode('utf-8')
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(file_content)
                
            print(f"🎉 结果已保存至本地: {output_path}")
            break
            
        elif state in ['JOB_STATE_FAILED', 'FAILED', 'JOB_STATE_CANCELLED', 'CANCELLED']:
            print("\n❌ 任务未成功执行。")
            if hasattr(job_info, 'error_uri') and job_info.error_uri:
                print(f"详细错误日志位置: {job_info.error_uri}")
            
            sys.exit(1)
            
        time.sleep(120)

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
                pass

    if not os.path.exists(raw_path):
        print(f"Error: Raw file not found: {raw_path}")
        sys.exit(1)

    for path in [output_path, error_path]:
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory): 
            os.makedirs(directory)

    with open(raw_path, 'r', encoding='utf-8') as f_raw, \
         open(output_path, 'a', encoding='utf-8') as f_out, \
         open(error_path, 'a', encoding='utf-8') as f_err:
        
        for idx, line in enumerate(f_raw):
            if idx < start: continue
            if idx > end: break
            if not line.strip(): continue

            raw_data = json.loads(line)
            filter_target_id = f"{KOL}-{idx}-filter" 
            
            validation_array = validation_dict.get(filter_target_id) or validation_dict.get(f"{KOL}-{idx}")
            
            if validation_array is None:
                error_record = {
                    "id": filter_target_id,
                    "error_type": "unmatched_validation_data",
                    "raw_data": raw_data
                }
                f_err.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                continue

            tweets = raw_data.get("tweets", [])
            
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

            for chunk_idx, chunk in enumerate(chunks):
                summary_req_id = f"{KOL}-{idx}-summary-{chunk_idx}"
                user_prompt = f"twitter_text: {chunk['text']}"

                request_body = generate_request(
                    system_prompt=system_instruction,
                    user_prompt=user_prompt,
                    output_schema=structured_output,
                    image_list=chunk['media']  
                )

                result = {
                    "id": summary_req_id,
                    "request": request_body
                }
                f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                f_out.flush()

def generate_retry_requests(response_path, original_req_path, retry_req_path):
    failed_ids = set()
    
    if not os.path.exists(response_path):
        return False
        
    with open(response_path, 'r', encoding='utf-8') as f_resp:
        for line in f_resp:
            if not line.strip(): continue
            try:
                data = json.loads(line)
                if "error" in data:
                    failed_ids.add(data.get("id"))
            except json.JSONDecodeError:
                continue
                
    if not failed_ids:
        return False
        
    print(f"⚠️ 提取到 {len(failed_ids)} 个失败请求，正在生成重试批次文件...")
    
    # 注意: 这里 'w' 模式会自动清空/覆盖旧的 retry_request 文件
    with open(original_req_path, 'r', encoding='utf-8') as f_orig, \
         open(retry_req_path, 'w', encoding='utf-8') as f_retry:
        for line in f_orig:
            if not line.strip(): continue
            try:
                req_data = json.loads(line)
                if req_data.get("id") in failed_ids:
                    f_retry.write(line)
            except json.JSONDecodeError:
                continue
                
    return True

def get_job_to_monitor(client, name_prefix, job_type, download_flag):
    matched_jobs = []
    target_states = ['JOB_STATE_SUCCEEDED', 'SUCCEEDED', 'JOB_STATE_RUNNING', 'RUNNING', 'JOB_STATE_PENDING', 'PENDING']
    
    for job in client.batches.list():
        if job.display_name and name_prefix in job.display_name and job_type in job.display_name:
            state = job.state.name if hasattr(job.state, 'name') else str(job.state)
            if state in target_states:
                matched_jobs.append({
                    "name": job.name,             
                    "display_name": job.display_name,
                    "state": state,
                    "create_time": job.create_time
                })
                
    if not matched_jobs:
        return None

    matched_jobs.sort(key=lambda x: x["create_time"], reverse=True)

    if download_flag == 1:
        print(f"\n🔍 找到以下 {job_type} 任务:")
        for i, job in enumerate(matched_jobs):
            print(f"  [{i}] 任务名称: {job['display_name']} | 状态: {job['state']} | 创建时间: {job['create_time']}")
        
        while True:
            try:
                choice = input("\n⌨️ 请输入要处理的任务序号 (输入 q 跳过/退出): ")
                if choice.lower() == 'q':
                    return None
                choice = int(choice)
                if 0 <= choice < len(matched_jobs):
                    selected_job = matched_jobs[choice]
                    break
                else:
                    print("❌ 序号超出范围，请重新输入。")
            except ValueError:
                print("❌ 请输入有效的数字序号。")
    else:
        selected_job = matched_jobs[0]
        print(f"⚡ 自动选择最近的 {job_type} 任务: {selected_job['display_name']}")
        
    print(f"📌 系统 ID: {selected_job['name']}")
    return selected_job['name']

def count_errors(filepath):
    count = 0
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    if "error" in data:
                        count += 1
                except json.JSONDecodeError:
                    pass
    return count

def merge_retry_and_clean(summary_path, retry_path):
    valid_lines = []
    
    # 1. 读取 summary_response，抛弃里面所有的 error 记录
    if os.path.exists(summary_path):
        with open(summary_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    if "error" not in data:
                        valid_lines.append(line)
                except json.JSONDecodeError:
                    pass
                    
    # 2. 读取完整的 retry_response (无论成败) 拼接到 valid_lines
    if os.path.exists(retry_path):
        with open(retry_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                valid_lines.append(line)
                
    # 3. 覆盖写入 summary_response
    with open(summary_path, 'w', encoding='utf-8') as f:
        for line in valid_lines:
            f.write(line)
            
    # 4. 清空 retry_response 文件
    if os.path.exists(retry_path):
        open(retry_path, 'w', encoding='utf-8').close()

def run_workflow(KOL, start, end, mode, download):
    client = genai.Client(api_key=GEMINI_API_KEY)
    display_name = f"{KOL}-{start}-{end}-{int(time.time())}"

    raw_path = os.path.join("daily","original_" + KOL + ".jsonl")  
    filtering_requests_path = os.path.join("requests", KOL, "filter_request.jsonl")
    filtering_response_path = os.path.join("requests", KOL, "filtering_response.jsonl" )

    if mode == 0:
        generate_filtering_requests(KOL, raw_path, filtering_requests_path, start, end)
        submitTasks(client, "models/gemini-2.5-flash", display_name + "-filtering",  filtering_requests_path, filtering_response_path)
    
    elif mode == 1:
        name_prefix = f"{KOL}-{start}-{end}"
        job_name = get_job_to_monitor(client, name_prefix, "filtering", download)
        if job_name:
            monitoring(client, job_name, filtering_response_path)
        else:
            return

    filtering_error_path = os.path.join("requests", KOL, "filtering_error.jsonl")
    summarizing_requests_path = os.path.join("requests", KOL, "summarizing_request.jsonl")
    summarizing_response_path = os.path.join("requests", KOL, "summarizing_response.jsonl")

    if mode < 2:
        generating_summarizer_requests(KOL, raw_path, filtering_response_path, summarizing_requests_path, filtering_error_path, start, end)
        submitTasks(client, "models/gemini-3-flash-preview", display_name + "-summarizing", summarizing_requests_path, summarizing_response_path)
        
    elif mode == 2:
        name_prefix = f"{KOL}-{start}-{end}"
        job_name = get_job_to_monitor(client, name_prefix, "summarizing", download)
        if job_name:
            monitoring(client, job_name, summarizing_response_path)
        else:
            return
            
    elif mode == 3:
        retry_requests_path = os.path.join("requests", KOL, "summarizing_retry_request.jsonl")
        retry_response_path = os.path.join("requests", KOL, "summarizing_retry_response.jsonl")
        
        name_prefix = f"{KOL}-{start}-{end}"
        
        # 1. 先检查是否已经有未处理完的 retry 任务
        existing_job_name = get_job_to_monitor(client, name_prefix, "retry", download)
        if existing_job_name:
            print(f"🔍 检测到历史/正在运行的 retry 任务，正在接管监控...")
            monitoring(client, existing_job_name, retry_response_path)
            
            print("🔄 任务完成，正在清洗老错误并合并最新重试结果...")
            merge_retry_and_clean(summarizing_response_path, retry_response_path)
            time.sleep(2)
        else:
            print("📭 当前无活跃的 retry 任务，准备检查错误数量...")

        # 2. 开始检查是否需要发起新一轮重试
        while True:
            current_errors = count_errors(summarizing_response_path)
            print(f"📊 当前 [summary_response] 中的错误总数: {current_errors}")
            
            if current_errors <= 50:
                print("✅ 错误数少于或等于 50 条，重试流程结束！")
                break
                
            print("\n🚀 错误数大于 50，开始准备本轮重试任务...")
            needs_retry = generate_retry_requests(summarizing_response_path, summarizing_requests_path, retry_requests_path)
            
            if needs_retry:
                retry_display_name = f"{KOL}-{start}-{end}-retry-{int(time.time())}"
                # 阻塞执行：提交并监控任务，结果会下载到 retry_response_path
                submitTasks(client, "models/gemini-3-flash-preview", retry_display_name, retry_requests_path, retry_response_path)
                
                # 3. 任务完成后：合并新数据，清除老 error，并清空 retry_response
                print("🔄 任务完成，正在清洗老错误并合并最新重试结果...")
                merge_retry_and_clean(summarizing_response_path, retry_response_path)
                
                # 稍微休眠，给文件系统缓冲时间
                time.sleep(2)
            else:
                break

if __name__ == '__main__':
    KOL = sys.argv[1]
    start = int(sys.argv[2])
    end = int(sys.argv[3])
    mode = int(sys.argv[4])
    download = int(sys.argv[5])

    run_workflow(KOL, start, end, mode, download)