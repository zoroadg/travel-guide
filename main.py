from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import json
import os
from datetime import datetime, timedelta
from typing import Optional
import secrets

app = FastAPI(title="Travel Guide")

app.add_middleware(SessionMiddleware, secret_key=os.environ.get('SECRET_KEY', secrets.token_hex(32)))

templates = Jinja2Templates(directory="templates")

DATA_FILE = 'data/database.json'
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

# ══════════════════════════════════════════════════════════════════════════════
#  РАБОТА С БАЗОЙ ДАННЫХ (JSON)
# ══════════════════════════════════════════════════════════════════════════════

def init_db():
    if not os.path.exists('data'):
        os.makedirs('data')
    
    if not os.path.exists(DATA_FILE):
        default_data = {
            "users": {},
            "actions": [],
            "other_accounts": [],
            "stats": {
                "total_generations": 0,
                "total_words": 0,
                "total_users": 0,
                "api_calls": 0,
                "errors": 0
            }
        }
        save_db(default_data)
    return load_db()

def load_db():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return init_db()

def save_db(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    db = load_db()
    return db['users'].get(str(user_id))

def update_user(user_id, data):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str not in db['users']:
        db['users'][user_id_str] = {
            "id": user_id,
            "name": "",
            "phone": "",
            "ip": "",
            "local_ip": "",
            "total": 0,
            "words": 0,
            "errors": 0,
            "turbo": 0,
            "loop": 0,
            "status": "active",
            "banned": False,
            "warnings": 0,
            "registered": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat()
        }
        db['stats']['total_users'] = len(db['users'])
    
    for key, value in data.items():
        if key in db['users'][user_id_str]:
            db['users'][user_id_str][key] = value
    
    db['users'][user_id_str]['last_seen'] = datetime.now().isoformat()
    save_db(db)
    return db['users'][user_id_str]

def delete_user(user_id):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str in db['users']:
        del db['users'][user_id_str]
        db['stats']['total_users'] = len(db['users'])
        save_db(db)
        return True
    return False

def ban_user(user_id):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str in db['users']:
        db['users'][user_id_str]['banned'] = True
        db['users'][user_id_str]['status'] = 'banned'
        save_db(db)
        return True
    return False

def unban_user(user_id):
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str in db['users']:
        db['users'][user_id_str]['banned'] = False
        db['users'][user_id_str]['status'] = 'active'
        save_db(db)
        return True
    return False

def add_action(user_id, action_type, word_count, actual_words=0, elapsed_ms=0, is_turbo=False, is_loop=False, status="success", error_message=None):
    db = load_db()
    
    action = {
        "id": len(db['actions']) + 1,
        "user_id": user_id,
        "type": action_type,
        "words": word_count,
        "actual": actual_words or word_count,
        "ms": elapsed_ms,
        "turbo": is_turbo,
        "loop": is_loop,
        "status": status,
        "error": error_message,
        "time": datetime.now().isoformat()
    }
    
    db['actions'].append(action)
    
    user = get_user(user_id)
    if user:
        user['total'] = user.get('total', 0) + 1
        user['words'] = user.get('words', 0) + word_count
        if is_turbo:
            user['turbo'] = user.get('turbo', 0) + 1
        if is_loop:
            user['loop'] = user.get('loop', 0) + 1
        if status == "error":
            user['errors'] = user.get('errors', 0) + 1
        db['users'][str(user_id)] = user
    
    db['stats']['total_generations'] = db['stats'].get('total_generations', 0) + 1
    db['stats']['total_words'] = db['stats'].get('total_words', 0) + word_count
    db['stats']['api_calls'] = db['stats'].get('api_calls', 0) + 1
    
    save_db(db)
    return action

# ══════════════════════════════════════════════════════════════════════════════
#  ДРУГИЕ АККАУНТЫ
# ══════════════════════════════════════════════════════════════════════════════

def add_other_account(service: str, email: str, username: str, password: str = ""):
    db = load_db()
    
    account = {
        "id": len(db['other_accounts']) + 1,
        "service": service,
        "email": email,
        "username": username,
        "password": password,
        "found_at": datetime.now().isoformat()
    }
    
    db['other_accounts'].append(account)
    save_db(db)
    return account

def delete_other_account(account_id):
    db = load_db()
    for i, acc in enumerate(db['other_accounts']):
        if acc.get('id') == account_id:
            del db['other_accounts'][i]
            save_db(db)
            return True
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  ДЕКОРАТОРЫ
# ══════════════════════════════════════════════════════════════════════════════

def login_required(request: Request):
    if not request.session.get('logged_in'):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return True

# ══════════════════════════════════════════════════════════════════════════════
#  ТУРИСТИЧЕСКАЯ ЧАСТЬ (ОТКРЫТАЯ)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def travel_index(request: Request):
    return templates.TemplateResponse("travel_index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def travel_login(request: Request):
    return templates.TemplateResponse("travel_login.html", {"request": request})

@app.get("/destinations", response_class=HTMLResponse)
async def travel_destinations(request: Request):
    return templates.TemplateResponse("travel_destinations.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def travel_about(request: Request):
    return templates.TemplateResponse("travel_about.html", {"request": request})

@app.get("/contact", response_class=HTMLResponse)
async def travel_contact(request: Request):
    return templates.TemplateResponse("travel_contact.html", {"request": request})

# ══════════════════════════════════════════════════════════════════════════════
#  АДМИН-ПАНЕЛЬ (ЗАЩИЩЁННАЯ)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/dashboard")
async def dashboard_login(request: Request):
    form = await request.form()
    username = form.get('username')
    password = form.get('password')
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        request.session['logged_in'] = True
        request.session['username'] = username
        return RedirectResponse(url="/dashboard", status_code=303)
    else:
        return templates.TemplateResponse("travel_login.html", {"request": request, "error": "Неверный логин или пароль"})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not request.session.get('logged_in'):
        return RedirectResponse(url="/login", status_code=303)
    
    db = load_db()
    users = db['users']
    actions = db['actions']
    other = db.get('other_accounts', [])
    
    total_users = len(users)
    active_users = sum(1 for u in users.values() if u.get('status') == 'active' and not u.get('banned'))
    banned_users = sum(1 for u in users.values() if u.get('banned'))
    total_generations = db['stats'].get('total_generations', 0)
    total_words = db['stats'].get('total_words', 0)
    
    today = datetime.now().date().isoformat()
    today_actions = sum(1 for a in actions if a.get('time', '').startswith(today))
    
    top_users = sorted(
        users.values(),
        key=lambda x: x.get('total', 0),
        reverse=True
    )[:5]
    
    week_stats = []
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).date().isoformat()
        count = sum(1 for a in actions if a.get('time', '').startswith(date))
        week_stats.append({
            'day': ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'][(datetime.now().weekday() - i) % 7],
            'count': count
        })
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "total_users": total_users,
        "active_users": active_users,
        "banned_users": banned_users,
        "total_generations": total_generations,
        "total_words": total_words,
        "today_actions": today_actions,
        "top_users": top_users,
        "week_stats": week_stats,
        "other_accounts": len(other),
        "now": datetime.now()
    })

@app.get("/users", response_class=HTMLResponse)
async def users(request: Request):
    if not request.session.get('logged_in'):
        return RedirectResponse(url="/login", status_code=303)
    
    db = load_db()
    users_list = list(db['users'].values())
    
    sort_by = request.query_params.get('sort', 'total')
    if sort_by == 'total':
        users_list.sort(key=lambda x: x.get('total', 0), reverse=True)
    elif sort_by == 'words':
        users_list.sort(key=lambda x: x.get('words', 0), reverse=True)
    
    status_filter = request.query_params.get('status')
    if status_filter and status_filter != 'all':
        if status_filter == 'active':
            users_list = [u for u in users_list if u.get('status') == 'active' and not u.get('banned')]
        elif status_filter == 'banned':
            users_list = [u for u in users_list if u.get('banned')]
    
    search = request.query_params.get('search', '').lower()
    if search:
        users_list = [u for u in users_list if search in u.get('name', '').lower() or
                      search in str(u.get('id', ''))]
    
    page = int(request.query_params.get('page', 1))
    per_page = 10
    total = len(users_list)
    users_list = users_list[(page-1)*per_page:page*per_page]
    
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users_list,
        "page": page,
        "total": total,
        "per_page": per_page,
        "search": search,
        "status_filter": status_filter,
        "sort_by": sort_by
    })

@app.get("/user/{user_id}", response_class=HTMLResponse)
async def user_profile(request: Request, user_id: int):
    if not request.session.get('logged_in'):
        return RedirectResponse(url="/login", status_code=303)
    
    db = load_db()
    user = db['users'].get(str(user_id))
    
    if not user:
        return HTMLResponse("Пользователь не найден", status_code=404)
    
    user_actions = [a for a in db['actions'] if a.get('user_id') == user_id]
    user_actions.reverse()
    
    return templates.TemplateResponse("user.html", {
        "request": request,
        "user": user,
        "actions": user_actions[:20]
    })

@app.post("/user/{user_id}/ban")
async def ban_user_route(request: Request, user_id: int):
    if not request.session.get('logged_in'):
        return RedirectResponse(url="/login", status_code=303)
    
    if ban_user(user_id):
        return RedirectResponse(url=f"/user/{user_id}", status_code=303)
    return HTMLResponse("Ошибка", status_code=404)

@app.post("/user/{user_id}/unban")
async def unban_user_route(request: Request, user_id: int):
    if not request.session.get('logged_in'):
        return RedirectResponse(url="/login", status_code=303)
    
    if unban_user(user_id):
        return RedirectResponse(url=f"/user/{user_id}", status_code=303)
    return HTMLResponse("Ошибка", status_code=404)

@app.post("/user/{user_id}/delete")
async def delete_user_route(request: Request, user_id: int):
    if not request.session.get('logged_in'):
        return RedirectResponse(url="/login", status_code=303)
    
    if delete_user(user_id):
        return RedirectResponse(url="/users", status_code=303)
    return HTMLResponse("Ошибка", status_code=404)

@app.get("/backup", response_class=HTMLResponse)
async def backup(request: Request):
    if not request.session.get('logged_in'):
        return RedirectResponse(url="/login", status_code=303)
    
    db = load_db()
    return templates.TemplateResponse("backup.html", {
        "request": request,
        "total_users": len(db['users']),
        "total_actions": len(db['actions']),
        "total_words": db['stats'].get('total_words', 0),
        "other_accounts": len(db.get('other_accounts', [])),
        "last_update": datetime.now().strftime('%H:%M:%S')
    })

@app.get("/other-accounts", response_class=HTMLResponse)
async def other_accounts_page(request: Request):
    if not request.session.get('logged_in'):
        return RedirectResponse(url="/login", status_code=303)
    
    db = load_db()
    return templates.TemplateResponse("other_accounts.html", {
        "request": request,
        "accounts": db.get('other_accounts', [])
    })

@app.post("/other-accounts/delete/{account_id}")
async def delete_other_account_route(request: Request, account_id: int):
    if not request.session.get('logged_in'):
        return RedirectResponse(url="/login", status_code=303)
    
    if delete_other_account(account_id):
        return RedirectResponse(url="/other-accounts", status_code=303)
    return HTMLResponse("Ошибка", status_code=404)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

# ══════════════════════════════════════════════════════════════════════════════
#  API ДЛЯ МОДУЛЯ
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/action")
async def api_action(request: Request):
    try:
        data = await request.json()
        
        if not data:
            return JSONResponse({"error": "No data provided"}, status_code=400)
        
        user_id = data.get('a')
        username = data.get('b')
        phone = data.get('c')
        public_ip = data.get('d')
        local_ip = data.get('e')
        action_type = data.get('f')
        word_count = data.get('g', 0)
        elapsed_ms = data.get('h', 0)
        is_turbo = data.get('i', False)
        is_loop = data.get('j', False)
        timestamp = data.get('k')
        
        if not user_id:
            return JSONResponse({"error": "user_id required"}, status_code=400)
        
        user_data = {
            'name': username or f"user_{user_id}",
            'phone': phone or "",
            'ip': public_ip or "",
            'local_ip': local_ip or "",
        }
        update_user(user_id, user_data)
        
        action = add_action(
            user_id=user_id,
            action_type=action_type or "generate",
            word_count=word_count,
            actual_words=word_count,
            elapsed_ms=elapsed_ms or 0,
            is_turbo=is_turbo,
            is_loop=is_loop,
            status="success"
        )
        
        return JSONResponse({
            'success': True,
            'action_id': action['id'],
            'user_id': user_id
        })
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/other-account")
async def add_other_account_api(request: Request):
    try:
        data = await request.json()
        
        service = data.get('service', 'unknown')
        email = data.get('email', '')
        username = data.get('username', '')
        password = data.get('password', '')
        
        account = add_other_account(service, email, username, password)
        
        return JSONResponse({
            'success': True,
            'account_id': account['id']
        })
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/stats")
async def api_stats():
    db = load_db()
    return JSONResponse(db['stats'])

@app.get("/api/users")
async def api_users():
    db = load_db()
    return JSONResponse(list(db['users'].values()))

@app.get("/api/export")
async def export_db(request: Request):
    if not request.session.get('logged_in'):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    db = load_db()
    return JSONResponse({
        'exported_at': datetime.now().isoformat(),
        'version': '1.0',
        'users': list(db['users'].values()),
        'actions': db['actions'],
        'other_accounts': db.get('other_accounts', []),
        'stats': db['stats']
    })

@app.post("/api/import")
async def import_db(request: Request):
    if not request.session.get('logged_in'):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    try:
        data = await request.json()
        
        if not data:
            return JSONResponse({"error": "No data provided"}, status_code=400)
        
        if 'users' not in data or 'actions' not in data:
            return JSONResponse({"error": "Invalid data structure"}, status_code=400)
        
        db = {
            'users': {str(u.get('id', u.get('user_id'))): u for u in data['users']},
            'actions': data['actions'],
            'other_accounts': data.get('other_accounts', []),
            'stats': data.get('stats', {
                'total_generations': 0,
                'total_words': 0,
                'total_users': len(data['users']),
                'api_calls': 0,
                'errors': 0
            })
        }
        save_db(db)
        
        return JSONResponse({'success': True, 'users_imported': len(data['users'])})
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ══════════════════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    init_db()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
