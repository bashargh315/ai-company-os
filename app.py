from __future__ import annotations
import os, json, sqlite3, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import hashlib
import httpx
from fastapi import FastAPI, HTTPException, Header
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .execution import select_agents, completeness, build_execution_plan, generate_research_report, build_first_execution, build_content_pack

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv('AIOS_DB_PATH', ROOT / 'backend' / 'ai_company_os.db'))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield

app = FastAPI(title='AI Company OS API', version='1.3.1', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

AGENTS = [
    ('ceo','CEO Agent','يفهم الأهداف ويقود التنفيذ'),('research','Research Agent','بحث السوق والمنافسين والفرص'),
    ('sales','Sales Agent','اكتشاف العملاء والمتابعات'),('marketing','Marketing Agent','التسويق والحملات وSEO'),
    ('content','Content Agent','كتابة المحتوى والترجمة'),('image','Image Studio','صور المنتجات والإعلانات'),
    ('video','Video Studio','فيديوهات وإعلانات'),('support','Customer Support','دعم العملاء والتصعيد'),
    ('operations','Operations Agent','تشغيل المهام والمواعيد'),('analytics','Analytics Agent','تحليل الأداء'),
    ('finance','Finance Agent','المالية الداخلية والتوقعات'),('qa','QA & Security','الجودة والأمان والصلاحيات')
]

class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    company_id: str | None = None

class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ''
    language: str = 'ar'

class ApprovalDecision(BaseModel):
    status: str = Field(pattern='^(approved|rejected)$')


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def now(): return datetime.now(timezone.utc).isoformat()

def init_db():
    con=db(); cur=con.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT, provider TEXT, role TEXT DEFAULT 'client', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS companies (id TEXT PRIMARY KEY, user_id TEXT, name TEXT NOT NULL, description TEXT, language TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, company_id TEXT, user_id TEXT, role TEXT, content TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, company_id TEXT, agent TEXT, title TEXT, status TEXT, risk TEXT DEFAULT 'low', result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, company_id TEXT, task_id TEXT, title TEXT, description TEXT, status TEXT DEFAULT 'pending', created_at TEXT NOT NULL, decided_at TEXT);
    CREATE TABLE IF NOT EXISTS activity (id TEXT PRIMARY KEY, company_id TEXT, agent TEXT, event TEXT, meta TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ideas (id TEXT PRIMARY KEY, company_id TEXT, title TEXT, description TEXT, priority TEXT, status TEXT DEFAULT 'new', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS subscriptions (id TEXT PRIMARY KEY, user_id TEXT, company_id TEXT, plan TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', amount_usd REAL NOT NULL, billing_cycle TEXT NOT NULL DEFAULT 'monthly', provider TEXT DEFAULT 'manual', external_id TEXT, starts_at TEXT, renews_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS payment_requests (id TEXT PRIMARY KEY, user_id TEXT, company_id TEXT, plan TEXT NOT NULL, amount_usd REAL NOT NULL, currency TEXT NOT NULL DEFAULT 'USD', status TEXT NOT NULL DEFAULT 'pending', provider TEXT NOT NULL DEFAULT 'manual_link', checkout_url TEXT, external_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_payment_requests_company_time ON payment_requests(company_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_messages_company_time ON messages(company_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_tasks_company_time ON tasks(company_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_activity_company_time ON activity(company_id, created_at);
    ''')
    con.commit(); con.close()

# Safe for local scripts/tests and production startup.
init_db()

PLANS = {
    'starter': {'name':'Starter','amount_usd':49,'label':'للبدايات والمهام الأساسية'},
    'growth': {'name':'Growth','amount_usd':149,'label':'للشركات التي تريد تشغيل AI كفريق'},
    'pro': {'name':'Pro','amount_usd':399,'label':'للتوسع والأتمتة المتقدمة'},
}

def is_owner(user_id: str) -> bool:
    return user_id == 'demo-user'

def current_user(x_demo_user: str | None):
    # Demo auth until real provider credentials are configured.
    uid = x_demo_user or 'demo-user'
    con=db(); row=con.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if not row:
        con.execute('INSERT INTO users(id,email,provider,role,created_at) VALUES(?,?,?,?,?)',(uid, uid+'@demo.local','demo','owner' if uid=='demo-user' else 'client',now())); con.commit()
    con.close(); return uid

def ensure_company(user_id: str, company_id: str | None):
    con=db()
    if company_id:
        row=con.execute('SELECT * FROM companies WHERE id=? AND user_id=?',(company_id,user_id)).fetchone()
        if row: con.close(); return row['id']
        con.close(); raise HTTPException(404,'الشركة غير موجودة')
    row=con.execute('SELECT id FROM companies WHERE user_id=? ORDER BY created_at LIMIT 1',(user_id,)).fetchone()
    if row: con.close(); return row['id']
    cid=str(uuid.uuid4())
    t=now(); con.execute('INSERT INTO companies(id,user_id,name,description,language,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(cid,user_id,'شركتي الجديدة','','ar',t,t)); con.commit(); con.close(); return cid




def get_subscription(user_id: str, company_id: str):
    con=db(); row=con.execute('SELECT * FROM subscriptions WHERE user_id=? AND company_id=? ORDER BY created_at DESC LIMIT 1',(user_id,company_id)).fetchone(); con.close()
    return dict(row) if row else None

def require_paid(user_id: str, company_id: str):
    if is_owner(user_id):
        return {'plan':'owner','status':'active','amount_usd':0}
    sub=get_subscription(user_id,company_id)
    if not sub or sub['status'] != 'active':
        raise HTTPException(402,'الاشتراك غير مفعّل. اختر خطة مدفوعة للمتابعة.')
    return sub

class SubscriptionIn(BaseModel):
    company_id: str
    plan: str = Field(pattern='^(starter|growth|pro)$')

@app.get('/api/billing/plans')
def billing_plans():
    return {'currency':'USD','plans':PLANS}

@app.get('/api/billing/status')
def billing_status(company_id: str, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); ensure_company(uid, company_id)
    if is_owner(uid): return {'active':True,'plan':'owner','amount_usd':0,'label':'Owner / internal access'}
    sub=get_subscription(uid,company_id)
    return {'active':bool(sub and sub['status']=='active'),'subscription':sub}

class CheckoutIn(BaseModel):
    company_id: str
    plan: str = Field(pattern='^(starter|growth|pro)$')

class PaymentConfirmIn(BaseModel):
    payment_id: str
    external_id: str = ''

@app.post('/api/billing/checkout')
def billing_checkout(data: CheckoutIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); ensure_company(uid,data.company_id)
    plan=PLANS[data.plan]; t=now(); pid=str(uuid.uuid4())
    env_key='AIOS_CHECKOUT_URL_'+data.plan.upper()
    checkout_url=os.getenv(env_key,'').strip()
    provider='configured_link' if checkout_url else 'manual_link'
    con=db()
    con.execute('INSERT INTO payment_requests(id,user_id,company_id,plan,amount_usd,currency,status,provider,checkout_url,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(pid,uid,data.company_id,data.plan,plan['amount_usd'],'USD','pending',provider,checkout_url,t,t))
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),data.company_id,'finance','payment_request_created',json.dumps({'payment_id':pid,'plan':data.plan,'amount_usd':plan['amount_usd'],'provider':provider},ensure_ascii=False),t))
    con.commit(); con.close()
    return {'ok':True,'payment_id':pid,'plan':data.plan,'amount_usd':plan['amount_usd'],'currency':'USD','status':'pending','provider':provider,'checkout_url':checkout_url or None}

@app.get('/api/billing/payment-status')
def billing_payment_status(payment_id: str, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); con=db(); row=con.execute('SELECT * FROM payment_requests WHERE id=? AND user_id=?',(payment_id,uid)).fetchone(); con.close()
    if not row: raise HTTPException(404,'طلب الدفع غير موجود')
    return dict(row)

@app.post('/api/billing/confirm')
def billing_confirm(data: PaymentConfirmIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user)
    if not is_owner(uid): raise HTTPException(403,'تأكيد الدفع متاح للمدير فقط.')
    con=db(); row=con.execute('SELECT * FROM payment_requests WHERE id=?',(data.payment_id,)).fetchone()
    if not row:
        con.close(); raise HTTPException(404,'طلب الدفع غير موجود')
    if row['status'] == 'paid':
        sub=con.execute('SELECT * FROM subscriptions WHERE user_id=? AND company_id=? AND plan=? AND status="active" ORDER BY created_at DESC LIMIT 1',(row['user_id'],row['company_id'],row['plan'])).fetchone()
        con.close()
        return {'ok':True,'subscription_id':sub['id'] if sub else None,'payment_id':data.payment_id,'status':'active','plan':row['plan'],'already_confirmed':True}
    t=now(); external_id=data.external_id.strip()
    con.execute("UPDATE payment_requests SET status='paid', external_id=?, updated_at=? WHERE id=? AND status='pending'",(external_id,t,data.payment_id))
    sid=str(uuid.uuid4()); plan=PLANS[row['plan']]
    con.execute("INSERT INTO subscriptions(id,user_id,company_id,plan,status,amount_usd,billing_cycle,provider,external_id,starts_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(sid,row['user_id'],row['company_id'],row['plan'],'active',plan['amount_usd'],'monthly',row['provider'],external_id,t,t,t))
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),row['company_id'],'finance','payment_confirmed',json.dumps({'payment_id':data.payment_id,'plan':row['plan'],'subscription_id':sid},ensure_ascii=False),t))
    con.commit(); con.close(); return {'ok':True,'subscription_id':sid,'payment_id':data.payment_id,'status':'active','plan':row['plan'],'already_confirmed':False}

@app.get('/api/admin/payments')
def admin_payments(x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user)
    if not is_owner(uid): raise HTTPException(403,'للمدير فقط')
    con=db(); rows=con.execute('SELECT * FROM payment_requests ORDER BY created_at DESC LIMIT 100').fetchall(); con.close(); return [dict(r) for r in rows]

@app.post('/api/billing/activate')
def billing_activate(data: SubscriptionIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user)
    if not is_owner(uid): raise HTTPException(403,'هذه العملية متاحة للمدير فقط.')
    ensure_company(uid,data.company_id)
    plan=PLANS[data.plan]; t=now(); sid=str(uuid.uuid4()); con=db()
    con.execute("INSERT INTO subscriptions(id,user_id,company_id,plan,status,amount_usd,billing_cycle,provider,starts_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(sid,uid,data.company_id,data.plan,'active',plan['amount_usd'],'monthly','manual',t,t,t))
    con.commit(); con.close(); return {'ok':True,'subscription_id':sid,'plan':data.plan,'amount_usd':plan['amount_usd']}

class PilotIn(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    goal: str = Field(default='', max_length=1000)

@app.post('/api/pilot/start')
def start_pilot(data: PilotIn, x_demo_user: str | None = Header(default=None)):
    """Create a customer workspace; paid execution remains subscription-gated."""
    uid=current_user(x_demo_user)
    cid=str(uuid.uuid4()); t=now(); con=db()
    desc=(data.description.strip() + ('\nالهدف: '+data.goal.strip() if data.goal.strip() else '')).strip()
    con.execute('INSERT INTO companies(id,user_id,name,description,language,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(cid,uid,data.company_name.strip(),desc,'ar',t,t))
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),cid,'ceo','workspace_created',json.dumps({'goal':data.goal},ensure_ascii=False),t))
    con.execute('INSERT INTO ideas(id,company_id,title,description,priority,status,created_at) VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),cid,'خطة أول 7 أيام','نبدأ بفهم النشاط والهدف، ثم نحدد أسرع تجربة قابلة للقياس بدون تكلفة إعلانية في البداية.','high','new',t))
    con.commit(); con.close()
    return {'ok':True,'company_id':cid,'mode':'onboarding','message':'تم إنشاء مساحة الشركة. فعّل الاشتراك لبدء التنفيذ المدفوع.'}

@app.post('/api/discover')
def discover(company_id: str, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); ensure_company(uid,company_id); require_paid(uid,company_id); con=db()
    ideas=[
      ('زيادة الطلب من العملاء الحاليين','اختبار عرض بسيط للعملاء الحاليين قبل إنفاق أي ميزانية.','high'),
      ('تحسين نقطة التحويل','تحليل أين يتوقف العميل بين الاهتمام والشراء واقتراح تجربة واحدة قابلة للقياس.','high'),
      ('فرصة محتوى منخفضة التكلفة','إنشاء محتوى يجيب عن أكثر سؤال متكرر لدى الجمهور وتحويله إلى قناة جذب.','medium')
    ]
    out=[]
    for title,desc,priority in ideas:
        iid=str(uuid.uuid4()); con.execute('INSERT INTO ideas(id,company_id,title,description,priority,status,created_at) VALUES(?,?,?,?,?,?,?)',(iid,company_id,title,desc,priority,'new',now())); out.append({'id':iid,'title':title,'description':desc,'priority':priority})
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),company_id,'ceo','opportunities_discovered',json.dumps({'count':len(out)},ensure_ascii=False),now()))
    con.commit(); con.close(); return {'ideas':out}

class LiveResearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    company_id: str | None = None
    limit: int = Field(default=5, ge=1, le=10)


def live_search(query: str, limit: int = 5):
    # Provider-agnostic: Tavily is used when a key is configured.
    # Without a key, return a clear setup state rather than fake research.
    key = os.getenv('TAVILY_API_KEY', '').strip()
    if not key:
        return {'connected': False, 'provider': None, 'results': [],
                'message': 'محرك البحث الخارجي غير موصول بعد. أضف TAVILY_API_KEY لتفعيل البحث الحي.'}
    try:
        r = httpx.post('https://api.tavily.com/search', json={
            'api_key': key, 'query': query, 'search_depth': 'basic',
            'max_results': limit, 'include_answer': True, 'include_raw_content': False
        }, timeout=20)
        r.raise_for_status()
        data = r.json()
        return {'connected': True, 'provider': 'tavily', 'answer': data.get('answer',''),
                'results': [{'title':x.get('title',''), 'url':x.get('url',''), 'content':x.get('content','')} for x in data.get('results',[])]}
    except Exception as e:
        return {'connected': True, 'provider': 'tavily', 'results': [], 'error': str(e)}


@app.post('/api/research/live')
def live_research(data: LiveResearchIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user)
    if data.company_id:
        ensure_company(uid, data.company_id); require_paid(uid, data.company_id)
    result=live_search(data.query, data.limit)
    if data.company_id:
        con=db(); t=now()
        con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',
                    (str(uuid.uuid4()),data.company_id,'research','live_research',json.dumps({'query':data.query,'connected':result.get('connected')},ensure_ascii=False),t))
        con.commit(); con.close()
    return result


@app.get('/api/health')
def health(): return {'ok':True,'service':'AI Company OS','version':app.version}

@app.get('/api/config')
def config():
    return {
        'supabase_url': os.getenv('SUPABASE_URL',''),
        'supabase_publishable_key': os.getenv('SUPABASE_PUBLISHABLE_KEY',''),
        'billing_mode': 'paid-client',
        'plans': PLANS,
        'auth_mode': 'supabase' if os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_PUBLISHABLE_KEY') else 'demo',
        'agents': [{'id':a,'name':n,'description':d} for a,n,d in AGENTS]
    }

@app.get('/api/me')
def me(x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user)
    con=db(); row=con.execute('SELECT id,email,provider,role,created_at FROM users WHERE id=?',(uid,)).fetchone(); con.close()
    return dict(row)

@app.get('/api/companies')
def companies(x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); con=db(); rows=con.execute('SELECT * FROM companies WHERE user_id=? ORDER BY updated_at DESC',(uid,)).fetchall(); con.close()
    return [dict(r) for r in rows]

@app.post('/api/companies')
def create_company(data: CompanyIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); cid=str(uuid.uuid4()); t=now(); con=db()
    con.execute('INSERT INTO companies(id,user_id,name,description,language,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(cid,uid,data.name,data.description,data.language,t,t)); con.commit(); con.close()
    return {'id':cid,'name':data.name,'description':data.description,'language':data.language}

@app.get('/api/companies/{company_id}/messages')
def messages(company_id: str, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); ensure_company(uid,company_id); con=db(); rows=con.execute('SELECT role,content,created_at FROM messages WHERE company_id=? ORDER BY created_at',(company_id,)).fetchall(); con.close(); return [dict(r) for r in rows]

@app.post('/api/chat')
def chat(data: MessageIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); cid=ensure_company(uid,data.company_id); require_paid(uid,cid); t=now(); con=db()
    con.execute('INSERT INTO messages(id,company_id,user_id,role,content,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),cid,uid,'user',data.message,t))
    text=data.message.lower()
    needs=select_agents(data.message)
    if 'sales' in needs and 'marketing' not in needs: needs += ['marketing','analytics']
    if 'research' in needs and 'analytics' not in needs: needs += ['analytics']
    needs=list(dict.fromkeys(needs))
    agent_names={a:n for a,n,_ in AGENTS}
    missing = ['مجال الشركة','الهدف الرئيسي','السوق/البلد المستهدف']
    row=con.execute('SELECT description,name FROM companies WHERE id=?',(cid,)).fetchone()
    desc=row['description'] if row else ''
    if desc and len(desc)>20: missing=missing[1:]
    reply=(f"فهمت طلبك مبدئياً، وسأبدأ من {', '.join(agent_names[n] for n in needs[:3])}. "
        + (f"حتى أعطيك نتيجة دقيقة، أحتاج فقط: {missing[0]}" if missing else "المعلومات الأساسية كافية حالياً.")
        + (f"، ثم {missing[1]}" if len(missing)>1 else '')
        + (f" و{missing[2]}" if len(missing)>2 else '')
        + ".\nما رح أطلب معلومات لا تؤثر على القرار، وبعد اكتمال الحد الأدنى سأحوّل الطلب إلى خطة ومهام تنفيذية.")
    con.execute('INSERT INTO messages(id,company_id,user_id,role,content,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),cid,uid,'assistant',reply,now()))
    # Create a visible task for orchestration traceability.
    task_id=str(uuid.uuid4()); con.execute('INSERT INTO tasks(id,company_id,agent,title,status,risk,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(task_id,cid,'ceo','تحليل الطلب وبناء خطة أولية','queued','low',json.dumps({'agents':needs},ensure_ascii=False),t,now()))
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),cid,'ceo','received_request',json.dumps({'agents':needs},ensure_ascii=False),now()))
    con.commit(); con.close(); return {'company_id':cid,'reply':reply,'selected_agents':needs,'task_id':task_id}


@app.get('/api/companies/{company_id}/brain')
def company_brain(company_id: str, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); ensure_company(uid,company_id); con=db()
    company=dict(con.execute('SELECT * FROM companies WHERE id=?',(company_id,)).fetchone())
    msg_count=con.execute('SELECT COUNT(*) n FROM messages WHERE company_id=?',(company_id,)).fetchone()['n']
    task_count=con.execute('SELECT COUNT(*) n FROM tasks WHERE company_id=?',(company_id,)).fetchone()['n']
    idea_count=con.execute('SELECT COUNT(*) n FROM ideas WHERE company_id=?',(company_id,)).fetchone()['n']
    con.close()
    c=completeness(company.get('description',''))
    return {'company':company,'confidence':c['score'],'known':c['checks'],'messages':msg_count,'tasks':task_count,'ideas':idea_count,'next_questions':[k for k,v in c['checks'].items() if not v]}

@app.post('/api/execution/plan')
def execution_plan(data: MessageIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); cid=ensure_company(uid,data.company_id); require_paid(uid,cid); con=db(); company=dict(con.execute('SELECT * FROM companies WHERE id=?',(cid,)).fetchone()); con.close()
    plan=build_execution_plan(company,data.message)
    return {'ok':True,**plan}

@app.post('/api/research/report')
def research_report(data: MessageIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); cid=ensure_company(uid,data.company_id); require_paid(uid,cid); con=db(); company=dict(con.execute('SELECT * FROM companies WHERE id=?',(cid,)).fetchone()); t=now()
    # Build a real report from live evidence when the provider is connected.
    query = data.message.strip() or company.get('description','') or company.get('name','')
    live = live_search(query, 5)
    report=generate_research_report(company,data.message,live)
    tid=str(uuid.uuid4())
    con.execute('INSERT INTO tasks(id,company_id,agent,title,status,risk,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(tid,cid,'research','تقرير بحث وخطة تنفيذ أولية','completed','low',json.dumps(report,ensure_ascii=False),t,t))
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),cid,'research','research_report_created',json.dumps({'confidence':report['confidence']},ensure_ascii=False),t))
    con.commit(); con.close(); return {'ok':True,'task_id':tid,'report':report}


class ExecutionIn(BaseModel):
    request: str = Field(default='', max_length=5000)
    company_id: str | None = None
    audience: str = Field(default='العملاء المحتملون', max_length=300)


@app.post('/api/execution/first')
def first_execution(data: ExecutionIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); cid=ensure_company(uid,data.company_id); require_paid(uid,cid); con=db(); company=dict(con.execute('SELECT * FROM companies WHERE id=?',(cid,)).fetchone()); t=now()
    execution=build_first_execution(company,data.request)
    tid=str(uuid.uuid4())
    con.execute('INSERT INTO tasks(id,company_id,agent,title,status,risk,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
        (tid,cid,'marketing','حزمة التنفيذ الأولى','completed','low',json.dumps(execution,ensure_ascii=False),t,t))
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',
        (str(uuid.uuid4()),cid,'marketing','first_execution_created',json.dumps({'deliverables':len(execution['deliverables'])},ensure_ascii=False),t))
    con.commit(); con.close()
    return {'ok':True,'task_id':tid,'execution':execution,'free_pilot':False}

@app.post('/api/execution/content')
def execution_content(data: ExecutionIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); cid=ensure_company(uid,data.company_id); require_paid(uid,cid); con=db(); company=dict(con.execute('SELECT * FROM companies WHERE id=?',(cid,)).fetchone()); t=now()
    pack=build_content_pack(company,data.audience)
    tid=str(uuid.uuid4())
    con.execute('INSERT INTO tasks(id,company_id,agent,title,status,risk,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
        (tid,cid,'content','حزمة محتوى أولية','completed','low',json.dumps(pack,ensure_ascii=False),t,t))
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',
        (str(uuid.uuid4()),cid,'content','content_pack_created',json.dumps({'posts':3},ensure_ascii=False),t))
    con.commit(); con.close(); return {'ok':True,'task_id':tid,'content':pack}

@app.post('/api/execution/outreach-draft')
def outreach_draft(data: ExecutionIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); cid=ensure_company(uid,data.company_id); require_paid(uid,cid); con=db(); company=dict(con.execute('SELECT * FROM companies WHERE id=?',(cid,)).fetchone()); t=now()
    title='مسودة تواصل مع العملاء المحتملين'; desc=f"مسودة تواصل مرتبطة بهدف: {data.request or 'استكشاف الحاجة'}"
    task_id=str(uuid.uuid4()); approval_id=str(uuid.uuid4())
    draft={'message':f'مرحباً، لاحظنا أن لديكم تحدياً محتملاً في هذا المجال. نريد فهم وضعكم أولاً قبل اقتراح أي شيء. هل يمكن أن تخبرونا ما أكبر مشكلة تواجهكم حالياً؟','note':'هذه مسودة فقط ولن يتم إرسالها تلقائياً.'}
    con.execute('INSERT INTO tasks(id,company_id,agent,title,status,risk,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
        (task_id,cid,'sales',title,'awaiting_approval','medium',json.dumps(draft,ensure_ascii=False),t,t))
    con.execute('INSERT INTO approvals(id,company_id,task_id,title,description,status,created_at) VALUES(?,?,?,?,?,?,?)',
        (approval_id,cid,task_id,title,desc,'pending',t))
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',
        (str(uuid.uuid4()),cid,'sales','outreach_draft_waiting_approval',json.dumps({'approval_id':approval_id},ensure_ascii=False),t))
    con.commit(); con.close(); return {'ok':True,'task_id':task_id,'approval_id':approval_id,'draft':draft,'requires_manager_approval':True}




class LaunchIn(BaseModel):
    company_id: str
    request: str = Field(default='', max_length=5000)
    audience: str = Field(default='العملاء المحتملون', max_length=300)

@app.get('/api/companies/{company_id}/summary')
def company_summary(company_id: str, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); ensure_company(uid,company_id); con=db()
    company=dict(con.execute('SELECT * FROM companies WHERE id=?',(company_id,)).fetchone())
    pending=con.execute('SELECT COUNT(*) n FROM approvals WHERE company_id=? AND status="pending"',(company_id,)).fetchone()['n']
    completed=con.execute('SELECT COUNT(*) n FROM tasks WHERE company_id=? AND status="completed"',(company_id,)).fetchone()['n']
    queued=con.execute('SELECT COUNT(*) n FROM tasks WHERE company_id=? AND status IN ("queued","awaiting_approval")',(company_id,)).fetchone()['n']
    recent=[dict(r) for r in con.execute('SELECT agent,event,created_at FROM activity WHERE company_id=? ORDER BY created_at DESC LIMIT 8',(company_id,)).fetchall()]
    con.close()
    c=completeness(company.get('description',''))
    return {'company':company,'confidence':c['score'],'next_questions':[k for k,v in c['checks'].items() if not v],
            'stats':{'completed_tasks':completed,'active_tasks':queued,'pending_approvals':pending},'recent_activity':recent}

@app.post('/api/execution/launch')
def launch_execution(data: LaunchIn, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); cid=ensure_company(uid,data.company_id); require_paid(uid,cid); con=db(); company=dict(con.execute('SELECT * FROM companies WHERE id=?',(cid,)).fetchone()); t=now()
    req=data.request.strip() or 'الحصول على أول نتيجة قابلة للقياس'
    # Avoid running the same first-client request repeatedly within 24h.
    cutoff=(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
    rows=con.execute('SELECT id,result,created_at FROM tasks WHERE company_id=? AND title=? AND created_at>=? ORDER BY created_at DESC LIMIT 10',(cid,'تشغيل تجربة العميل الأول',cutoff)).fetchall()
    for row in rows:
        try:
            old=json.loads(row['result']) if row['result'] else {}
        except Exception:
            old={}
        if (old.get('request') or '').strip().lower()==req.lower():
            con.close(); return {'ok':True,'task_id':row['id'],'result':old,'free_pilot':False,'deduplicated':True}
    plan=build_execution_plan(company,req)
    execution=build_first_execution(company,req)
    content=build_content_pack(company,data.audience)
    task_id=str(uuid.uuid4())
    result={'mode':'paid-execution','request':req,'plan':plan,'execution':execution,'content':content,
            'next_actions':['راجع خطة الأيام السبعة','اختر أفضل منشور للتجربة','لا يتم إرسال أي رسالة خارجية بدون موافقة المدير']}
    con.execute('INSERT INTO tasks(id,company_id,agent,title,status,risk,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (task_id,cid,'ceo','تشغيل تجربة العميل الأول','completed','low',json.dumps(result,ensure_ascii=False),t,t))
    con.execute('INSERT INTO activity(id,company_id,agent,event,meta,created_at) VALUES(?,?,?,?,?,?)',
                (str(uuid.uuid4()),cid,'ceo','first_client_launched',json.dumps({'task_id':task_id,'agents':plan['agents']},ensure_ascii=False),t))
    con.commit(); con.close()
    return {'ok':True,'task_id':task_id,'result':result,'free_pilot':False,'deduplicated':False}

@app.get('/api/companies/{company_id}/latest-result')
def latest_result(company_id: str, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); ensure_company(uid,company_id); con=db()
    row=con.execute("SELECT id,result,title,status,created_at FROM tasks WHERE company_id=? AND status='completed' ORDER BY created_at DESC LIMIT 1",(company_id,)).fetchone()
    con.close()
    if not row: return {'result':None}
    result=json.loads(row['result']) if row['result'] else None
    return {'task_id':row['id'],'title':row['title'],'status':row['status'],'created_at':row['created_at'],'result':result}

@app.get('/api/tasks/{task_id}')
def get_task(task_id: str, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); con=db(); row=con.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
    if not row: con.close(); raise HTTPException(404,'Task not found')
    if row['company_id']:
        check=con.execute('SELECT id FROM companies WHERE id=? AND user_id=?',(row['company_id'],uid)).fetchone()
        if not check and uid!='demo-user': con.close(); raise HTTPException(403,'Forbidden')
    item=dict(row); item['result']=json.loads(item['result']) if item.get('result') else None; con.close(); return item

@app.get('/api/tasks/{task_id}/text')
def get_task_text(task_id: str, x_demo_user: str | None = Header(default=None)):
    task=get_task(task_id,x_demo_user)
    r=task.get('result') or {}
    lines=[f"AI Company OS — {task['title']}",f"الحالة: {task['status']}",f"تاريخ الإنشاء: {task['created_at']}",""]
    if isinstance(r,dict):
        for key,label in [('request','الطلب'),('objective','الهدف'),('context','السياق')]:
            if r.get(key): lines += [f"{label}: {r[key]}",""]
        plan=(r.get('plan') or {}).get('steps',[]) if isinstance(r.get('plan'),dict) else []
        if plan: lines += ['الخطة:', *[f'- {x}' for x in plan], '']
        deliver=r.get('execution',{}).get('deliverables',[]) if isinstance(r.get('execution'),dict) else []
        if deliver:
            lines += ['التنفيذ الأول:']
            for d in deliver:
                lines += [f"## {d.get('title','')}", *[f"- {x}" for x in d.get('items',[])], '']
        posts=r.get('content',{}).get('posts',[]) if isinstance(r.get('content'),dict) else []
        if posts:
            lines += ['حزمة المحتوى:']
            for p in posts:
                lines += [f"## {p.get('title','')}", p.get('copy',''), '']
        lines += ['الملاحظة: أي إجراء خارجي حساس يحتاج موافقة المدير قبل الإرسال.']
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse('\n'.join(lines),media_type='text/plain; charset=utf-8')

@app.get('/api/companies/{company_id}/tasks')
def company_tasks(company_id: str, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user); ensure_company(uid,company_id); con=db(); rows=con.execute('SELECT * FROM tasks WHERE company_id=? ORDER BY created_at DESC',(company_id,)).fetchall(); con.close(); return [dict(r) for r in rows]

@app.get('/api/admin/overview')
def admin_overview(x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user)
    if uid!='demo-user': raise HTTPException(403,'Owner access required')
    con=db()
    data={
      'customers': con.execute('SELECT COUNT(*) n FROM users WHERE role="client"').fetchone()['n'],
      'companies': con.execute('SELECT COUNT(*) n FROM companies').fetchone()['n'],
      'tasks': con.execute('SELECT COUNT(*) n FROM tasks').fetchone()['n'],
      'pending_approvals': con.execute('SELECT COUNT(*) n FROM approvals WHERE status="pending"').fetchone()['n'],
      'ideas': con.execute('SELECT COUNT(*) n FROM ideas WHERE status="new"').fetchone()['n'],
      'recent_activity':[dict(r) for r in con.execute('SELECT agent,event,meta,created_at FROM activity ORDER BY created_at DESC LIMIT 12').fetchall()],
      'approvals':[dict(r) for r in con.execute('SELECT * FROM approvals WHERE status="pending" ORDER BY created_at DESC LIMIT 12').fetchall()],
      'customers_list':[dict(r) for r in con.execute('SELECT c.id,c.name,c.language,c.created_at,u.email FROM companies c LEFT JOIN users u ON u.id=c.user_id ORDER BY c.created_at DESC LIMIT 12').fetchall()]
    }
    con.close(); return data

@app.get('/api/admin/agents')
def admin_agents(x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user)
    if uid!='demo-user': raise HTTPException(403,'Owner access required')
    con=db(); out=[]
    for aid,name,desc in AGENTS:
        n=con.execute('SELECT COUNT(*) n FROM activity WHERE agent=?',(aid,)).fetchone()['n']
        out.append({'id':aid,'name':name,'description':desc,'activity_count':n,'status':'ready'})
    con.close(); return out

@app.get('/api/admin/tasks')
def admin_tasks(x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user)
    if uid!='demo-user': raise HTTPException(403)
    con=db(); rows=con.execute('SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100').fetchall(); con.close(); return [dict(r) for r in rows]

@app.post('/api/admin/approvals/{approval_id}')
def decide_approval(approval_id: str, data: ApprovalDecision, x_demo_user: str | None = Header(default=None)):
    uid=current_user(x_demo_user)
    if uid!='demo-user': raise HTTPException(403)
    con=db(); row=con.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
    if not row: con.close(); raise HTTPException(404,'Approval not found')
    con.execute('UPDATE approvals SET status=?,decided_at=? WHERE id=?',(data.status,now(),approval_id)); con.commit(); con.close(); return {'ok':True,'status':data.status}

# Static serving for a simple single-origin deployment.
@app.get('/')
def client_home(): return FileResponse(ROOT/'client'/'index.html')
@app.get('/app')
def client_app(): return FileResponse(ROOT/'client'/'index.html')
@app.get('/admin')
def admin_home(): return FileResponse(ROOT/'admin'/'index.html')
@app.get('/manager')
def manager_home(): return FileResponse(ROOT/'admin'/'index.html')
