import urllib.request, json, os, urllib.parse, time

print('=== 等待后端 ===')
for i in range(10):
    try:
        urllib.request.urlopen('http://localhost:8000/api/process/vehicles', timeout=2)
        print(f'后端已就绪')
        break
    except Exception:
        time.sleep(2)
else:
    print('后端启动超时'); exit(1)

# 1. 加载 Excel
excel_path = r'd:\AI_model\snail_avatar\data\蜗牛项目-VTS_SSTS_V7.0.xlsx'
boundary = '----Boundary1234567890'
with open(excel_path, 'rb') as f:
    file_data = f.read()
body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{os.path.basename(excel_path)}"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode() + file_data + f'\r\n--{boundary}--\r\n'.encode()
req = urllib.request.Request('http://localhost:8000/api/files/open', data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}, method='POST')
urllib.request.urlopen(req, timeout=60).read()
print('Excel 加载完成')
time.sleep(2)

# 2. 获取 instance_key
r = urllib.request.urlopen('http://localhost:8000/api/process/vehicles')
ik = json.loads(r.read())['vehicles'][0]['instance_key']
print(f'instance_key: {ik}')

# 3. 启动完整流程
ik_enc = urllib.parse.quote(ik)
req = urllib.request.Request(f'http://localhost:8000/api/process/{ik_enc}/run', data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
try:
    resp = urllib.request.urlopen(req, timeout=30).read()
    print(f'流程启动: {resp.decode()[:200]}')
except Exception as e:
    print(f'启动失败: {e}')

# 4. 轮询 step 执行状态
print('\n=== 轮询 step 执行结果 ===')
for i in range(120):
    time.sleep(5)
    try:
        url = f'http://localhost:8000/api/process/{ik_enc}/status'
        r = urllib.request.urlopen(url, timeout=5)
        resp = json.loads(r.read())
        
        # process_service 返回的 status 结构
        steps_status = resp.get('steps_status', {}) or resp.get('step_results', {}) or {}
        
        # 找 CHECK_REGULATIONS_AND_REFERENCES (step2_3)
        target_sid = 'CHECK_REGULATIONS_AND_REFERENCES'
        step23 = steps_status.get(target_sid)
        
        if step23 is None and isinstance(steps_status, dict):
            # 遍历找
            for sid, sval in steps_status.items():
                if 'REGULATIONS' in sid or '2_3' in sid:
                    step23 = sval
                    target_sid = sid
                    break
        
        if step23:
            status = step23.get('status', 'unknown') if isinstance(step23, dict) else str(step23)
            print(f'  [{i*5}s] {target_sid}: status={status}')
            
            if status in ('completed', 'done', 'success', 'error', 'failed'):
                result = step23.get('result', step23.get('output', {})) if isinstance(step23, dict) else {}
                
                struct = None
                reasoning = None
                formatter_result = None
                
                if isinstance(result, dict):
                    formatter_result = result.get('formatter_result', result.get('structured_data', {}))
                    # result_formatter 返回的是 {"structured_data": {...}, "reasoning_logic": "..."}
                    if isinstance(formatter_result, dict):
                        struct = formatter_result.get('structured_data', {})
                        reasoning = formatter_result.get('reasoning_logic', '')
                
                print(f'\n=== step2_3 最终结果 ===')
                print(f'status: {status}')
                print(f'structured_data: {json.dumps(struct, ensure_ascii=False)[:2000]}')
                print(f'reasoning_logic: {str(reasoning)[:500] if reasoning else "(空)"}')
                
                if not struct:
                    print('\n❌ 问题依然存在！formatter 输出的 structured_data 为空')
                else:
                    regs = struct.get('regulations', [])
                    vts_ref = struct.get('VTS/SSTS_references', {})
                    print(f'\n✅ structured_data 有内容')
                    print(f'   regulations 条数: {len(regs) if isinstance(regs, list) else "N/A"}')
                    print(f'   VTS/SSTS_references keys: {list(vts_ref.keys()) if isinstance(vts_ref, dict) else "N/A"}')
                break
        
        # 也打印一下总体进度
        overall = resp.get('status', resp.get('overall', ''))
        completed = sum(1 for s in (steps_status.values() if isinstance(steps_status, dict) else []) 
                       if isinstance(s, dict) and s.get('status') in ('completed', 'done', 'success'))
        total = len(steps_status) if isinstance(steps_status, dict) else 0
        print(f'  [{i*5}s] 总体={overall} 进度={completed}/{total}')
        
    except Exception as e:
        if i % 6 == 0:
            print(f'  [{i*5}s] 轮询异常: {e}')
        continue
else:
    print('超时')
