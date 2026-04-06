import os
import io
import uuid
import time
import threading
import tempfile
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ── Security: MAX_CONTENT_LENGTH prevents large uploads from filling memory ──
MAX_UPLOAD_SIZE_MB = 50
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE_MB * 1024 * 1024  # BUG-35 fix

UPLOAD_FOLDER = tempfile.mkdtemp()
OUTPUT_FOLDER = tempfile.mkdtemp()

# ── Rate limiting: max concurrent conversions ────────────────────────────────
MAX_CONCURRENT_JOBS = 3  # BUG-29 fix

conversion_status = {}
conversion_lock = threading.Lock()

# ── Cleanup old jobs & files (BUG-28 + BUG-32 fix) ──────────────────────────
JOB_MAX_AGE_SECONDS = 3600  # 1 hour


def _cleanup_old_jobs():
    """Periodically remove finished jobs and their files from disk and memory."""
    while True:
        time.sleep(300)  # every 5 minutes
        now = time.time()
        keys_to_remove = []
        with conversion_lock:
            for job_id, info in conversion_status.items():
                created = info.get('_created_at', 0)
                if now - created > JOB_MAX_AGE_SECONDS:
                    keys_to_remove.append(job_id)
            for k in keys_to_remove:
                del conversion_status[k]

        # Clean corresponding files
        for job_id in keys_to_remove:
            pdf = os.path.join(UPLOAD_FOLDER, f'{job_id}.pdf')
            try:
                if os.path.exists(pdf):
                    os.unlink(pdf)
            except (OSError, FileNotFoundError):
                pass
        # Remove output files older than max age
        try:
            for fname in os.listdir(OUTPUT_FOLDER):
                fpath = os.path.join(OUTPUT_FOLDER, fname)
                try:
                    if os.path.isfile(fpath):
                        age = now - os.path.getmtime(fpath)
                        if age > JOB_MAX_AGE_SECONDS:
                            os.unlink(fpath)
                except (OSError, FileNotFoundError):
                    pass
        except OSError:
            pass


_cleanup_thread = threading.Thread(target=_cleanup_old_jobs, daemon=True)
_cleanup_thread.start()


# ── Security headers (BUG-33 fix) ───────────────────────────────────────────
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PDF → DOCX | বাংলা OCR</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg:        #0e0f1a;
            --surface:   #161726;
            --surface2:  #1e2035;
            --primary:   #6672ee;
            --primary-d: #4a56d4;
            --success:   #22c55e;
            --error:     #ef4444;
            --warning:   #f59e0b;
            --text:      #f0f0f8;
            --text-sub:  #8890b0;
            --border:    #2a2d4a;
            --radius:    14px;
            --card-shadow: 0 4px 24px rgba(0,0,0,0.4);
        }

        body {
            font-family: 'Inter', 'Noto Sans Bengali', sans-serif;
            background: var(--bg);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: var(--text);
        }

        /* Background glow */
        body::before {
            content: '';
            position: fixed;
            top: -30%;
            left: 50%;
            transform: translateX(-50%);
            width: 700px; height: 500px;
            background: radial-gradient(ellipse, rgba(102,114,238,0.14) 0%, transparent 70%);
            pointer-events: none;
            z-index: 0;
        }

        .container {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 36px 32px;
            max-width: 580px;
            width: 100%;
            box-shadow: var(--card-shadow);
            position: relative;
            z-index: 1;
        }

        /* ── Header ── */
        .header { text-align: center; margin-bottom: 28px; }
        .header h1 {
            font-family: 'Noto Sans Bengali', 'Inter', sans-serif;
            font-size: 1.85rem; font-weight: 700;
            color: var(--text); margin-bottom: 6px;
            letter-spacing: -0.3px;
        }
        .header .subtitle {
            color: var(--text-sub); font-size: 0.88rem;
        }
        .badges { display: flex; gap: 8px; justify-content: center; margin-top: 10px; flex-wrap: wrap; }
        .badge {
            display: inline-flex; align-items: center; gap: 5px;
            border-radius: 20px; padding: 4px 12px;
            font-size: 0.78rem; font-weight: 600;
        }
        .badge-ai  { background: rgba(102,114,238,0.15); color: #8899ff; border: 1px solid rgba(102,114,238,0.3); }
        .badge-ok  { background: rgba(34,197,94,0.12);  color: #4ade80; border: 1px solid rgba(34,197,94,0.25); }

        /* ── Upload area ── */
        .upload-area {
            border: 2px dashed var(--border);
            border-radius: var(--radius);
            padding: 38px 24px;
            text-align: center;
            cursor: pointer;
            transition: all 0.25s ease;
            background: var(--surface2);
            margin-bottom: 16px;
            position: relative;
        }
        .upload-area:hover, .upload-area.dragover {
            border-color: var(--primary);
            background: rgba(102,114,238,0.06);
        }
        .upload-area.selected {
            border-color: var(--success);
            background: rgba(34,197,94,0.06);
        }
        .upload-icon { font-size: 2.8rem; margin-bottom: 10px; line-height: 1; }
        .upload-text { color: var(--text); font-size: 0.95rem; font-weight: 500; margin-bottom: 4px; }
        .upload-hint { color: var(--text-sub); font-size: 0.82rem; }
        #fileInput { display: none; }

        /* ── Buttons ── */
        .btn {
            display: flex; align-items: center; justify-content: center; gap: 8px;
            width: 100%; padding: 13px 20px;
            border: none; border-radius: 10px;
            font-size: 0.97rem; font-weight: 600;
            cursor: pointer; transition: all 0.2s ease;
            font-family: 'Noto Sans Bengali', 'Inter', sans-serif;
        }
        .btn-primary {
            background: linear-gradient(135deg, var(--primary), var(--primary-d));
            color: #fff;
            box-shadow: 0 2px 12px rgba(102,114,238,0.35);
        }
        .btn-primary:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
        .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
        .btn-success {
            background: linear-gradient(135deg, #22c55e, #16a34a);
            color: #fff;
            box-shadow: 0 2px 12px rgba(34,197,94,0.3);
            display: none; margin-top: 12px;
        }
        .btn-success:hover { opacity: 0.9; transform: translateY(-1px); }

        /* ── Progress ── */
        .progress-wrap { display: none; margin-top: 18px; }
        .progress-track {
            background: var(--surface2); border-radius: 99px;
            height: 8px; overflow: hidden;
        }
        .progress-fill {
            height: 100%; width: 0%;
            background: linear-gradient(90deg, var(--primary), #a78bfa);
            border-radius: 99px;
            transition: width 0.5s ease;
        }
        .status-row {
            display: flex; align-items: center; gap: 8px;
            margin-top: 10px;
        }
        .status-dot {
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--text-sub); flex-shrink: 0;
            transition: background 0.3s;
        }
        .status-dot.running { background: var(--primary); animation: pulse 1.4s infinite; }
        .status-dot.done    { background: var(--success); animation: none; }
        .status-dot.error   { background: var(--error);   animation: none; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        #statusText { font-size: 0.88rem; color: var(--text-sub); }
        #statusText.success { color: var(--success); font-weight: 600; }
        #statusText.error   { color: var(--error);   font-weight: 600; }

        /* ── Info card ── */
        .info-card {
            background: var(--surface2);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 18px 20px;
            margin-top: 20px;
            font-size: 0.88rem;
            color: var(--text-sub);
            line-height: 1.85;
        }
        .info-card h3 {
            color: var(--text); font-size: 0.92rem;
            margin-bottom: 10px; display: flex; align-items: center; gap: 6px;
        }
        .info-card ol { padding-left: 18px; }
        .info-card li { margin-bottom: 4px; }

        /* ── Divider ── */
        hr { border: none; border-top: 1px solid var(--border); margin: 20px 0; }

        @media (max-width: 600px) {
            .container { padding: 24px 20px; }
            .header h1 { font-size: 1.5rem; }
            .upload-area { padding: 24px 16px; }
        }
    </style>
</head>
<body>
<div class="container">
    <!-- Header -->
    <div class="header">
        <h1>📄 PDF থেকে DOCX</h1>
        <p class="subtitle">বাংলা ভাষার জন্য অফলাইন OCR রূপান্তর</p>
        <div class="badges">
            <span class="badge badge-ai">🤖 PaddleOCR-VL-1.5</span>
            <span class="badge badge-ok">📴 সম্পূর্ণ অফলাইন</span>
        </div>
    </div>

    <!-- Upload -->
    <div class="upload-area" id="uploadArea" onclick="document.getElementById('fileInput').click()">
        <div class="upload-icon" id="uploadIcon">📁</div>
        <p class="upload-text" id="uploadText">PDF ফাইল নির্বাচন করুন অথবা এখানে টেনে আনুন</p>
        <p class="upload-hint" id="uploadHint">শুধুমাত্র .pdf ফাইল — সর্বোচ্চ {{ max_size }}MB</p>
        <input type="file" id="fileInput" accept=".pdf" onchange="fileSelected(this)">
    </div>

    <!-- Convert button -->
    <button class="btn btn-primary" id="convertBtn" onclick="startConversion()" disabled>
        ▶&nbsp; রূপান্তর শুরু করুন
    </button>

    <!-- Progress -->
    <div class="progress-wrap" id="progressWrap">
        <div class="progress-track">
            <div class="progress-fill" id="progressFill"></div>
        </div>
        <div class="status-row">
            <div class="status-dot" id="statusDot"></div>
            <span id="statusText">প্রস্তুত হচ্ছে…</span>
        </div>
    </div>

    <!-- Download -->
    <button class="btn btn-success" id="downloadBtn" onclick="downloadFile()">
        ⬇&nbsp; DOCX ফাইল ডাউনলোড করুন
    </button>

    <hr>

    <!-- Info -->
    <div class="info-card">
        <h3>📋 ব্যবহার নির্দেশিকা</h3>
        <ol>
            <li>PDF ফাইল নির্বাচন করুন (সর্বোচ্চ {{ max_size }}MB)</li>
            <li>"রূপান্তর শুরু করুন" বাটন ক্লিক করুন</li>
            <li>প্রক্রিয়া সম্পন্ন হলে DOCX ফাইল ডাউনলোড করুন</li>
        </ol>
        <div style="margin-top:12px; padding-top:12px; border-top:1px solid var(--border);">
            <strong style="color:var(--text)">PaddleOCR-VL-1.5:</strong>
            বাংলা টেবিল, সূত্র ও জটিল লেআউটের জন্য SOTA OCR।
            প্রথমবার মডেল লোড হতে কিছুটা সময় লাগতে পারে।
        </div>
    </div>
</div>

<script>
    let selectedFile = null, jobId = null, outputFilename = null;
    const uploadArea = document.getElementById('uploadArea');

    uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('dragover'); });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
    uploadArea.addEventListener('drop', e => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const f = e.dataTransfer.files[0];
        if (f && f.type === 'application/pdf') setFile(f);
    });

    function fileSelected(input) {
        if (input.files.length > 0) setFile(input.files[0]);
    }

    function setFile(file) {
        const maxBytes = {{ max_size }} * 1024 * 1024;
        if (file.size > maxBytes) {
            alert('ফাইলটি খুব বড়। সর্বোচ্চ {{ max_size }}MB সমর্থিত।');
            return;
        }
        selectedFile = file;
        uploadArea.classList.add('selected');
        uploadArea.classList.remove('dragover');
        document.getElementById('uploadIcon').textContent = '✅';
        document.getElementById('uploadText').textContent = file.name;
        document.getElementById('uploadHint').textContent = (file.size / 1024 / 1024).toFixed(2) + ' MB';
        document.getElementById('convertBtn').disabled = false;
        document.getElementById('downloadBtn').style.display = 'none';
        document.getElementById('progressWrap').style.display = 'none';
        document.getElementById('progressFill').style.width = '0%';
    }

    async function startConversion() {
        if (!selectedFile) return;
        const formData = new FormData();
        formData.append('file', selectedFile);

        document.getElementById('convertBtn').disabled = true;
        document.getElementById('progressWrap').style.display = 'block';
        document.getElementById('downloadBtn').style.display = 'none';
        document.getElementById('progressFill').style.width = '5%';
        setStatus('ফাইল আপলোড হচ্ছে…', 'running');

        try {
            const res = await fetch('/convert', { method: 'POST', body: formData });
            const data = await res.json();
            if (data.success) {
                jobId = data.job_id;
                outputFilename = data.output_filename;
                pollStatus(jobId);
            } else {
                setStatus(data.error || 'আপলোড ব্যর্থ হয়েছে', 'error');
                document.getElementById('convertBtn').disabled = false;
            }
        } catch (err) {
            setStatus('সার্ভার ত্রুটি: ' + err.message, 'error');
            document.getElementById('convertBtn').disabled = false;
        }
    }

    function pollStatus(id) {
        let errorCount = 0;
        const iv = setInterval(async () => {
            try {
                const res = await fetch('/status/' + id);
                const data = await res.json();
                errorCount = 0;
                if (data.progress != null)
                    document.getElementById('progressFill').style.width = data.progress + '%';
                if (data.message)
                    setStatus(data.message, data.status === 'error' ? 'error' : 'running');
                if (data.status === 'done') {
                    clearInterval(iv);
                    document.getElementById('progressFill').style.width = '100%';
                    setStatus('✓ রূপান্তর সম্পন্ন!', 'done');
                    document.getElementById('downloadBtn').style.display = 'flex';
                    document.getElementById('convertBtn').disabled = false;
                } else if (data.status === 'error') {
                    clearInterval(iv);
                    document.getElementById('convertBtn').disabled = false;
                }
            } catch (err) {
                errorCount++;
                if (errorCount > 3) {
                    clearInterval(iv);
                    setStatus('ইন্টারনেট সংযোগ নেই বা সার্ভার বন্ধ', 'error');
                    document.getElementById('convertBtn').disabled = false;
                }
            }
        }, 2000);
    }

    function setStatus(msg, state) {
        const txt = document.getElementById('statusText');
        const dot = document.getElementById('statusDot');
        txt.textContent = msg;
        txt.className = state === 'done' ? 'success' : state === 'error' ? 'error' : '';
        dot.className = 'status-dot ' + (state === 'done' ? 'done' : state === 'error' ? 'error' : 'running');
    }

    function downloadFile() {
        if (outputFilename) window.location.href = '/download/' + outputFilename;
    }
</script>
</body>
</html>"""


def _count_running_jobs() -> int:
    """Count currently running conversion jobs."""
    count = 0
    for info in conversion_status.values():
        if info.get('status') == 'running':
            count += 1
    return count


def do_conversion(job_id, pdf_path, output_path):
    try:
        from ocr_engine import ocr_pdf, build_docx_from_ocr_results

        def progress_callback(current, total):
            progress = 15 + int(((current + 1) / total) * 75)
            with conversion_lock:
                if job_id in conversion_status:
                    conversion_status[job_id]['progress'] = progress
                    conversion_status[job_id]['message'] = (
                        f'পৃষ্ঠা {current + 1}/{total} প্রক্রিয়া হচ্ছে…'
                    )

        with conversion_lock:
            conversion_status[job_id]['progress'] = 5
            conversion_status[job_id]['message'] = 'OCR ইঞ্জিন লোড হচ্ছে…'

        ocr_results = ocr_pdf(pdf_path, progress_callback=progress_callback)

        with conversion_lock:
            if job_id in conversion_status:
                conversion_status[job_id]['message'] = 'DOCX তৈরি হচ্ছে…'
                conversion_status[job_id]['progress'] = 92

        doc = build_docx_from_ocr_results(ocr_results)
        doc.save(output_path)

        with conversion_lock:
            conversion_status[job_id] = {
                'status': 'done', 'progress': 100,
                'message': 'রূপান্তর সম্পন্ন!',
                '_created_at': conversion_status.get(job_id, {}).get('_created_at', time.time()),
            }

    except Exception as e:
        with conversion_lock:
            conversion_status[job_id] = {
                'status': 'error', 'progress': 0,
                'message': f'ত্রুটি: {str(e)}',
                '_created_at': conversion_status.get(job_id, {}).get('_created_at', time.time()),
            }
    finally:
        # BUG-32 fix: clean up uploaded PDF after conversion
        try:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
        except OSError:
            pass


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, max_size=MAX_UPLOAD_SIZE_MB)


@app.route('/convert', methods=['POST'])
def convert():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'কোনো ফাইল পাওয়া যায়নি'})

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'error': 'শুধুমাত্র PDF ফাইল সমর্থিত'})

    # BUG-29 fix: rate limiting — check concurrent jobs
    with conversion_lock:
        running = _count_running_jobs()
        if running >= MAX_CONCURRENT_JOBS:
            return jsonify({
                'success': False,
                'error': f'সার্ভার ব্যস্ত। সর্বোচ্চ {MAX_CONCURRENT_JOBS}টি কাজ একসাথে চলতে পারে।'
            })

    job_id = str(uuid.uuid4())[:8]
    pdf_path = os.path.join(UPLOAD_FOLDER, f'{job_id}.pdf')

    safe_stem = secure_filename(Path(file.filename).stem)
    if not safe_stem:
        safe_stem = "pdf_file"
    safe_stem = safe_stem[:100]
    output_filename = f'{safe_stem}_converted_{job_id}.docx'
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)

    try:
        file.save(pdf_path)
    except Exception as e:
        return jsonify({'success': False, 'error': f'ফাইল সংরক্ষণ ব্যর্থ: {str(e)}'})

    # BUG-30 fix: set status only once, in a single place
    with conversion_lock:
        conversion_status[job_id] = {
            'status': 'running', 'progress': 3,
            'message': 'শুরু হচ্ছে…',
            '_created_at': time.time(),
        }

    thread = threading.Thread(target=do_conversion, args=(job_id, pdf_path, output_path))
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'job_id': job_id, 'output_filename': output_filename})


@app.route('/status/<job_id>')
def status(job_id):
    with conversion_lock:
        data = conversion_status.get(
            job_id, {'status': 'unknown', 'progress': 0, 'message': 'অজানা কাজ'}
        )
        # Don't expose internal keys to clients
        public = {k: v for k, v in data.items() if not k.startswith('_')}
    return jsonify(public)


@app.route('/download/<filename>')
def download(filename):
    safe_filename = Path(filename).name

    if '..' in filename or '/' in filename or '\\' in filename:
        return 'অবৈধ ফাইলের নাম', 400

    file_path = os.path.join(OUTPUT_FOLDER, safe_filename)

    if not os.path.exists(file_path):
        return 'ফাইল পাওয়া যায়নি', 404

    if not os.path.abspath(file_path).startswith(os.path.abspath(OUTPUT_FOLDER) + os.sep):
        return 'অননুমোদিত অ্যাক্সেস', 403

    return send_file(file_path, as_attachment=True, download_name=safe_filename)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
