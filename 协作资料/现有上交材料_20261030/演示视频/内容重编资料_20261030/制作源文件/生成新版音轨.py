"""生成分段旁白、完整主音轨与同步字幕。运行环境：edge-tts 7.3.1。"""
import asyncio
import argparse
import json
from pathlib import Path
import re
import subprocess
import wave

import edge_tts

BUNDLE = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=BUNDLE/'音轨')
parser.add_argument('--voice', default='zh-CN-YunyangNeural')
parser.add_argument('--rate', default='-2%')
parser.add_argument('--prefix', default='联枢_新版旁白')
parser.add_argument('--gap', type=float, default=0.7)
options = parser.parse_args()
OUT = options.out
OUT.mkdir(exist_ok=True)
PARTS = OUT / '分段'
PARTS.mkdir(exist_ok=True)
FFMPEG = Path(r'D:\Tools\ClaudeToolchain\tools\ffmpeg\9.0.2\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe')
VOICE = options.voice
RATE = options.rate
PREFIX = options.prefix
SAMPLE_RATE = 48000
SEGMENTS = json.loads((OUT / '旁白分段.json').read_text(encoding='utf-8'))

def run(*args):
    subprocess.run([str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)], check=True)

def normalize_audio(target):
    scan = subprocess.run([str(FFMPEG), '-hide_banner', '-nostats', '-i', str(target), '-af',
        'loudnorm=I=-18:TP=-1.5:LRA=7:print_format=json', '-f', 'null', 'NUL'],
        capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
    measured = json.loads(re.search(r'\{\s*"input_i".*?\}', scan.stderr, re.S).group())
    options = ('loudnorm=I=-18:TP=-1.5:LRA=7:measured_I={input_i}:measured_TP={input_tp}:'
               'measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}:'
               'linear=true:print_format=json').format(**measured)
    temp = target.with_name(target.stem + '_响度调整.wav')
    run('-i', target, '-af', options, '-ar', SAMPLE_RATE, '-ac', 1, '-c:a', 'pcm_s16le', temp)
    temp.replace(target)
    (OUT/'响度处理.json').write_text(json.dumps({'target_lufs':-18,'target_true_peak_dbtp':-1.5,
        'source_measurement':measured}, ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

async def speak(segment, semaphore):
    stem = f'{segment["index"]:02d}_{segment["name"]}'
    mp3 = PARTS / (stem + '.mp3')
    srt = PARTS / (stem + '.srt')
    async with semaphore:
        for attempt in range(2):
            try:
                sub = edge_tts.SubMaker()
                communication = edge_tts.Communicate(segment['text'], VOICE, rate=RATE)
                with mp3.open('wb') as audio:
                    async for chunk in communication.stream():
                        if chunk['type'] == 'audio': audio.write(chunk['data'])
                        elif chunk['type'] in ('SentenceBoundary', 'WordBoundary'): sub.feed(chunk)
                srt.write_text(sub.get_srt(), encoding='utf-8')
                break
            except Exception:
                if attempt == 1: raise
    run('-i', mp3, '-ar', SAMPLE_RATE, '-ac', 1, '-c:a', 'pcm_s16le', PARTS/(stem+'.wav'))
    print(json.dumps({'segment':segment['index'],'status':'ready'}, ensure_ascii=True), flush=True)

def milliseconds(stamp):
    h,m,s,ms = map(int, re.split('[:,]', stamp))
    return h*3600000 + m*60000 + s*1000 + ms

def stamp(ms):
    ms = max(0, round(ms))
    h,ms = divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'

async def main():
    await asyncio.gather(*(speak(s, asyncio_semaphore) for s in SEGMENTS))
    target = OUT/(PREFIX+'主轨.wav')
    timeline=[]; cues=[]
    with wave.open(str(target), 'wb') as master:
        master.setnchannels(1); master.setsampwidth(2); master.setframerate(SAMPLE_RATE)
        cursor = SAMPLE_RATE  # 片头一秒
        master.writeframes(b'\0' * (cursor*2))
        for index,segment in enumerate(SEGMENTS):
            stem=f'{segment["index"]:02d}_{segment["name"]}'
            with wave.open(str(PARTS/(stem+'.wav')), 'rb') as part:
                frames=part.getnframes(); master.writeframes(part.readframes(frames))
            start_ms=cursor*1000/SAMPLE_RATE
            raw=(PARTS/(stem+'.srt')).read_text(encoding='utf-8')
            for block in re.split(r'\n\s*\n',raw.strip()):
                lines=block.strip().splitlines()
                if len(lines)<3: continue
                a,b=lines[1].split(' --> ')
                content=''.join(lines[2:])
                wrapped='\n'.join(content[i:i+26] for i in range(0,len(content),26))
                cues.append({'start':start_ms+milliseconds(a),'end':min(start_ms+milliseconds(b),start_ms+frames*1000/SAMPLE_RATE),'text':wrapped})
            timeline.append({'index':segment['index'],'name':segment['name'],'start_seconds':round(cursor/SAMPLE_RATE,3),
                             'end_seconds':round((cursor+frames)/SAMPLE_RATE,3),'speech_seconds':round(frames/SAMPLE_RATE,3),
                             'audio':'分段/'+stem+'.wav','text':segment['text'],
                             'gap_after_seconds':2.0 if index==len(SEGMENTS)-1 else segment.get('gap_after_seconds',options.gap)})
            cursor+=frames
            silence=round(SAMPLE_RATE*(2.0 if index==len(SEGMENTS)-1 else segment.get('gap_after_seconds',options.gap)))
            master.writeframes(b'\0'*(silence*2)); cursor+=silence
    # 句子边界偶有约50ms重叠，压到下一句起点，避免字幕同时出现。
    for index,cue in enumerate(cues[:-1]): cue['end']=min(cue['end'],cues[index+1]['start'])
    (OUT/(PREFIX+'字幕.srt')).write_text('\n\n'.join(f'{i}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{c["text"]}' for i,c in enumerate(cues,1))+'\n',encoding='utf-8')
    normalize_audio(target)
    run('-i',target,'-codec:a','libmp3lame','-b:a','192k',OUT/(PREFIX+'试听.mp3'))
    duration=cursor/SAMPLE_RATE
    (OUT/'音轨时间轴.json').write_text(json.dumps({'voice':VOICE,'rate':RATE,'sample_rate':SAMPLE_RATE,
        'duration_seconds':round(duration,3),'lead_seconds':1.0,'default_segment_gap_seconds':options.gap,'tail_seconds':2.0,
        'background_music':None,'segments':timeline},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    table=['# 新版旁白实际时间轴','',f'总长 {int(duration//60)}分{duration%60:05.2f}秒。以主音轨WAV为剪辑基准。','',
           '| 段落 | 开始 | 结束 | 对应内容 |','|---|---|---|---|']
    def clock(sec): return f'{int(sec//60):02d}:{sec%60:06.3f}'
    for item in timeline: table.append(f'| {item["index"]:02d} | {clock(item["start_seconds"])} | {clock(item["end_seconds"])} | {item["name"]} |')
    table.extend(['',f'音色为{VOICE}，语速设置为{RATE}；主轨单声道48kHz PCM。段间停顿见音轨时间轴，片头1秒、片尾2秒。MP3用于试听，WAV用于剪辑。','',
                  '配音使用合成语音。字幕按句子时间与主音轨对齐。'])
    (OUT/'实际时间轴.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
    print(json.dumps({'duration_seconds':round(duration,3),'segments':len(timeline),'subtitle_cues':len(cues)}),flush=True)

if __name__=='__main__':
    asyncio_semaphore=asyncio.Semaphore(2)
    asyncio.run(main())
