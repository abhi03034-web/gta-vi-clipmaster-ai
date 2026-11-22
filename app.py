import os, re, shutil, subprocess, tempfile, zipfile
from pathlib import Path
import gradio as gr

TITLE = 'GTA VI ClipMaster AI'
ROOT = Path('/tmp/clipmaster')
ROOT.mkdir(exist_ok=True)

def cmd(args):
 p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-1800:])
    return p.stdout

def duration(path):
    return float(cmd(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]).strip())

def transcribe(path):
    try:
        from faster_whisper import WhisperModel
 model = WhisperModel('tiny', device='cpu', compute_type='int8')
 segs, _ = model.transcribe(str(path), vad_filter=True)
        return [{'start':float(s.start),'end':float(s.end),'text':s.text.strip()} for s in segs if s.text.strip()]
    except Exception:
        return []

def score(text):
 keys = ['wow','no way','oh my god',"let's go",'crazy','insane','amazing','wait','bro','holy','explosion','police','wanted','chase','crash','fight','mission','secret','funny','fail','clutch']
 t = text.lower()
    return sum(2 for k in keys if k in t) + min(len(t.split())/18, 2)

def esc(s):
    return s.replace('\\','\\\\').replace(':','\\:').replace("'","\\'").replace('%','\\%').replace(',','\\,')

def render(src, out, start, length, captions, vertical):
 vf = ['scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920' if vertical else 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2']
    for a,b,text in captions:
 vf.append("drawtext=font='DejaVuSans-Bold':text='"+esc(text[:85])+"':fontcolor=white:borderw=3:bordercolor=black:fontsize=42:x=(w-text_w)/2:y=h*0.78:enable='between(t,"+f'{a:.2f}'+','+f'{b:.2f}'+")'")
    cmd(['ffmpeg','-y','-ss',str(start),'-i',str(src),'-t',str(length),'-vf',','.join(vf),'-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-b:a','128k','-movflags','+faststart',str(out)])

def process(upload, count, minlen, maxlen, layout, progress=gr.Progress()):
    if not upload:
        raise gr.Error('Upload your own gameplay video (MP4 recommended).')
 src = Path(upload)
 work = Path(tempfile.mkdtemp(prefix='job_', dir=str(ROOT)))
    try:
        progress(0.08, desc='Reading video…')
 total = duration(src)
        if total &lt; minlen:
            raise gr.Error('Video is shorter than the minimum clip length.')
        progress(0.18, desc='Finding exciting moments…')
 transcript = transcribe(src)
 options = []
        if transcript:
 step = max(8, int(minlen/2))
 t = 0
            while t + minlen &lt;= total:
 end = min(total, t + maxlen)
 words = ' '.join(s['text'] for s in transcript if s['start'] &lt; end and s['end'] &gt; t)
                if len(words.split()) &gt;= 4:
 options.append((score(words),t,end,words))
                t += step
        if not options:
 step = max(minlen, int(total/max(int(count),1)))
 t = 0
            while t + minlen &lt;= total and len(options) &lt; int(count)*3:
 options.append((0,t,min(total,t+maxlen),''))
                t += step
 options.sort(key=lambda x:x[0], reverse=True)
 chosen=[]
        for item in options:
            if all(abs(item[1]-old[1]) &gt; minlen*.65 for old in chosen):
 chosen.append(item)
            if len(chosen)&gt;=int(count): break
        if not chosen: raise gr.Error('No suitable segments found.')
 outputs=[]
        for i,(_,start,end,_) in enumerate(chosen,1):
            progress(.25+.68*i/len(chosen), desc=f'Rendering clip {i}/{len(chosen)}…')
 caps=[]
            for s in transcript:
 a=max(s['start'],start)-start; b=min(s['end'],end)-start
                if b&gt;a: caps.append((a,b,s['text']))
 out=work/f'GTA_Clip_{i:02d}.mp4'
            render(src,out,start,end-start,caps,layout=='9:16 Vertical')
 outputs.append(str(out))
 archive=work/'GTA_VI_Clips.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in outputs: z.write(p,Path(p).name)
        progress(1, desc='Finished!')
 ote='Captions added from speech recognition.' if transcript else 'Speech was not detected; clips were selected at spaced intervals without captions.'
        return outputs,str(archive),note
    except gr.Error: raise
    except Exception as e: raise gr.Error(str(e))

css = '.gradio-container{max-width:950px!important;margin:auto!important} #hero{text-align:center;padding:22px;border-radius:18px;background:linear-gradient(120deg,#101827,#17406a)} #hero h1{color:white} #hero p{color:#dbeafe}'
with gr.Blocks(title=TITLE,theme=gr.themes.Soft(primary_hue='blue'),css=css) as app:
 gr.HTML('&lt;div id="hero"&gt;&lt;h1&gt;🎮 GTA VI ClipMaster AI&lt;/h1&gt;&lt;p&gt;Long gameplay → short MP4 clips&lt;/p&gt;&lt;/div&gt;')
 gr.Markdown('Upload a gameplay video you own or have permission to edit. The app automatically selects moments, crops to vertical or landscape, adds speech captions when possible, and exports real MP4 files.')
    with gr.Row():
        with gr.Column():
 video=gr.File(label='Upload gameplay video',file_types=['.mp4','.mov','.mkv','.webm'],type='filepath')
 =gr.Slider(1,5,value=3,step=1,label='Number of clips')
            with gr.Row():
 low=gr.Slider(15,30,value=20,step=1,label='Minimum seconds')
 high=gr.Slider(25,60,value=35,step=5,label='Maximum seconds')
 layout=gr.Radio(['9:16 Vertical','16:9 Landscape'],value='9:16 Vertical',label='Format')
 button=gr.Button('⚡ Generate MP4 Clips',variant='primary')
        with gr.Column():
 files=gr.Files(label='Your MP4 clips')
 bundle=gr.File(label='Download all clips')
 status=gr.Textbox(label='Status',lines=3,interactive=False)
 button.click(process,[video,n,low,high,layout],[files,bundle,status])
 gr.Markdown('**Free hosting note:** Free CPU spaces may sleep and can be slow. Automatic selection is a best-effort estimate; review clips before publishing.')
app.queue(max_size=3).launch()
