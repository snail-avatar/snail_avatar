import urllib.request, json, urllib.parse, time

ik = '增程车型_reevlto'
ik_enc = urllib.parse.quote(ik)

# 启动流程
print('启动流程...')
req = urllib.request.Request(f'http://localhost:8000/api/process/{ik_enc}/run', data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
try:
    r = urllib.request.urlopen(req, timeout=10)
    print(f'启动成功: {r.read().decode()[:200]}')
except Exception as e:
    print(f'启动返回: {e}')

# 轮询 step2_3
print('\n轮询 step2_3 执行状态...')
for i in range(240):
    time.sleep(5)
    try:
        r = urllib.request.urlopen(f'http://localhost:8000/api/process/{ik_enc}/status', timeout=5)
        resp = json.loads(r.read())
        tree = resp.get('controller_state', {}).get('states_tree', [])
        
        step23_result = None
        for state in tree:
            if state.get('step_id') == 'loop_categories':
                for li in state.get('loop_items', []):
                    for inner in li.get('inner_steps', []):
                        if inner.get('step_id') == 'CHECK_REGULATIONS_AND_REFERENCES':
                            step23_result = inner
                            break
        
        is_running = resp.get('is_running', False)
        print(f'[{i*5}s] running={is_running} step2_3_status={step23_result.get("status") if step23_result else "N/A"}', end='')
        
        if step23_result and step23_result.get('status') in ('completed', 'done', 'success', 'error', 'failed'):
            result = step23_result.get('step_result', {})
            print()
            print(f'\n=== step2_3 status: {step23_result.get("status")} ===')
            print(f'result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}')
            
            # 尝试各种路径找 formatter_result
            struct = None
            reasoning = None
            if isinstance(result, dict):
                # path 1: result.formatter_result.{structured_data, reasoning_logic}
                fr = result.get('formatter_result')
                if fr and isinstance(fr, dict):
                    struct = fr.get('structured_data')
                    reasoning = fr.get('reasoning_logic')
                # path 2: 直接在 result 里
                elif 'structured_data' in result:
                    struct = result.get('structured_data')
                    reasoning = result.get('reasoning_logic')
                # path 3: raw_result 经过格式化后的结果
                elif 'raw_result' in result:
                    print(f'raw_result (前300字): {str(result["raw_result"])[:300]}')
            
            print(f'\nstructured_data: {json.dumps(struct, ensure_ascii=False)[:2000]}')
            print(f'\nreasoning_logic: {str(reasoning)[:500] if reasoning else "(空)"}')
            
            if struct and isinstance(struct, dict):
                regs = struct.get('regulations', [])
                if regs:
                    print(f'\n✅ 成功！regulations 有 {len(regs)} 条')
                else:
                    print(f'\n⚠️ structured_data 存在但 regulations 为空')
            else:
                print(f'\n❌ 问题仍存在！structured_data 为空')
            break
        
        # 也打印 step_result 的简单摘要
        if step23_result:
            sr_keys = list(step23_result.get('step_result', {}).keys()) if isinstance(step23_result.get('step_result'), dict) else []
            print(f' result_keys={sr_keys[:5]}', end='')
        
        print()
        
        # 如果流程已经结束
        if resp.get('is_finished') and not is_running:
            print('\n=== 流程已结束 ===')
            break
            
    except Exception as e:
        if i % 12 == 0:
            print(f'[{i*5}s] 异常: {e}')
        continue
else:
    print('超时')
