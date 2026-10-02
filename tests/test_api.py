import os, tempfile
from fastapi.testclient import TestClient

fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['AIOS_DB_PATH'] = path
from backend.app import app
client = TestClient(app)

def test_health():
    r=client.get('/api/health'); assert r.status_code==200; assert r.json()['version']=='1.3.1'

def test_first_client_and_dedupe():
    h={'X-Demo-User':'demo-client'}
    r=client.post('/api/pilot/start',json={'company_name':'اختبار v1','description':'متجر موبايلات في سوريا','goal':'زيادة المبيعات'},headers=h)
    assert r.status_code==200
    cid=r.json()['company_id']
    payment=client.post('/api/billing/checkout',json={'company_id':cid,'plan':'starter'},headers=h)
    assert payment.status_code==200
    confirmed=client.post('/api/billing/confirm',json={'payment_id':payment.json()['payment_id'],'external_id':'TEST-001'},headers={'X-Demo-User':'demo-user'})
    assert confirmed.status_code==200
    r1=client.post('/api/execution/launch',json={'company_id':cid,'request':'زيادة المبيعات','audience':'عملاء جدد'},headers=h)
    assert r1.status_code==200 and r1.json()['deduplicated'] is False
    r2=client.post('/api/execution/launch',json={'company_id':cid,'request':'زيادة المبيعات','audience':'عملاء جدد'},headers=h)
    assert r2.status_code==200 and r2.json()['deduplicated'] is True
    r3=client.get(f'/api/companies/{cid}/latest-result',headers=h)
    assert r3.status_code==200 and r3.json()['result'] is not None


def test_paid_gating_and_payment_confirmation_idempotency():
    h={'X-Demo-User':'paid-test-client'}
    r=client.post('/api/pilot/start',json={'company_name':'عميل مدفوع','description':'شركة خدمات في سوريا','goal':'زيادة المبيعات'},headers=h)
    assert r.status_code==200
    cid=r.json()['company_id']
    blocked=client.post('/api/execution/launch',json={'company_id':cid,'request':'زيادة المبيعات'},headers=h)
    assert blocked.status_code==402
    checkout=client.post('/api/billing/checkout',json={'company_id':cid,'plan':'starter'},headers=h)
    assert checkout.status_code==200
    pid=checkout.json()['payment_id']
    bad_owner=client.post('/api/billing/confirm',json={'payment_id':pid},headers=h)
    assert bad_owner.status_code==403
    confirmed=client.post('/api/billing/confirm',json={'payment_id':pid,'external_id':'BANK-001'},headers={'X-Demo-User':'demo-user'})
    assert confirmed.status_code==200 and confirmed.json()['already_confirmed'] is False
    confirmed2=client.post('/api/billing/confirm',json={'payment_id':pid,'external_id':'BANK-001'},headers={'X-Demo-User':'demo-user'})
    assert confirmed2.status_code==200 and confirmed2.json()['already_confirmed'] is True
    active=client.get(f'/api/billing/status?company_id={cid}',headers=h)
    assert active.status_code==200 and active.json()['active'] is True
    allowed=client.post('/api/execution/launch',json={'company_id':cid,'request':'زيادة المبيعات'},headers=h)
    assert allowed.status_code==200

def test_admin_agents_requires_owner():
    r=client.get('/api/admin/agents',headers={'X-Demo-User':'not-owner'})
    assert r.status_code==403
