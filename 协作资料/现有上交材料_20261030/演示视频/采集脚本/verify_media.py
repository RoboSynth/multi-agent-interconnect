"""Validate exported video/action pairs and PNG dimensions; no cloud operations."""
import json
from pathlib import Path
import subprocess
from PIL import Image

root = Path(__file__).resolve().parents[1]
config = json.loads(Path('D:/Tools/ClaudeToolchain/config/tools.json').read_text(encoding='utf-8'))
checks = []
for folder in sorted(root.glob('V*-*')):
    videos = []
    for actions_path in sorted(folder.glob('*actions.json')):
        actions = json.loads(actions_path.read_text(encoding='utf-8-sig'))
        video_path = folder / actions.get('video', 'video.webm')
        probe = json.loads(subprocess.check_output([config['ffprobe'], '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,avg_frame_rate:format=duration', '-of', 'json', str(video_path)],
            encoding='utf-8'))
        stream = probe['streams'][0]
        duration = float(probe['format']['duration'])
        assert (stream['width'], stream['height']) == (1920, 1080), video_path.name
        errors = []
        for event in actions['actions']:
            if event['atSeconds'] > duration + 0.12:
                errors.append({'id': event['id'], 'reason': 'past_video_end'})
            box = event.get('box')
            if box and not (0 <= box['x'] <= 1920 and 0 <= box['y'] <= 1080
                            and 0 <= box['width'] <= 1920 and 0 <= box['height'] <= 1080):
                errors.append({'id': event['id'], 'reason': 'invalid_box'})
        assert not errors, errors
        videos.append({'file': video_path.name, 'actions_file': actions_path.name, 'width': stream['width'],
            'height': stream['height'], 'duration_seconds': duration, 'frame_rate': stream['avg_frame_rate'],
            'actions': len(actions['actions']), 'action_validation_errors': errors,
            'pre_first_frame_actions': [x['label'] for x in actions['actions'] if x['atSeconds'] < 0],
            'capture_errors': actions.get('captureErrors', [])})
    screenshots = []
    for path in sorted(folder.glob('*.png')):
        size = Image.open(path).size
        assert size == (3840, 2160), (path.name, size)
        screenshots.append({'file': path.name, 'width': size[0], 'height': size[1]})
    checks.append({'category': folder.name, 'videos': videos, 'screenshots': screenshots})
result = {'status': 'passed', 'scope': 'video dimensions/duration, paired action timing/boxes, PNG dimensions',
    'note': 'A first navigation may start before the first encoded frame; its negative offset is retained. Visual privacy/content review is separate.',
    'checks': checks}
(root / '媒体核验.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': 'passed', 'video_count': sum(len(x['videos']) for x in checks),
    'screenshot_count': sum(len(x['screenshots']) for x in checks)}, ensure_ascii=False))
