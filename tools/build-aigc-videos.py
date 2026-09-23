#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 AIGC 视频素材压成网页可用版本并嵌入作品集 index.html。

用法:
    python tools/build-aigc-videos.py <素材目录> [--title "AIGC 短片"]

流程:
1. 扫描素材目录中的 .mp4/.mov/.m4v/.webm
2. ffmpeg 转码 -> works/<slug>.mp4 (720p / H.264 / yuv420p / faststart, 音频 AAC 128k)
   自动控码率，尽量压到单文件 < 20MB（GitHub Pages 单文件上限 100MB，仓库总量 < 1GB）
3. 抽取第 1 秒画面作封面 works/<slug>.jpg
4. 生成 HTML 区块，注入 index.html 的
   <!-- AIGC-VIDEOS:START --> ... <!-- AIGC-VIDEOS:END --> 标记之间

依赖: ffmpeg（本机可用剪映自带: D:/Program Files/JianyingPro/8.9.0.13361/ffmpeg.exe）
"""
import os
import re
import subprocess
import sys
import html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKS = os.path.join(ROOT, 'works')
INDEX = os.path.join(ROOT, 'index.html')

FFMPEG_CANDIDATES = [
    r'D:\Program Files\JianyingPro\8.9.0.13361\ffmpeg.exe',
    r'C:\Program Files\JianyingPro\8.9.0.13361\ffmpeg.exe',
    'ffmpeg',
]

VIDEO_EXT = ('.mp4', '.mov', '.m4v', '.webm', '.avi')

MARK_START = '<!-- AIGC-VIDEOS:START -->'
MARK_END = '<!-- AIGC-VIDEOS:END -->'


def find_ffmpeg():
    for c in FFMPEG_CANDIDATES:
        if os.path.isabs(c):
            if os.path.exists(c):
                return c
        else:
            from shutil import which
            w = which(c)
            if w:
                return w
    raise SystemExit('[ERR] 找不到 ffmpeg，请确认剪映安装路径或把 ffmpeg 加进 PATH')


def slugify(name):
    s = re.sub(r'\.[a-z0-9]+$', '', name, flags=re.I)
    s = re.sub(r'[^\w\u4e00-\u9fff]+', '-', s).strip('-').lower()
    return s or 'video'


def probe_duration(ff, path):
    try:
        out = subprocess.run([ff, '-i', path], capture_output=True, text=True,
                             encoding='utf-8', errors='ignore', timeout=60)
        m = re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', out.stderr)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def calc_bitrate(duration, target_mb=18.0):
    """按目标体积反推总码率(kbps)，留 8% 余量；约束在 800~6000 kbps。"""
    if duration <= 0:
        return 2500
    total_kbit = target_mb * 8 * 1024 / duration * 0.92
    audio = 128
    v = total_kbit - audio
    return int(max(800, min(6000, v)))


def build_html(items, title):
    if not items:
        return ''
    cards = []
    for it in items:
        cards.append(f'''      <div class="ai-video">
        <video class="ai-v" controls preload="metadata" playsinline poster="{it['poster']}">
          <source src="{it['src']}" type="video/mp4">
          你的浏览器不支持内嵌视频，请 <a href="{it['src']}" target="_blank">直接观看 ↗</a>
        </video>
        <div class="ai-v-t">{html.escape(it['title'])}</div>
        <div class="ai-v-d">{html.escape(it['note'])}</div>
      </div>''')

    return f'''  <h2>{html.escape(title)}<span class="en">AIGC FILMS</span></h2>
  <p class="sec-note">即梦 / 可灵 / Coze 生成素材 + 实拍，进 Pr / Ae 完成剪辑。点击即可在页内播放。</p>
  <div class="ai-video-grid">
{chr(10).join(cards)}
  </div>
'''


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    title = 'AIGC 短片'
    if '--title' in sys.argv:
        i = sys.argv.index('--title')
        if i + 1 < len(sys.argv):
            title = sys.argv[i + 1]
    if not args:
        raise SystemExit('用法: python tools/build-aigc-videos.py <素材目录> [--title "AIGC 短片"]')

    src_dir = args[0]
    if not os.path.isdir(src_dir):
        raise SystemExit(f'[ERR] 素材目录不存在: {src_dir}')

    ff = find_ffmpeg()
    print(f'[OK] ffmpeg: {ff}')
    os.makedirs(WORKS, exist_ok=True)

    files = []
    for f in sorted(os.listdir(src_dir)):
        if f.lower().endswith(VIDEO_EXT) and not f.startswith('.'):
            files.append(f)
    if not files:
        raise SystemExit(f'[ERR] 目录里没有视频文件: {src_dir}')

    items = []
    for f in files:
        src = os.path.join(src_dir, f)
        slug = slugify(f)
        dst = os.path.join(WORKS, slug + '.mp4')
        poster = os.path.join(WORKS, slug + '.jpg')
        dur = probe_duration(ff, src)
        br = calc_bitrate(dur)
        print(f'  -> {f}  ({dur:.1f}s, 视频码率 {br}k)')

        cmd = [ff, '-y', '-i', src,
               '-vf', "scale='min(1280,iw)':-2:flags=lanczos,format=yuv420p",
               '-c:v', 'libx264', '-preset', 'medium', '-b:v', f'{br}k',
               '-maxrate', f'{int(br*1.5)}k', '-bufsize', f'{int(br*2)}k',
               '-c:a', 'aac', '-b:a', '128k', '-ac', '2',
               '-movflags', '+faststart', dst]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='ignore')
        if r.returncode != 0:
            print(f'  [WARN] 转码失败，跳过: {f}\n{r.stderr[-500:]}')
            continue

        subprocess.run([ff, '-y', '-ss', '1', '-i', dst, '-frames:v', '1',
                        '-q:v', '3', poster],
                       capture_output=True, text=True, encoding='utf-8', errors='ignore')

        size_mb = os.path.getsize(dst) / 1024 / 1024
        print(f'     {slug}.mp4  {size_mb:.1f} MB')
        items.append({
            'src': f'works/{slug}.mp4',
            'poster': f'works/{slug}.jpg',
            'title': os.path.splitext(f)[0],
            'note': f'{dur:.0f} 秒 · {size_mb:.1f} MB',
        })

    if not items:
        raise SystemExit('[ERR] 没有成功转码的视频')

    html_block = build_html(items, title)

    with open(INDEX, encoding='utf-8') as fh:
        content = fh.read()

    if MARK_START in content and MARK_END in content:
        new = re.sub(re.escape(MARK_START) + r'.*?' + re.escape(MARK_END),
                     MARK_START + '\n' + html_block + '  ' + MARK_END,
                     content, flags=re.S)
    else:
        anchor = '  <h2>AIGC 工作流'
        idx = content.find(anchor)
        if idx == -1:
            raise SystemExit('[ERR] index.html 里找不到注入锚点（AIGC 工作流 或 标记）')
        new = (content[:idx] + MARK_START + '\n' + html_block + '  ' + MARK_END + '\n\n'
               + content[idx:])

    with open(INDEX, 'w', encoding='utf-8') as fh:
        fh.write(new)

    print(f'[OK] 已嵌入 {len(items)} 个视频到 index.html')


if __name__ == '__main__':
    main()
