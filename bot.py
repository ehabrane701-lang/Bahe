import os
import json
import re
import subprocess
import psutil
import socket
import sys
import hashlib
import secrets
import time
import signal
import shutil
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, request, jsonify, session, redirect, url_for, make_response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "USERS")
os.makedirs(USERS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=BASE_DIR)
app.secret_key = secrets.token_hex(32)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

running_procs = {}
USERS_FILE = os.path.join(BASE_DIR, "users.json")
REMEMBER_TOKENS_FILE = os.path.join(BASE_DIR, "remember_tokens.json")

# الحساب الرئيسي
ADMIN_USERNAME = "AAAAAA"
ADMIN_PASSWORD = "AAAAAA"

# ============== دوال المساعدة ==============

def init_users_db():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            admin_data = {
                ADMIN_USERNAME: {
                    "password": hash_password(ADMIN_PASSWORD),
                    "created_at": datetime.now().isoformat(),
                    "last_login": None,
                    "theme": "premium",
                    "is_admin": True,
                    "can_create_users": True
                }
            }
            json.dump(admin_data, f, indent=2)
    else:
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                json.load(f)
        except (json.JSONDecodeError, Exception):
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                admin_data = {
                    ADMIN_USERNAME: {
                        "password": hash_password(ADMIN_PASSWORD),
                        "created_at": datetime.now().isoformat(),
                        "last_login": None,
                        "theme": "premium",
                        "is_admin": True,
                        "can_create_users": True
                    }
                }
                json.dump(admin_data, f, indent=2)

def init_tokens_db():
    if not os.path.exists(REMEMBER_TOKENS_FILE):
        with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    else:
        try:
            with open(REMEMBER_TOKENS_FILE, "r", encoding="utf-8") as f:
                json.load(f)
        except (json.JSONDecodeError, Exception):
            with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

# تهيئة قواعد البيانات عند بدء التشغيل
init_users_db()
init_tokens_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_remember_token(username):
    init_tokens_db()
    try:
        with open(REMEMBER_TOKENS_FILE, "r", encoding="utf-8") as f:
            tokens = json.load(f)
    except:
        tokens = {}
    
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=30)).isoformat()
    
    tokens[token] = {
        "username": username,
        "created_at": datetime.now().isoformat(),
        "expires_at": expires,
        "last_used": datetime.now().isoformat()
    }
    
    with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    return token

def validate_remember_token(token):
    if not os.path.exists(REMEMBER_TOKENS_FILE):
        return None
    
    try:
        with open(REMEMBER_TOKENS_FILE, "r", encoding="utf-8") as f:
            tokens = json.load(f)
    except:
        return None
    
    if token not in tokens:
        return None
    
    token_data = tokens[token]
    try:
        expires_at = datetime.fromisoformat(token_data["expires_at"])
    except:
        del tokens[token]
        with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)
        return None
    
    if datetime.now() > expires_at:
        del tokens[token]
        with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)
        return None
    
    token_data["last_used"] = datetime.now().isoformat()
    tokens[token] = token_data
    
    with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    
    return token_data["username"]

def delete_all_user_tokens(username):
    if not os.path.exists(REMEMBER_TOKENS_FILE):
        return
    
    try:
        with open(REMEMBER_TOKENS_FILE, "r", encoding="utf-8") as f:
            tokens = json.load(f)
    except:
        return
    
    tokens_to_delete = [token for token, data in tokens.items() if data.get("username") == username]
    for token in tokens_to_delete:
        del tokens[token]
    
    with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)

def register_user(username, password, created_by_admin=False):
    init_users_db()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except:
        users = {}
    
    if username in users:
        return False, "المستخدم موجود بالفعل"
    
    if len(password) < 6:
        return False, "كلمة المرور يجب أن تكون 6 أحرف على الأقل"
    
    users[username] = {
        "password": hash_password(password),
        "created_at": datetime.now().isoformat(),
        "last_login": None,
        "theme": "blue",
        "is_admin": False,
        "created_by_admin": created_by_admin,
        "created_by": session.get('username') if 'username' in session else None
    }
    
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
    
    user_dir = os.path.join(USERS_DIR, username)
    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(os.path.join(user_dir, "SERVERS"), exist_ok=True)
    
    return True, "تم إنشاء الحساب بنجاح"

def authenticate_user(username, password):
    init_users_db()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except:
        users = {}
    
    if username not in users:
        return False, "المستخدم غير موجود"
    
    if users[username]["password"] != hash_password(password):
        return False, "كلمة المرور غير صحيحة"
    
    users[username]["last_login"] = datetime.now().isoformat()
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
    
    return True, "تم تسجيل الدخول بنجاح"

def is_admin(username):
    init_users_db()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except:
        users = {}
    
    if username in users:
        return users[username].get("is_admin", False)
    return False

def get_user_servers_dir(username):
    return os.path.join(USERS_DIR, username, "SERVERS")

def ensure_user_servers_dir():
    if 'username' not in session:
        return None
    user_dir = get_user_servers_dir(session['username'])
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def sanitize_folder_name(name):
    if not name: return ""
    name = name.strip()
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"[^A-Za-z0-9\-\_\.]", "", name)
    return name[:200]

def sanitize_filename(name):
    if not name: return ""
    name = name.strip()
    name = re.sub(r"[^A-Za-z0-9\-\_\.]", "", name)
    return name[:200]

def ensure_meta(folder):
    user_servers_dir = ensure_user_servers_dir()
    if not user_servers_dir:
        return None
    
    server_folder_path = os.path.join(user_servers_dir, folder)
    os.makedirs(server_folder_path, exist_ok=True)
    
    meta_path = os.path.join(server_folder_path, "meta.json")
    if not os.path.exists(meta_path):
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"display_name": folder, "startup_file": ""}, f, indent=2)
    return meta_path

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except: 
        return '127.0.0.1'

def is_server_running(folder):
    proc_key = f"{session.get('username')}_{folder}"
    proc = running_procs.get(proc_key)
    if proc and psutil.pid_exists(proc.pid):
        try:
            p = psutil.Process(proc.pid)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except:
            return False
    return False

def load_servers_list():
    if 'username' not in session:
        return []
    
    user_servers_dir = ensure_user_servers_dir()
    if not user_servers_dir or not os.path.exists(user_servers_dir):
        return []
    
    try:
        entries = [d for d in os.listdir(user_servers_dir) 
                  if os.path.isdir(os.path.join(user_servers_dir, d))]
    except: 
        entries = []
    
    servers = []
    for i, folder in enumerate(entries, start=1):
        ensure_meta(folder)
        meta_path = os.path.join(user_servers_dir, folder, "meta.json")
        display_name, startup_file = folder, ""
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                display_name = meta.get("display_name", folder)
                startup_file = meta.get("startup_file", "")
        except: 
            pass
        
        running = is_server_running(folder)
        
        servers.append({
            "id": i, 
            "title": display_name, 
            "folder": folder, 
            "subtitle": f"Node-{i} · {'🟢 شغال' if running else '🔴 واقف'}",
            "startup_file": startup_file,
            "status": "running" if running else "stopped"
        })
    return servers

# ============== المسارات ==============

@app.before_request
def check_remember_token():
    if 'username' in session:
        return
    
    remember_token = request.cookies.get('remember_token')
    if remember_token:
        username = validate_remember_token(remember_token)
        if username:
            session['username'] = username
            session.permanent = True

@app.route("/")
def home():
    if 'username' not in session:
        return redirect(url_for('login_page'))
    
    if is_admin(session['username']):
        return send_from_directory(BASE_DIR, "admin_panel.html")
    
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/login")
def login_page():
    if 'username' in session:
        return redirect(url_for('home'))
    return send_from_directory(BASE_DIR, "login.html")

@app.route("/api/register", methods=["POST"])
def api_register():
    if 'username' not in session or not is_admin(session['username']):
        return jsonify({"success": False, "message": "غير مصرح"}), 403
    
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"success": False, "message": "اسم المستخدم وكلمة المرور مطلوبان"})
    
    success, message = register_user(username, password, created_by_admin=True)
    return jsonify({"success": success, "message": message})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    remember_me = data.get("remember_me", False)
    
    if not username or not password:
        return jsonify({"success": False, "message": "اسم المستخدم وكلمة المرور مطلوبان"})
    
    success, message = authenticate_user(username, password)
    if success:
        session['username'] = username
        session.permanent = True
        
        response_data = {
            "success": True, 
            "message": message,
            "username": username,
            "is_admin": is_admin(username)
        }
        
        if remember_me:
            token = create_remember_token(username)
            response = make_response(jsonify(response_data))
            response.set_cookie(
                'remember_token',
                token,
                max_age=30*24*60*60,
                httponly=True,
                secure=request.is_secure,
                samesite='Lax'
            )
            return response
        
        return jsonify(response_data)
    
    return jsonify({"success": False, "message": message})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    username = session.get('username')
    
    if username:
        for key, proc in list(running_procs.items()):
            if key.startswith(f"{username}_"):
                try:
                    p = psutil.Process(proc.pid)
                    for child in p.children(recursive=True):
                        child.terminate()
                    p.terminate()
                    p.wait(timeout=3)
                except:
                    pass
                del running_procs[key]
        
        delete_all_user_tokens(username)
    
    session.pop('username', None)
    
    response = make_response(jsonify({"success": True, "message": "تم تسجيل الخروج"}))
    response.set_cookie('remember_token', '', expires=0)
    return response

@app.route("/api/current_user")
def api_current_user():
    if 'username' in session:
        return jsonify({
            "success": True, 
            "username": session['username'],
            "is_admin": is_admin(session['username']),
            "has_remember_token": bool(request.cookies.get('remember_token'))
        })
    return jsonify({"success": False})

@app.route("/servers")
def get_servers():
    if 'username' not in session:
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    return jsonify({"success": True, "servers": load_servers_list()})

@app.route("/add", methods=["POST"])
def add_server():
    if 'username' not in session:
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    folder = sanitize_folder_name(name)
    
    if not folder:
        return jsonify({"success": False, "message": "اسم السيرفر غير صالح"}), 400
    
    user_servers_dir = ensure_user_servers_dir()
    target = os.path.join(user_servers_dir, folder)
    
    if os.path.exists(target): 
        return jsonify({"success": False, "message": "السيرفر موجود بالفعل"}), 409
    
    os.makedirs(target, exist_ok=True)
    ensure_meta(folder)
    
    log_path = os.path.join(target, "server.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"[SYSTEM] تم إنشاء السيرفر: {name}\n")
        f.write(f"[SYSTEM] التاريخ: {datetime.now().isoformat()}\n")
        f.write("[SYSTEM] جاهز لاستقبال الملفات\n")
    
    return jsonify({"success": True, "servers": load_servers_list()})

@app.route("/server/stats/<folder>")
def get_stats(folder):
    if 'username' not in session:
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    
    folder = sanitize_folder_name(folder)
    proc_key = f"{session['username']}_{folder}"
    proc = running_procs.get(proc_key)
    running = False
    cpu, mem = "0%", "0 MB"
    
    if proc and psutil.pid_exists(proc.pid):
        try:
            p = psutil.Process(proc.pid)
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                running = True
                cpu = f"{p.cpu_percent(interval=0.1)}%"
                mem = f"{p.memory_info().rss / 1024 / 1024:.2f} MB"
        except:
            pass
    
    user_servers_dir = ensure_user_servers_dir()
    log_path = os.path.join(user_servers_dir, folder, "server.log")
    logs = ""
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                logs = f.read()
                if len(logs) > 50000:
                    logs = logs[-50000:] + "\n[SYSTEM] تم اقتطاع السجل...\n"
        except:
            logs = "[خطأ في قراءة السجل]"
    
    return jsonify({
        "status": "🟢 شغال" if running else "🔴 واقف",
        "cpu": cpu,
        "mem": mem,
        "logs": logs,
        "ip": get_ip()
    })

@app.route("/server/action/<folder>/<act>", methods=["POST"])
def server_action(folder, act):
    if 'username' not in session:
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    
    folder = sanitize_folder_name(folder)
    proc_key = f"{session['username']}_{folder}"
    user_servers_dir = ensure_user_servers_dir()
    server_path = os.path.join(user_servers_dir, folder)
    log_path = os.path.join(server_path, "server.log")
    
    if not os.path.exists(server_path):
        return jsonify({"success": False, "message": "السيرفر غير موجود"}), 404
    
    if act == "stop":
        if proc_key in running_procs:
            try:
                p = psutil.Process(running_procs[proc_key].pid)
                for child in p.children(recursive=True):
                    child.terminate()
                p.terminate()
                p.wait(timeout=5)
                
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n[SYSTEM] تم إيقاف السيرفر - {datetime.now().isoformat()}\n")
            except:
                pass
            finally:
                if proc_key in running_procs:
                    del running_procs[proc_key]
        return jsonify({"success": True, "message": "تم إيقاف السيرفر"})
    
    elif act == "restart":
        if proc_key in running_procs:
            try:
                p = psutil.Process(running_procs[proc_key].pid)
                for child in p.children(recursive=True):
                    child.terminate()
                p.terminate()
                p.wait(timeout=5)
            except:
                pass
            finally:
                if proc_key in running_procs:
                    del running_procs[proc_key]
        
        return start_server(folder, server_path, log_path)
    
    elif act == "start":
        return start_server(folder, server_path, log_path)
    
    return jsonify({"success": False, "message": "إجراء غير معروف"})

def start_server(folder, server_path, log_path):
    proc_key = f"{session['username']}_{folder}"
    
    meta_path = os.path.join(server_path, "meta.json")
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            startup_file = meta.get("startup_file", "")
    except:
        startup_file = ""
    
    if not startup_file:
        return jsonify({"success": False, "message": "لم يتم تعيين ملف التشغيل"})
    
    startup_path = os.path.join(server_path, startup_file)
    if not os.path.exists(startup_path):
        return jsonify({"success": False, "message": f"الملف {startup_file} غير موجود"})
    
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"[SYSTEM] بدء التشغيل - {datetime.now().isoformat()}\n")
        f.write(f"[SYSTEM] الملف: {startup_file}\n")
        f.write(f"{'='*50}\n\n")
    
    try:
        log_file = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-u", startup_file],
            cwd=server_path,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )
        
        running_procs[proc_key] = proc
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[SYSTEM] تم التشغيل - PID: {proc.pid}\n")
        
        return jsonify({"success": True, "message": "تم بدء التشغيل", "pid": proc.pid})
    
    except Exception as e:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[ERROR] فشل التشغيل: {str(e)}\n")
        return jsonify({"success": False, "message": f"فشل التشغيل: {str(e)}"})

@app.route("/files/list/<folder>")
def list_files(folder):
    if 'username' not in session:
        return jsonify([]), 401
    
    folder = sanitize_folder_name(folder)
    user_servers_dir = ensure_user_servers_dir()
    p = os.path.join(user_servers_dir, folder)
    files = []
    if os.path.exists(p):
        for f in os.listdir(p):
            if f in ["meta.json", "server.log"]:
                continue
            f_path = os.path.join(p, f)
            if os.path.isfile(f_path):
                try:
                    size = os.path.getsize(f_path)
                except:
                    size = 0
                
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.2f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.2f} MB"
                
                ext = f.split('.')[-1] if '.' in f else ''
                icon = "📄"
                if ext == 'py': icon = "🐍"
                elif ext in ['txt', 'md']: icon = "📝"
                elif ext == 'json': icon = "🔧"
                elif ext in ['html', 'css', 'js']: icon = "🌐"
                
                files.append({"name": f, "size": size_str, "icon": icon})
    
    files.sort(key=lambda x: x['name'])
    return jsonify(files)

@app.route("/files/content/<folder>/<filename>")
def get_file_content(folder, filename):
    if 'username' not in session:
        return jsonify({"content": ""}), 401
    
    folder = sanitize_folder_name(folder)
    filename = sanitize_filename(filename)
    user_servers_dir = ensure_user_servers_dir()
    file_path = os.path.join(user_servers_dir, folder, filename)
    
    if not os.path.abspath(file_path).startswith(os.path.abspath(user_servers_dir)):
        return jsonify({"content": ""}), 403
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return jsonify({"content": f.read()})
    except:
        return jsonify({"content": "[لا يمكن قراءة الملف]"})

@app.route("/files/save/<folder>/<filename>", methods=["POST"])
def save_file_content(folder, filename):
    if 'username' not in session:
        return jsonify({"success": False}), 401
    
    folder = sanitize_folder_name(folder)
    filename = sanitize_filename(filename)
    user_servers_dir = ensure_user_servers_dir()
    file_path = os.path.join(user_servers_dir, folder, filename)
    
    if not os.path.abspath(file_path).startswith(os.path.abspath(user_servers_dir)):
        return jsonify({"success": False}), 403
    
    data = request.get_json(silent=True) or {}
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data.get('content', ''))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/files/upload/<folder>", methods=["POST"])
def upload_file(folder):
    if 'username' not in session:
        return jsonify({"success": False}), 401
    
    folder = sanitize_folder_name(folder)
    user_servers_dir = ensure_user_servers_dir()
    target_dir = os.path.join(user_servers_dir, folder)
    os.makedirs(target_dir, exist_ok=True)
    
    uploaded_files = request.files.getlist('files[]')
    results = []
    
    for f in uploaded_files:
        if f and f.filename:
            safe_name = sanitize_filename(f.filename)
            save_path = os.path.join(target_dir, safe_name)
            f.save(save_path)
            
            log_path = os.path.join(target_dir, "server.log")
            try:
                with open(log_path, "a", encoding="utf-8") as log:
                    log.write(f"\n[SYSTEM] تم رفع الملف: {safe_name} - {datetime.now().isoformat()}\n")
            except:
                pass
            
            try:
                size_kb = os.path.getsize(save_path) / 1024
            except:
                size_kb = 0
            
            results.append({
                "name": safe_name,
                "size": f"{size_kb:.2f} KB"
            })
    
    return jsonify({
        "success": True,
        "message": f"تم رفع {len(results)} ملف",
        "uploaded_files": results
    })

@app.route("/files/delete/<folder>", methods=["POST"])
def delete_file(folder):
    if 'username' not in session:
        return jsonify({"success": False}), 401
    
    folder = sanitize_folder_name(folder)
    user_servers_dir = ensure_user_servers_dir()
    data = request.get_json(silent=True) or {}
    filename = sanitize_filename(data.get('name', ''))
    
    if not filename:
        return jsonify({"success": False, "message": "اسم الملف غير صالح"})
    
    file_path = os.path.join(user_servers_dir, folder, filename)
    
    if not os.path.abspath(file_path).startswith(os.path.abspath(user_servers_dir)):
        return jsonify({"success": False}), 403
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            
            log_path = os.path.join(user_servers_dir, folder, "server.log")
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"\n[SYSTEM] تم حذف الملف: {filename} - {datetime.now().isoformat()}\n")
            
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "الملف غير موجود"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/files/install/<folder>", methods=["POST"])
def install_req(folder):
    if 'username' not in session:
        return jsonify({"success": False}), 401
    
    folder = sanitize_folder_name(folder)
    user_servers_dir = ensure_user_servers_dir()
    server_path = os.path.join(user_servers_dir, folder)
    req_path = os.path.join(server_path, "requirements.txt")
    
    if not os.path.exists(req_path):
        return jsonify({"success": False, "message": "requirements.txt غير موجود"})
    
    log_path = os.path.join(server_path, "server.log")
    
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"\n{'='*50}\n")
        log.write(f"[SYSTEM] بدء التثبيت - {datetime.now().isoformat()}\n")
        log.write(f"{'='*50}\n\n")
    
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=server_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        if process.stdout:
            for line in process.stdout:
                with open(log_path, "a", encoding="utf-8") as log:
                    log.write(line)
        
        process.wait()
        
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"\n[SYSTEM] اكتمل التثبيت - {datetime.now().isoformat()}\n")
        
        return jsonify({"success": True, "message": "تم التثبيت بنجاح"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/server/set-startup/<folder>", methods=["POST"])
def set_startup(folder):
    if 'username' not in session:
        return jsonify({"success": False}), 401
    
    folder = sanitize_folder_name(folder)
    meta_path = ensure_meta(folder)
    if not meta_path:
        return jsonify({"success": False}), 404
    
    data = request.get_json(silent=True) or {}
    startup_file = sanitize_filename(data.get('file', ''))
    
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            m = json.load(f)
        m["startup_file"] = startup_file
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/admin/users", methods=["GET"])
def get_all_users():
    if 'username' not in session or not is_admin(session['username']):
        return jsonify({"success": False}), 403
    
    init_users_db()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except:
        users = {}
    
    user_list = []
    for username, data in users.items():
        if username != ADMIN_USERNAME:
            user_list.append({
                "username": username,
                "created_at": data.get("created_at"),
                "last_login": data.get("last_login"),
                "created_by": data.get("created_by", "system")
            })
    
    return jsonify({"success": True, "users": user_list})

@app.route("/api/admin/delete-user", methods=["POST"])
def delete_user():
    if 'username' not in session or not is_admin(session['username']):
        return jsonify({"success": False}), 403
    
    data = request.get_json(silent=True) or {}
    username_to_delete = data.get("username", "").strip()
    
    if not username_to_delete or username_to_delete == ADMIN_USERNAME:
        return jsonify({"success": False, "message": "لا يمكن حذف هذا المستخدم"})
    
    init_users_db()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except:
        users = {}
    
    if username_to_delete not in users:
        return jsonify({"success": False, "message": "المستخدم غير موجود"})
    
    for key, proc in list(running_procs.items()):
        if key.startswith(f"{username_to_delete}_"):
            try:
                p = psutil.Process(proc.pid)
                for child in p.children(recursive=True):
                    child.terminate()
                p.terminate()
            except:
                pass
            del running_procs[key]
    
    if username_to_delete in users:
        del users[username_to_delete]
    
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
    
    user_dir = os.path.join(USERS_DIR, username_to_delete)
    if os.path.exists(user_dir):
        try:
            shutil.rmtree(user_dir)
        except:
            pass
    
    delete_all_user_tokens(username_to_delete)
    
    return jsonify({"success": True, "message": "تم حذف المستخدم بنجاح"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
