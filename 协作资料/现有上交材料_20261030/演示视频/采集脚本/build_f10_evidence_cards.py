"""Render editorial evidence cards from the already captured F10 records.

This does not contact Wutong or run an experiment. The cards are record excerpts,
not screenshots of the platform or a fresh observation.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'V3-f10'
SCALE = 2
COLORS = {'bg': '#F2F5F7', 'ink': '#173448', 'muted': '#526B7B',
          'blue': '#126E94', 'green': '#157463', 'line': '#C7D6DF',
          'amber': '#986A15', 'white': '#FFFFFF'}
FONTS = Path('C:/Windows/Fonts')


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def read_lines(name):
    return [json.loads(line) for line in (OUT / name).read_text(encoding='utf-8').splitlines() if line.strip()]


def font(size, bold=False, mono=False):
    name = ('consolab.ttf' if bold else 'consola.ttf') if mono else ('msyhbd.ttc' if bold else 'msyh.ttc')
    return ImageFont.truetype(str(FONTS / name), round(size * SCALE))


def text(x, y, value, size=28, color='ink', bold=False, mono=False):
    draw.text((x * SCALE, y * SCALE), str(value), font=font(size, bold, mono), fill=COLORS.get(color, color))


def box(x, y, width, height, fill='white', outline=None, radius=18):
    draw.rounded_rectangle((x * SCALE, y * SCALE, (x + width) * SCALE, (y + height) * SCALE),
                           radius=radius * SCALE, fill=COLORS.get(fill, fill),
                           outline=COLORS.get(outline, outline) if outline else None, width=2)


def line(x1, y1, x2, y2, color='line', width=2):
    draw.line((x1 * SCALE, y1 * SCALE, x2 * SCALE, y2 * SCALE), fill=COLORS[color], width=width * SCALE)


def base(title, subtitle):
    global image, draw
    image = Image.new('RGB', (3840, 2160), COLORS['bg'])
    draw = ImageDraw.Draw(image)
    box(72, 48, 336, 44, fill='blue', radius=6)
    text(88, 51, '本次运行记录摘录 · F10', 23, 'white', True)
    text(72, 119, title, 46, bold=True)
    text(72, 188, subtitle, 25, 'muted')


def clock(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=8))).strftime('%H:%M:%S.%f')[:-3]


state = read('incident-state.json')
evaluation = read('evaluation-result.json')[0]
pairing = read('access/pairing-summary.json')
samples = read('order-samples.json')['samples']
events = read_lines('events.jsonl')
assert evaluation['scenario'] == 'F10' and evaluation['method'] == 'M0'
task = next(t for t in state['tasks'] if t['tool'] == 'db.restore_writes')
assert len([t for t in state['tasks'] if t['tool'] == 'db.restore_writes']) == 1
pair = next(p for p in pairing['pairs'] if p['route'] == task['tool'])
assert pair['caller']['aic'] == 'A01' and pair['callee']['aic'] == 'A03'
assert pair['coordinator_status'] == 202 and pair['domain_status'] == 200
start_event = next(e for e in events if e.get('event') == 'task_started' and e.get('logical_task_id') == task['logical_task_id'])
return_event = next(e for e in events if e.get('event') == 'task_returned' and e.get('logical_task_id') == task['logical_task_id'])
assert task['product']['status'] == 'ok'
assert task['product']['operation']['before']['value'] is True
assert task['product']['operation']['after']['value'] is False

base('跨端请求有双端记录，返回结果可对应', '2026-10-29 · 北京时间（UTC+8） · F10 / M0 / seed 101 · 同次运行')
text(72, 256, 'A01 协调端  →  梧桐 AMQPS 群组任务  →  A03 数据库端', 33, 'blue', True)
for x, title, timestamp, status in (
    (72, '调用端 AMP 记录', pair['coordinator_timestamp'], pair['coordinator_status']),
    (994, '执行端 AMP 记录', pair['domain_timestamp'], pair['domain_status']),
):
    box(x, 322, 854, 300, outline='line')
    text(x + 32, 348, title, 28, bold=True)
    text(x + 32, 402, clock(timestamp), 32, 'blue', mono=True)
    text(x + 32, 459, 'request.method: start', 28, mono=True)
    text(x + 32, 506, 'request.route: db.restore_writes', 28, mono=True)
    text(x + 32, 553, f'response.statusCode: {status}', 28, 'green', True, True)
text(92, 648, '双端相同 correlation_id：' + pair['correlation_id'], 25, 'muted', mono=False)
box(72, 706, 1776, 198, outline='line')
text(104, 726, '协调者收到的任务产物', 28, bold=True)
text(104, 777, f"status: {task['product']['status']}    operation.state: {task['product']['operation']['state']}", 31, 'green', True, True)
text(104, 834, 'read_only: true → false', 31, 'green', True, True)
text(1002, 726, '协调者原生事件（北京时间）', 26, bold=True)
text(1002, 779, 'task_started   ' + clock(start_event['at']), 27, mono=True)
text(1002, 833, 'task_returned  ' + clock(return_event['at']), 27, mono=True)
text(72, 934, '202 为异步受理记录；业务恢复另看订单验证。A01、A03 为匿名角色代号。', 25, 'muted')
text(72, 982, '来源：access/pairing-summary.json、双端 access 日志、incident-state.json、events.jsonl', 22, 'muted')
text(72, 1021, '日志摘录可视化；不是平台页面截图。时间按原始 UTC 字段换算，显示到毫秒。', 22, 'muted')
image.save(OUT / 'cross-end-request-response.png')

order = state['result']['order_observation']
rows = order['events'][:3]
assert [r['phase'] for r in rows] == ['create', 'query', 'cancel']
assert len({r['request_key'] for r in rows}) == 1
assert all(r['http_status'] == 200 and r['outcome'] == 'success' for r in rows)
counts = Counter(s['outcome'] for s in samples)
assert counts == {'success': 36, 'unknown': 16}
assert order['requests'] == order['success'] == 30 and order['completed_workflows'] == 10
assert order['failed'] == order['unknown'] == 0
base('恢复效果落实到真实订单访问', 'F10 同次运行 · 最终验证窗内第一个完整订单流程（按原顺序摘录 3 / 30 条）')
box(72, 254, 1776, 358, outline='line')
cols = [104, 310, 570, 1350, 1534]
for x, label in zip(cols, ['相对窗起点', '阶段', 'HTTP 请求路径', '状态码', '结果']):
    text(x, 279, label, 26, 'muted', True)
line(104, 330, 1816, 330)
phase_labels = {'create': '创建订单', 'query': '查询订单', 'cancel': '取消订单'}
display_paths = ['/orders', '/orders/[order-id]', '/orders/[order-id]/cancel']
for index, (r, path) in enumerate(zip(rows, display_paths)):
    y = 355 + index * 77
    text(cols[0], y, f"{r['elapsed_seconds']:.3f} s", 30, mono=True)
    text(cols[1], y, phase_labels[r['phase']], 29, bold=True)
    text(cols[2], y, r['method'] + ' ' + path, 29, mono=True)
    text(cols[3], y, str(r['http_status']), 32, 'green', True, True)
    text(cols[4], y, r['outcome'], 30, 'green', True, True)
text(104, 571, '[order-id] 为同一个测试订单编号；只缩写编号，不改变请求方法、路径结构或结果。', 21, 'muted')
box(72, 654, 854, 242, outline='line')
text(104, 680, '覆盖故障前后的连续观察', 29, bold=True)
text(104, 735, '52 条', 54, 'blue', True)
text(350, 747, '36 成功  /  16 当时未知', 31, 'ink', True)
text(104, 834, '包含故障前 5 条基线；未知随后收敛。', 25, 'muted')
box(994, 654, 854, 242, outline='line')
text(1026, 680, f"最终 {order['duration_seconds']:.3f} 秒业务验证窗", 29, bold=True)
text(1026, 737, '30 / 30 请求成功', 43, 'green', True)
text(1026, 834, '10 个完整流程  ·  0 失败  ·  0 未知', 29, 'ink', True)
text(72, 934, '两组数据对应不同范围；平台调用次数、任务受理状态与订单成功次数分别统计。', 25, 'muted')
text(72, 982, '来源：incident-state.json → result.order_observation；order-samples.json → samples', 22, 'muted')
text(72, 1021, '本图为真实记录摘录可视化；不是交互式业务页面或新的运行结果。', 22, 'muted')
image.save(OUT / 'business-access-workflow.png')

sources = {
    'schema': 'f10-editorial-record-excerpts/1',
    'capture_kind': 'visualization_from_existing_same_run_records',
    'new_experiment_performed': False,
    'is_platform_screenshot': False,
    'incident_id': state['id'],
    'case_key': pairing['case_key'],
    'cross_end': {
        'image': 'cross-end-request-response.png',
        'source_files': ['access/pairing-summary.json', 'access/coordinator.jsonl', 'access/domain.jsonl', 'incident-state.json', 'events.jsonl', 'evaluation-result.json'],
        'pair': pair,
        'task_selector': {'tool': task['tool'], 'logical_task_id': task['logical_task_id']},
        'selected_request_args': task['args'],
        'selected_product': {k: task['product'][k] for k in ['logical_task_id', 'executor_aic', 'status', 'operation', 'facts']},
        'task_started_event': start_event,
        'task_returned_event': return_event,
        'matching': 'Both access records match the exact correlation_id; the one restore_writes task in the same case supplies the product. AMP statuses are not interpreted as business success.',
        'time_display': 'Original UTC converted to Asia/Shanghai UTC+08:00; displayed to millisecond precision, not a measurement of clock accuracy.'
    },
    'business_access': {
        'image': 'business-access-workflow.png',
        'final_window_source': 'incident-state.json#/result/order_observation',
        'selected_event_indices': [0, 1, 2],
        'selected_events': rows,
        'path_display': 'The same order ID in paths is displayed as [order-id]; method, elapsed time, HTTP status and outcome are unchanged.',
        'final_window_summary': {k: order[k] for k in ['duration_seconds', 'requests', 'success', 'failed', 'unknown', 'completed_workflows']},
        'continuous_source': 'order-samples.json#/samples',
        'continuous_summary': {'records': len(samples), **dict(counts), 'includes_pre_fault_baseline_records': 5}
    },
    'dimensions': [3840, 2160],
    'privacy': 'Only existing anonymized role labels and selected non-secret fields are used. No approval proof, identity URL, provider name or credential is included.'
}
(OUT / 'evidence-cards-source.json').write_text(json.dumps(sources, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'generated': ['cross-end-request-response.png', 'business-access-workflow.png', 'evidence-cards-source.json'], 'dimensions': [3840, 2160]}, ensure_ascii=False))
