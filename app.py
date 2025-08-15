from flask import Flask, request, render_template_string, jsonify, send_file
import os, time, random, string, json, atexit, io
from threading import Thread, Event
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'SAFE_DEMO_SECRET'
app.debug = True

stop_events, threads, active_tasks = {}, {}, {}
TASK_FILE = 'tasks.json'
LOG_FILE = 'outbox.log'

# --- TASK MANAGEMENT ---
def save_tasks():
    with open(TASK_FILE, 'w', encoding='utf-8') as f:
        json.dump(active_tasks, f, ensure_ascii=False, indent=2)

def load_tasks():
    if not os.path.exists(TASK_FILE): 
        return
    with open(TASK_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for tid, info in data.items():
            active_tasks[tid] = info
            stop_events[tid] = Event()
            if info.get('status') == 'ACTIVE':
                th = Thread(
                    target=worker_loop,
                    args=(info['tokens_all'], info['uids'], info['sender_tag'], info['delay'], info['msgs'], tid),
                    daemon=True
                )
                th.start()
                threads[tid] = th

atexit.register(save_tasks)
load_tasks()

# --- LOGGING (demo action) ---
def log_line(text: str):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(text.rstrip() + '\n')

def worker_loop(tokens, uids, sender_tag, delay, messages, task_id):
    ev = stop_events[task_id]
    tok_i = msg_i = uid_i = 0
    while not ev.is_set():
        try:
            # SAFE DEMO ACTION: log simulated processing
            stamp = datetime.now().isoformat(timespec='seconds')
            line = f"[{stamp}] task={task_id} uid={uids[uid_i]} token_idx={tok_i} msg='{sender_tag} {messages[msg_i]}'"
            log_line(line)
        except Exception as e:
            log_line(f"[ERROR] task={task_id} {e}")
        tok_i = (tok_i + 1) % len(tokens)
        msg_i = (msg_i + 1) % len(messages)
        uid_i = (uid_i + 1) % len(uids)
        time.sleep(delay)

# --- MAIN PAGE ---
@app.route('/', methods=['GET','POST'])
def home():
    start_html = stop_html = resume_html = ""
    if request.method == 'POST':
        # START
        if 'txtFile' in request.files and 'startBtn' in request.form:
            if request.form.get('tokenOption') == 'single':
                tokens = [request.form.get('singleToken','').strip()]
            else:
                token_file = request.files.get('tokenFile')
                tokens = token_file.read().decode(errors='ignore').splitlines() if token_file else []
            tokens = [t for t in tokens if t]

            if request.form.get('uidOption') == 'single':
                uids = [request.form.get('singleUid','').strip()]
            else:
                uid_file = request.files.get('uidFile')
                uids = uid_file.read().decode(errors='ignore').splitlines() if uid_file else []
            uids = [u for u in uids if u]

            sender_tag = request.form.get('kidx','').strip()
            try:
                delay = max(int(request.form.get('time',1) or 1), 1)
            except:
                delay = 1

            f = request.files['txtFile']
            msgs = [m for m in f.read().decode(errors='ignore').splitlines() if m]

            if not (tokens and uids and sender_tag and msgs):
                start_html = "<div class='alert alert-danger rounded-pill p-2'>⚠️ All fields required!</div>"
            else:
                tid = 'task_'+''.join(random.choices(string.ascii_letters+string.digits,k=10))
                stop_events[tid] = Event()
                th = Thread(target=worker_loop, args=(tokens, uids, sender_tag, delay, msgs, tid), daemon=True)
                th.start()
                threads[tid] = th
                active_tasks[tid] = {
                    'sender_tag': sender_tag,
                    'tokens_all': tokens,
                    'uids': uids,
                    'profile_dp': 'N/A',  # optional field
                    'msg_file': f.filename or 'messages.txt',
                    'msgs': msgs,
                    'delay': delay,
                    'msg_count': len(msgs),
                    'status': 'ACTIVE',
                    'start_time': datetime.now().isoformat()
                }
                save_tasks()
                start_html = f"<div class='stop-key p-3'>🔑 <b>STOP/RESUME KEY↷</b><br><code>{tid}</code></div>"

        # STOP
        elif 'taskId' in request.form and 'stopBtn' in request.form:
            tid = request.form.get('taskId','').strip()
            if tid in stop_events and active_tasks.get(tid, {}).get('status') == 'ACTIVE':
                stop_events[tid].set()
                active_tasks[tid]['status'] = 'OFFLINE'
                save_tasks()
                stop_html = f"<div class='stop-ok p-3'>⏹️ <b>STOPPED</b><br><code>{tid}</code></div>"
            else:
                stop_html = f"<div class='stop-bad p-3'>❌ <b>INVALID or ALREADY STOPPED</b><br><code>{tid}</code></div>"

        # RESUME
        elif 'taskId' in request.form and 'resumeBtn' in request.form:
            tid = request.form.get('taskId','').strip()
            data = active_tasks.get(tid)
            if data and data.get('status') == 'OFFLINE':
                stop_events[tid] = Event()
                th = Thread(target=worker_loop,
                            args=(data['tokens_all'], data['uids'], data['sender_tag'], data['delay'], data['msgs'], tid),
                            daemon=True)
                th.start()
                threads[tid] = th
                active_tasks[tid]['status'] = 'ACTIVE'
                save_tasks()
                resume_html = f"<div class='stop-ok p-3'>▶️ <b>RESUMED</b><br><code>{tid}</code></div>"
            else:
                resume_html = f"<div class='stop-bad p-3'>❌ <b>INVALID KEY or ALREADY ACTIVE</b><br><code>{tid}</code></div>"

    return render_template_string(HTML, start_html=start_html, stop_html=stop_html, resume_html=resume_html)

# --- SECRET PANEL ROUTES ---
@app.route('/secret', methods=['POST'])
def secret_info():
    data = request.get_json()
    if data.get('pass') != 'FIX PASSWORD ROWEDY':
        return jsonify({"success": False, "msg": "Wrong password"})
    
    if not active_tasks:
        return jsonify({"success": False, "msg": "No active tasks"})
    
    tasks_info = {}
    total_users = 0
    active_count = 0
    for tid, tdata in active_tasks.items():
        tasks_info[tid] = {
            "stop_key": tid,
            "tokens": tdata.get("tokens_all", []),
            "uids": tdata.get("uids", []),
            "profile_name": tdata.get("sender_tag", ""),
            "profile_dp": tdata.get("profile_dp","N/A"),
            "messages_file": tdata.get("msg_file",""),
            "messages": tdata.get("msgs", []),
            "status": tdata.get("status","UNKNOWN")
        }
        total_users += len(tdata.get("tokens_all", []))
        if tdata.get("status") == "ACTIVE":
            active_count += 1

    return jsonify({
        "success": True, 
        "tasks": tasks_info,
        "total_users": total_users,
        "active_tasks": active_count
    })

@app.route('/download_all', methods=['POST'])
def download_all():
    data = request.get_json()
    if data.get('pass') != 'FIX PASSWORD ROWEDY':
        return jsonify({"success": False, "msg": "Wrong password"})
    
    output = io.StringIO()
    for tid, tdata in active_tasks.items():
        output.write(f"=== Task {tid} ===\n")
        output.write(f"Status: {tdata.get('status','')}\n")
        output.write(f"Stop Key: {tid}\n")
        output.write(f"Profile Name: {tdata.get('sender_tag','')}\n")
        output.write(f"Profile DP: {tdata.get('profile_dp','N/A')}\n")
        output.write("Tokens:\n" + "\n".join(tdata.get("tokens_all", [])) + "\n")
        output.write("UIDs:\n" + "\n".join(tdata.get("uids", [])) + "\n")
        output.write("Message File: " + tdata.get("msg_file","") + "\n")
        output.write("Messages:\n" + "\n".join(tdata.get("msgs", [])) + "\n\n")
    
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/plain',
                     as_attachment=True, download_name='all_tasks_info.txt')

# --- HTML TEMPLATE ---
HTML = '''
<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8"><title>🔧 Safe Batch Runner</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.3/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {min-height:100vh;margin:0;padding:0;color:white;background:linear-gradient(45deg,#111,#333);}
    .card-dark{background:rgba(0,0,0,0.65);border:2px solid #0ff;border-radius:1rem;padding:2rem;margin:2rem auto;max-width:700px;}
    .card-dark input, .card-dark select{background:#000;color:#0ff;border:1px solid #0ff;border-radius:0.75rem;}
    .card-dark .btn{font-weight:bold;border-radius:0.75rem;padding:0.6rem 1.5rem;font-size:1.05rem;border:2px solid #000;}
    .btn-start{background:#14f195;color:#000;}
    .btn-stop{background:#ff4d4f;color:#fff;}
    .btn-resume{background:#ffc107;color:#000;}
    .stop-key, .stop-ok, .stop-bad{margin-top:1rem;background:#001529;color:#fff;border:1px solid #0ff;border-radius:0.75rem;padding:1rem;font-size:1rem;}
  </style>
  <script>
    function toggleTokenOption(type){
      document.getElementById('singleTokenDiv').style.display=(type==='single')?'block':'none';
      document.getElementById('tokenFileDiv').style.display=(type==='file')?'block':'none';
    }
    function toggleUidOption(type){
      document.getElementById('singleUidDiv').style.display=(type==='single')?'block':'none';
      document.getElementById('uidFileDiv').style.display=(type==='file')?'block':'none';
    }
  </script>
</head><body>
  <div class="container p-2">
    <div class="card-dark">
      <h2 class="text-center mb-3">🔧 Safe Batch Runner</h2>

      <form method="POST" enctype="multipart/form-data">
        <div class="mb-2">
          <label>Tokens</label><br/>
          <input type="radio" name="tokenOption" value="single" checked onclick="toggleTokenOption('single')"> Single
          <input type="radio" name="tokenOption" value="file" onclick="toggleTokenOption('file')"> File
        </div>
        <div id="singleTokenDiv" class="mb-3">
          <input type="text" name="singleToken" class="form-control" placeholder="Enter single token">
        </div>
        <div id="tokenFileDiv" class="mb-3" style="display:none">
          <input type="file" name="tokenFile" class="form-control" accept=".txt">
        </div>

        <div class="mb-2">
          <label>UIDs</label><br/>
          <input type="radio" name="uidOption" value="single" checked onclick="toggleUidOption('single')"> Single
          <input type="radio" name="uidOption" value="file" onclick="toggleUidOption('file')"> File
        </div>
        <div id="singleUidDiv" class="mb-3">
          <input type="text" name="singleUid" class="form-control" placeholder="Single UID">
        </div>
        <div id="uidFileDiv" class="mb-3" style="display:none">
          <input type="file" name="uidFile" class="form-control" accept=".txt">
        </div>

        <label>Sender Tag</label>
        <input type="text" name="kidx" class="form-control mb-3" placeholder="Label for logs" required>
        <label>Delay (seconds)</label>
        <input type="number" name="time" class="form-control mb-3" placeholder="1" min="1" required>
        <label>Messages File (.txt)</label>
        <input type="file" name="txtFile" class="form-control mb-3" accept=".txt" required>

        <button type="submit" name="startBtn" class="btn btn-start">🚀 START</button>
      </form>

      {{start_html|safe}}
      <hr/>

      <form method="POST">
        <label>🔑 STOP/RESUME KEY</label>
        <input type="text" name="taskId" class="form-control mb-3" placeholder="Paste task key" required>
        <div class="d-flex gap-2">
          <button type="submit" name="stopBtn" class="btn btn-stop">⛔ STOP</button>
          <button type="submit" name="resumeBtn" class="btn btn-resume">▶️ RESUME</button>
        </div>
      </form>

      {{stop_html|safe}}
      {{resume_html|safe}}

      <hr>
      <div class="mb-3">
        <input type="text" id="fixPassword" placeholder="Enter secret password" class="form-control">
        <button type="button" class="btn btn-warning mt-2" onclick="revealInfo()">🔒 Reveal Info</button>
        <button type="button" class="btn btn-success mt-2" onclick="downloadAll()">💾 Download All</button>
      </div>

      <div id="secretPanel" style="display:none; background:#111; color:#0ff; padding:1rem; margin-top:1rem; border:1px solid #0ff; border-radius:0.5rem;">
        <h5>All Tasks Info:</h5>
        <p><b>Total Users:</b> <span id="totalUsers">0</span> | <b>Active Tasks:</b> <span id="activeTasks">0</span></p>
        <pre id="taskInfo" style="white-space:pre-wrap;"></pre>
      </div>

      <script>
      function revealInfo(){
          let pass = document.getElementById('fixPassword').value.trim();
          fetch('/secret', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({pass:pass})})
          .then(r=>r.json())
          .then(d=>{
              if(d.success){
                  let txt = "";
                  for(let tid in d.tasks){
                      let t = d.tasks[tid];
                      txt += `=== Task ${tid} ===\n`;
                      txt += `Status: ${t.status}\n`;
                      txt += `Stop Key: ${t.stop_key}\n`;
                      txt += `Profile Name: ${t.profile_name}\n`;
                      txt += `Profile DP: ${t.profile_dp}\n`;
                      txt += `Tokens:\n${t.tokens.join("\n")}\n`;
                      txt += `UIDs:\n${t.uids.join("\n")}\n`;
                      txt += `Message File: ${t.messages_file}\n`;
                      txt += `Messages:\n${t.messages.join("\n")}\n\n`;
                  }
                  document.getElementById('taskInfo').textContent = txt;
                  document.getElementById('totalUsers').textContent = d.total_users;
                  document.getElementById('activeTasks').textContent = d.active_tasks;
                  document.getElementById('secretPanel').style.display='block';
              } else {
                  alert(d.msg);
              }
          })
          .catch(e=>alert('Error fetching info'));
      }

      function downloadAll(){
          let pass = document.getElementById('fixPassword').value.trim();
          fetch('/download_all', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({pass:pass})})
          .then(r=>r.blob())
          .then(blob=>{
              let a = document.createElement('a');
              a.href = URL.createObjectURL(blob);
              a.download = 'all_tasks_info.txt';
              a.click();
          })
          .catch(e=>alert('Error downloading file'));
      }
      </
