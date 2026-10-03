import os
import json
import re
import subprocess
import psutil
import socket
import sys
import hashlib
import secrets
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

ADMIN_USERNAME = "AAAAAA"
ADMIN_PASSWORD = "AAAAAA"

# ============== دوال مساعدة لإنشاء القوالب تلقائياً ==============
def create_default_templates():
    login_html = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول</title>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">
    <style>body { font-family: 'Cairo', sans-serif; }</style>
</head>
<body class="bg-gray-950 text-gray-100 flex items-center justify-center min-h-screen">
    <div class="bg-gray-900 border border-gray-800 p-8 rounded-2xl shadow-2xl w-full max-w-md">
        <div class="text-center mb-8">
            <h1 class="text-3xl font-bold text-blue-500">لوحة التحكم</h1>
            <p class="text-gray-400 text-sm mt-2">قم بتسجيل الدخول للمتابعة</p>
        </div>
        <div id="alert" class="hidden mb-4 p-3 rounded-lg text-sm"></div>
        <form id="loginForm" class="space-y-5">
            <div>
                <label class="block text-sm font-medium mb-2">اسم المستخدم</label>
                <input type="text" id="username" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500">
            </div>
            <div>
                <label class="block text-sm font-medium mb-2">كلمة المرور</label>
                <input type="password" id="password" required class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500">
            </div>
            <div class="flex items-center justify-between text-sm">
                <label class="flex items-center cursor-pointer">
                    <input type="checkbox" id="remember_me" class="rounded bg-gray-800 border-gray-700 text-blue-500 focus:ring-0 w-4 h-4 ml-2">
                    تذكرني
                </label>
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 transition font-bold py-3 rounded-lg shadow-lg">دخول</button>
        </form>
    </div>
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const remember_me = document.getElementById('remember_me').checked;
            const alertBox = document.getElementById('alert');
            
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password, remember_me})
            });
            const data = await res.json();
            alertBox.classList.remove('hidden');
            if(data.success) {
                alertBox.className = "mb-4 p-3 rounded-lg text-sm bg-green-900/50 border border-green-700 text-green-300";
                alertBox.textContent = data.message;
                setTimeout(() => window.location.href = '/', 1000);
            } else {
                alertBox.className = "mb-4 p-3 rounded-lg text-sm bg-red-900/50 border border-red-700 text-red-300";
                alertBox.textContent = data.message;
            }
        });
    </script>
</body>
</html>"""

    index_html = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة إدارة السيرفرات</title>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">
    <style>body { font-family: 'Cairo', sans-serif; }</style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen flex flex-col">
    <header class="bg-gray-900 border-b border-gray-800 px-6 py-4 flex justify-between items-center">
        <h1 class="text-xl font-bold text-blue-500">إدارة السيرفرات</h1>
        <div class="flex items-center gap-4">
            <span id="currentUser" class="text-sm text-gray-300"></span>
            <button onclick="logout()" class="bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white px-4 py-2 rounded-lg text-sm transition">تسجيل الخروج</button>
        </div>
    </header>
    <main class="flex-1 container mx-auto p-6 grid grid-cols-1 md:grid-cols-4 gap-6">
        <div class="bg-gray-900 border border-gray-800 p-4 rounded-xl flex flex-col">
            <h2 class="text-lg font-bold mb-4">السيرفرات</h2>
            <div id="serversList" class="space-y-2 flex-1 overflow-y-auto mb-4"></div>
            <button onclick="openAddServerModal()" class="w-full bg-blue-600 hover:bg-blue-700 py-2 rounded-lg text-sm font-bold transition">إضافة سيرفر جديد</button>
        </div>
        <div id="serverDetails" class="md:col-span-3 bg-gray-900 border border-gray-800 p-6 rounded-xl flex flex-col hidden">
            <div class="flex justify-between items-center mb-6 border-b border-gray-800 pb-4">
                <div>
                    <h2 id="serverTitle" class="text-2xl font-bold"></h2>
                    <p id="serverStatus" class="text-sm text-gray-400 mt-1"></p>
                </div>
                <div class="flex gap-2">
                    <button onclick="controlServer('start')" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded-lg text-sm">تشغيل</button>
                    <button onclick="controlServer('restart')" class="bg-yellow-600 hover:bg-yellow-700 px-4 py-2 rounded-lg text-sm">إعادة تشغيل</button>
                    <button onclick="controlServer('stop')" class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg text-sm">إيقاف</button>
                </div>
            </div>
            <div class="grid grid-cols-3 gap-4 mb-6">
                <div class="bg-gray-800/50 p-4 rounded-lg border border-gray-700/50">
                    <span class="text-xs text-gray-400">استهلاك المعالج</span>
                    <p id="cpuStat" class="text-xl font-bold mt-1">0%</p>
                </div>
                <div class="bg-gray-800/50 p-4 rounded-lg border border-gray-700/50">
                    <span class="text-xs text-gray-400">استهلاك الذاكرة</span>
                    <p id="memStat" class="text-xl font-bold mt-1">0 MB</p>
                </div>
                <div class="bg-gray-800/50 p-4 rounded-lg border border-gray-700/50">
                    <span class="text-xs text-gray-400">عنوان IP</span>
                    <p id="ipStat" class="text-xl font-bold mt-1">-</p>
                </div>
            </div>
            <div class="flex gap-4 border-b border-gray-800 mb-4">
                <button onclick="switchTab('console')" id="tabConsoleBtn" class="pb-2 border-b-2 border-blue-500 font-bold text-sm">وحدة التحكم</button>
                <button onclick="switchTab('files')" id="tabFilesBtn" class="pb-2 border-b-2 border-transparent text-gray-400 font-bold text-sm">الملفات</button>
            </div>
            <div id="tabConsole" class="flex-1 flex flex-col">
                <pre id="logsBox" class="bg-black/50 border border-gray-800 p-4 rounded-lg flex-1 font-mono text-xs overflow-y-auto h-96 text-green-400 whitespace-pre-wrap"></pre>
            </div>
            <div id="tabFiles" class="hidden flex-1 flex flex-col">
                <div class="flex justify-between mb-4">
                    <input type="file" id="fileUploadInput" multiple class="hidden" onchange="uploadFiles(this)">
                    <button onclick="document.getElementById('fileUploadInput').click()" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm">رفع ملفات</button>
                    <button onclick="installRequirements()" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg text-sm">تثبيت متطلبات (pip)</button>
                </div>
                <div class="flex-1 bg-black/30 border border-gray-800 rounded-lg overflow-hidden flex flex-col">
                    <div id="filesList" class="divide-y divide-gray-800 overflow-y-auto flex-1"></div>
                </div>
            </div>
        </div>
    </main>

    <!-- Modal Add Server -->
    <div id="addServerModal" class="fixed inset-0 bg-black/70 flex items-center justify-center hidden">
        <div class="bg-gray-900 border border-gray-800 p-6 rounded-xl w-full max-w-md">
            <h3 class="text-lg font-bold mb-4">إضافة سيرفر جديد</h3>
            <input type="text" id="newServerName" placeholder="اسم السيرفر..." class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 mb-4 focus:outline-none focus:border-blue-500">
            <div class="flex justify-end gap-3">
                <button onclick="closeAddServerModal()" class="bg-gray-800 hover:bg-gray-700 px-4 py-2 rounded-lg text-sm">إلغاء</button>
                <button onclick="createServer()" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm">إنشاء</button>
            </div>
        </div>
    </div>

    <!-- Modal Edit File -->
    <div id="editFileModal" class="fixed inset-0 bg-black/70 flex items-center justify-center hidden">
        <div class="bg-gray-900 border border-gray-800 p-6 rounded-xl w-full max-w-4xl h-[80vh] flex flex-col">
            <h3 id="editingFileName" class="text-lg font-bold mb-4"></h3>
            <textarea id="fileContentEditor" class="flex-1 bg-black/50 border border-gray-800 p-4 rounded-lg font-mono text-sm text-gray-200 focus:outline-none resize-none mb-4"></textarea>
            <div class="flex justify-end gap-3">
                <button onclick="closeEditModal()" class="bg-gray-800 hover:bg-gray-700 px-4 py-2 rounded-lg text-sm">إلغاء</button>
                <button onclick="saveFileContent()" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm">حفظ التغييرات</button>
            </div>
        </div>
    </div>

    <script>
        let currentFolder = null;
        let currentEditingFile = null;
        let statsInterval = null;

        async function init() {
            const res = await fetch('/api/current_user');
            const data = await res.json();
            if(!data.success) { window.location.href = '/login'; return; }
            if(data.is_admin) { window.location.href = '/'; return; }
            document.getElementById('currentUser').textContent = data.username;
            loadServers();
        }

        async function loadServers() {
            const res = await fetch('/servers');
            const data = await res.json();
            const list = document.getElementById('serversList');
            list.innerHTML = '';
            if(data.success && data.servers.length > 0) {
                data.servers.forEach(s => {
                    const div = document.createElement('div');
                    div.className = `p-3 rounded-lg cursor-pointer transition border ${currentFolder === s.folder ? 'bg-blue-600/20 border-blue-500' : 'bg-gray-800/40 border-gray-800 hover:bg-gray-800'}`;
                    div.innerHTML = `<div class="font-bold">${s.title}</div><div class="text-xs text-gray-400 mt-1">${s.subtitle}</div>`;
                    div.onclick = () => selectServer(s.folder, s.title);
                    list.appendChild(div);
                });
            } else {
                list.innerHTML = '<p class="text-gray-500 text-sm text-center py-4">لا توجد سيرفرات</p>';
            }
        }

        function selectServer(folder, title) {
            currentFolder = folder;
            document.getElementById('serverDetails').classList.remove('hidden');
            document.getElementById('serverTitle').textContent = title;
            loadServers();
            fetchStats();
            loadFiles();
            if(statsInterval) clearInterval(statsInterval);
            statsInterval = setInterval(fetchStats, 3000);
        }

        async function fetchStats() {
            if(!currentFolder) return;
            const res = await fetch(`/server/stats/${currentFolder}`);
            const data = await res.json();
            document.getElementById('serverStatus').textContent = data.status;
            document.getElementById('cpuStat').textContent = data.cpu;
            document.getElementById('memStat').textContent = data.mem;
            document.getElementById('ipStat').textContent = data.ip;
            document.getElementById('logsBox').textContent = data.logs;
        }

        async function controlServer(action) {
            if(!currentFolder) return;
            const res = await fetch(`/server/action/${currentFolder}/${action}`, {method: 'POST'});
            const data = await res.json();
            fetchStats();
        }

        async function loadFiles() {
            if(!currentFolder) return;
            const res = await fetch(`/files/list/${currentFolder}`);
            const files = await res.json();
            const list = document.getElementById('filesList');
            list.innerHTML = '';
            files.forEach(f => {
                const div = document.createElement('div');
                div.className = "flex items-center justify-between p-3 hover:bg-gray-800/50";
                div.innerHTML = `
                    <div class="flex items-center gap-3">
                        <span>${f.icon}</span>
                        <span class="text-sm font-medium">${f.name}</span>
                        <span class="text-xs text-gray-500">${f.size}</span>
                    </div>
                    <div class="flex gap-2">
                        <button onclick="editFile('${f.name}')" class="bg-gray-800 hover:bg-gray-700 px-3 py-1 rounded text-xs">تعديل</button>
                        <button onclick="setStartup('${f.name}')" class="bg-purple-600/20 hover:bg-purple-600 text-purple-300 hover:text-white px-3 py-1 rounded text-xs">تعيين كتشغيل</button>
                        <button onclick="deleteFile('${f.name}')" class="bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white px-3 py-1 rounded text-xs">حذف</button>
                    </div>
                `;
                list.appendChild(div);
            });
        }

        async function uploadFiles(input) {
            if(!currentFolder || !input.files.length) return;
            const formData = new FormData();
            for(let file of input.files) formData.append('files[]', file);
            await fetch(`/files/upload/${currentFolder}`, {method: 'POST', body: formData});
            input.value = '';
            loadFiles();
        }

        async function editFile(filename) {
            currentEditingFile = filename;
            document.getElementById('editingFileName').textContent = filename;
            const res = await fetch(`/files/content/${currentFolder}/${filename}`);
            const data = await res.json();
            document.getElementById('fileContentEditor').value = data.content;
            document.getElementById('editFileModal').classList.remove('hidden');
        }

        async function saveFileContent() {
            const content = document.getElementById('fileContentEditor').value;
            await fetch(`/files/save/${currentFolder}/${currentEditingFile}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({content})
            });
            closeEditModal();
        }

        async function deleteFile(filename) {
            if(!confirm('هل أنت متأكد من الحذف؟')) return;
            await fetch(`/files/delete/${currentFolder}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: filename})
            });
            loadFiles();
        }

        async function setStartup(filename) {
            await fetch(`/server/set-startup/${currentFolder}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({file: filename})
            });
            alert('تم تعيين ملف التشغيل بنجاح');
        }

        async function installRequirements() {
            alert('بدء تثبيت المتطلبات، تابع السجل لمعرفة النتيجة.');
            await fetch(`/files/install/${currentFolder}`, {method: 'POST'});
        }

        function switchTab(tab) {
            if(tab === 'console') {
                document.getElementById('tabConsole').classList.remove('hidden');
                document.getElementById('tabFiles').classList.add('hidden');
                document.getElementById('tabConsoleBtn').className = "pb-2 border-b-2 border-blue-500 font-bold text-sm";
                document.getElementById('tabFilesBtn').className = "pb-2 border-b-2 border-transparent text-gray-400 font-bold text-sm";
            } else {
                document.getElementById('tabConsole').classList.add('hidden');
                document.getElementById('tabFiles').classList.remove('hidden');
                document.getElementById('tabFilesBtn').className = "pb-2 border-b-2 border-blue-500 font-bold text-sm";
                document.getElementById('tabConsoleBtn').className = "pb-2 border-b-2 border-transparent text-gray-400 font-bold text-sm";
            }
        }

        function openAddServerModal() { document.getElementById('addServerModal').classList.remove('hidden'); }
        function closeAddServerModal() { document.getElementById('addServerModal').classList.add('hidden'); }
        function closeEditModal() { document.getElementById('editFileModal').classList.add('hidden'); }

        async function createServer() {
            const name = document.getElementById('newServerName').value;
            if(!name) return;
            const res = await fetch('/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name})
            });
            const data = await res.json();
            if(data.success) {
                closeAddServerModal();
                document.getElementById('newServerName').value = '';
                loadServers();
            } else {
                alert(data.message);
            }
        }

        async function logout() {
            await fetch('/api/logout', {method: 'POST'});
            window.location.href = '/login';
        }

        init();
    </script>
</body>
</html>"""

    admin_panel_html = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة تحكم المسؤول</title>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">
    <style>body { font-family: 'Cairo', sans-serif; }</style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen flex flex-col">
    <header class="bg-gray-900 border-b border-gray-800 px-6 py-4 flex justify-between items-center">
        <h1 class="text-xl font-bold text-blue-500">لوحة تحكم المسؤول (Admin)</h1>
        <button onclick="logout()" class="bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white px-4 py-2 rounded-lg text-sm transition">تسجيل الخروج</button>
    </header>
    <main class="flex-1 container mx-auto p-6 max-w-4xl">
        <div class="bg-gray-900 border border-gray-800 p-6 rounded-xl mb-6">
            <h2 class="text-lg font-bold mb-4">إنشاء مستخدم جديد</h2>
            <form id="createUserForm" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <input type="text" id="newUsername" placeholder="اسم المستخدم" required class="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500">
                <input type="password" id="newPassword" placeholder="كلمة المرور" required class="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500">
                <button type="submit" class="bg-blue-600 hover:bg-blue-700 font-bold py-3 rounded-lg transition">إضافة مستخدم</button>
            </form>
        </div>
        <div class="bg-gray-900 border border-gray-800 p-6 rounded-xl">
            <h2 class="text-lg font-bold mb-4">المستخدمون المسجلون</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-right border-collapse">
                    <thead>
                        <tr class="border-b border-gray-800 text-gray-400 text-sm">
                            <th class="py-3 px-4">اسم المستخدم</th>
                            <th class="py-3 px-4">تاريخ الإنشاء</th>
                            <th class="py-3 px-4">آخر دخول</th>
                            <th class="py-3 px-4">الإجراءات</th>
                        </tr>
                    </thead>
                    <tbody id="usersTableBody" class="divide-y divide-gray-800 text-sm"></tbody>
                </table>
            </div>
        </div>
    </main>
    <script>
        async function init() {
            const res = await fetch('/api/current_user');
            const data = await res.json();
            if(!data.success || !data.is_admin) { window.location.href = '/login'; return; }
            loadUsers();
        }

        async function loadUsers() {
            const res = await fetch('/api/admin/users');
            const data = await res.json();
            const tbody = document.getElementById('usersTableBody');
            tbody.innerHTML = '';
            if(data.success) {
                data.users.forEach(u => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td class="py-3 px-4 font-bold">${u.username}</td>
                        <td class="py-3 px-4 text-gray-400">${u.created_at ? new Date(u.created_at).toLocaleString() : '-'}</td>
                        <td class="py-3 px-4 text-gray-400">${u.last_login ? new Date(u.last_login).toLocaleString() : 'لم يسجل دخول بعد'}</td>
                        <td class="py-3 px-4">
                            <button onclick="deleteUser('${u.username}')" class="bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white px-3 py-1 rounded text-xs transition">حذف</button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        }

        document.getElementById('createUserForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('newUsername').value;
            const password = document.getElementById('newPassword').value;
            const res = await fetch('/api/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });
            const data = await res.json();
            alert(data.message);
            if(data.success) {
                document.getElementById('newUsername').value = '';
                document.getElementById('newPassword').value = '';
                loadUsers();
            }
        });

        async function deleteUser(username) {
            if(!confirm(`هل أنت متأكد من حذف المستخدم ${username}؟`)) return;
            const res = await fetch('/api/admin/delete-user', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username})
            });
            const data = await res.json();
            alert(data.message);
            loadUsers();
        }

        async function logout() {
            await fetch('/api/logout', {method: 'POST'});
            window.location.href = '/login';
        }

        init();
    </script>
</body>
</html>"""

    if not os.path.exists(os.path.join(BASE_DIR, "login.html")):
        with open(os.path.join(BASE_DIR, "login.html"), "w", encoding="utf-8") as f:
            f.write(login_html)
    if not os.path.exists(os.path.join(BASE_DIR, "index.html")):
        with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
            f.write(index_html)
    if not os.path.exists(os.path.join(BASE_DIR, "admin_panel.html")):
        with open(os.path.join(BASE_DIR, "admin_panel.html"), "w", encoding="utf-8") as f:
            f.write(admin_panel_html)

create_default_templates()

# ============== دوال النظام والقواعد ==============

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

def init_tokens_db():
    if not os.path.exists(REMEMBER_TOKENS_FILE):
        with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_remember_token(username):
    init_tokens_db()
    with open(REMEMBER_TOKENS_FILE, "r", encoding="utf-8") as f:
        tokens = json.load(f)
    
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
    
    with open(REMEMBER_TOKENS_FILE, "r", encoding="utf-8") as f:
        tokens = json.load(f)
    
    if token not in tokens:
        return None
    
    token_data = tokens[token]
    expires_at = datetime.fromisoformat(token_data["expires_at"])
    
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
    
    with open(REMEMBER_TOKENS_FILE, "r", encoding="utf-8") as f:
        tokens = json.load(f)
    
    tokens_to_delete = [token for token, data in tokens.items() if data["username"] == username]
    for token in tokens_to_delete:
        del tokens[token]
    
    with open(REMEMBER_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)

def register_user(username, password, created_by_admin=False):
    init_users_db()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    
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
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    
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
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    
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
    
    folder = sanitize_folder_name(folder)
    server_path = os.path.join(user_servers_dir, folder)
    os.makedirs(server_path, exist_ok=True)
    
    meta_path = os.path.join(server_path, "meta.json")
    if not os.path.exists(meta_path):
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"display_name": folder, "startup_file": ""}, f)
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

# ============== المسارات (Routes) ==============

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
    
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"success": False, "message": "اسم المستخدم وكلمة المرور مطلوبان"})
    
    success, message = register_user(username, password, created_by_admin=True)
    return jsonify({"success": success, "message": message})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    remember_me = data.get("remember_me", False)
    
    if not username or not password:
        return jsonify({"success": False, "message": "اسم المستخدم وكلمة المرور مطلوبان"})
    
    success, message = authenticate_user(username, password)
    if success:
        session['username'] = username
        
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
                secure=False,
                samesite='Strict'
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
    target = os.path.abspath(os.path.join(user_servers_dir, folder))
    
    if not target.startswith(os.path.abspath(user_servers_dir)):
        return jsonify({"success": False, "message": "مسار غير صالح"}), 400
    
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
    server_path = os.path.abspath(os.path.join(user_servers_dir, folder))
    
    if not server_path.startswith(os.path.abspath(user_servers_dir)):
        return jsonify({"success": False, "message": "مسار غير صالح"}), 400
        
    log_path = os.path.join(server_path, "server.log")
    
    if act == "stop":
        if proc_key in running_procs:
            try:
                p = psutil.Process(running_procs[proc_key].pid)
                for child in p.children(recursive=True):
                    child.terminate()
                p.terminate()
                p.wait(timeout=3)
                
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
                p.wait(timeout=3)
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
    
    startup_file = ""
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            startup_file = meta.get("startup_file", "")
    except:
        pass
    
    if not startup_file:
        return jsonify({"success": False, "message": "لم يتم تعيين ملف التشغيل"})
    
    startup_path = os.path.abspath(os.path.join(server_path, startup_file))
    if not startup_path.startswith(os.path.abspath(server_path)) or not os.path.exists(startup_path):
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
    p = os.path.abspath(os.path.join(user_servers_dir, folder))
    
    if not p.startswith(os.path.abspath(user_servers_dir)):
        return jsonify([]), 403
        
    files = []
    if os.path.exists(p):
        for f in os.listdir(p):
            if f in ["meta.json", "server.log"]:
                continue
            f_path = os.path.join(p, f)
            if os.path.isfile(f_path):
                size = os.path.getsize(f_path)
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
    file_path = os.path.abspath(os.path.join(user_servers_dir, folder, filename))
    
    if not file_path.startswith(os.path.abspath(user_servers_dir)):
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
    file_path = os.path.abspath(os.path.join(user_servers_dir, folder, filename))
    
    if not file_path.startswith(os.path.abspath(user_servers_dir)):
        return jsonify({"success": False}), 403
    
    data = request.get_json() or {}
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data.get('content', ''))
        return jsonify({"success": True})
    except:
        return jsonify({"success": False})

@app.route("/files/upload/<folder>", methods=["POST"])
def upload_file(folder):
    if 'username' not in session:
        return jsonify({"success": False}), 401
    
    folder = sanitize_folder_name(folder)
    user_servers_dir = ensure_user_servers_dir()
    target_dir = os.path.abspath(os.path.join(user_servers_dir, folder))
    
    if not target_dir.startswith(os.path.abspath(user_servers_dir)):
        return jsonify({"success": False}), 403
        
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
            
            results.append({
                "name": safe_name,
                "size": f"{os.path.getsize(save_path) / 1024:.2f} KB"
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
    data = request.get_json() or {}
    filename = sanitize_filename(data.get('name', ''))
    
    file_path = os.path.abspath(os.path.join(user_servers_dir, folder, filename))
    
    if not file_path.startswith(os.path.abspath(user_servers_dir)):
        return jsonify({"success": False}), 403
    
    try:
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            
            log_path = os.path.join(user_servers_dir, folder, "server.log")
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"\n[SYSTEM] تم حذف الملف: {filename} - {datetime.now().isoformat()}\n")
            
            return jsonify({"success": True})
    except:
        pass
    return jsonify({"success": False})

@app.route("/files/install/<folder>", methods=["POST"])
def install_req(folder):
    if 'username' not in session:
        return jsonify({"success": False}), 401
    
    folder = sanitize_folder_name(folder)
    user_servers_dir = ensure_user_servers_dir()
    server_path = os.path.abspath(os.path.join(user_servers_dir, folder))
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
            universal_newlines=True
        )
        
        for line in process.stdout:
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(line)
        
        process.wait()
        
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"\n[SYSTEM] اكتمل التثبيت - {datetime.now().isoformat()}\n")
        
        return jsonify({"success": True, "message": "تم التثبيت"})
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
    
    data = request.get_json() or {}
    startup_file = sanitize_filename(data.get('file', ''))
    
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            m = json.load(f)
        m["startup_file"] = startup_file
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2)
        return jsonify({"success": True})
    except:
        return jsonify({"success": False})

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
    
    data = request.get_json() or {}
    username_to_delete = data.get("username", "").strip()
    
    if not username_to_delete or username_to_delete == ADMIN_USERNAME:
        return jsonify({"success": False, "message": "لا يمكن حذف هذا المستخدم"})
    
    init_users_db()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
    
    if username_to_delete not in users:
        return jsonify({"success": False, "message": "المستخدم غير موجود"})
    
    for key, proc in list(running_procs.items()):
        if key.startswith(f"{username_to_delete}_"):
            try:
                p = psutil.Process(proc.pid)
                p.terminate()
            except:
                pass
            del running_procs[key]
    
    del users[username_to_delete]
    
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
    
    user_dir = os.path.join(USERS_DIR, username_to_delete)
    if os.path.exists(user_dir):
        try:
            import shutil
            shutil.rmtree(user_dir)
        except:
            pass
    
    delete_all_user_tokens(username_to_delete)
    
    return jsonify({"success": True, "message": "تم حذف المستخدم"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
