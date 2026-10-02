from __future__ import annotations
from typing import Dict, List

KEYWORDS = {
    'sales': ['مبيعات','بيع','عملاء','زبائن','sales','customers'],
    'marketing': ['تسويق','اعلان','إعلان','حملة','marketing','instagram','facebook'],
    'research': ['سوق','منافس','منافسين','سعر','market','competitor','research'],
    'content': ['محتوى','منشور','بوست','كتابة','content','post'],
    'analytics': ['تحليل','أرقام','احصائيات','إحصائيات','analytics','data'],
    'image': ['صورة','صور','تصميم','image','creative'],
    'video': ['فيديو','video','reel'],
}

def select_agents(text: str) -> List[str]:
    t=text.lower(); found=[]
    for agent, words in KEYWORDS.items():
        if any(w in t for w in words): found.append(agent)
    return found or ['ceo','research']

def completeness(description: str) -> Dict:
    d=(description or '').lower()
    checks={
        'business': any(x in d for x in ['شركة','مشروع','متجر','محل','خدمة','business','shop','company']),
        'goal': any(x in d for x in ['أريد','بدي','هدف','زيادة','خفض','اريد','want','goal']),
        'market': any(x in d for x in ['سوريا','السعودية','الإمارات','فرنسا','العراق','مصر','سوق','بلد','market','country']),
        'offer': any(x in d for x in ['منتج','خدمة','منتجات','سعر','product','service','price']),
    }
    return {'score': round(sum(checks.values())/len(checks)*100), 'checks': checks}

def build_execution_plan(company: Dict, request: str) -> Dict:
    agents=select_agents(request); plan=[]
    if 'research' in agents: plan.append('جمع معلومات السوق والمنافسين وتحديد فجوة قابلة للاستغلال')
    if 'analytics' in agents: plan.append('تحديد المقاييس الأساسية وخط أساس قبل أي تجربة')
    if 'marketing' in agents: plan.append('اقتراح تجربة تسويقية صغيرة قابلة للقياس')
    if 'content' in agents: plan.append('إنشاء 3 زوايا محتوى مرتبطة بالعرض والجمهور')
    if 'image' in agents or 'video' in agents: plan.append('تجهيز موجز إبداعي قبل توليد أي مادة مرئية')
    if 'sales' in agents: plan.append('بناء شرائح عملاء ورسائل أولية غير مزعجة')
    if not plan: plan=['فهم الوضع الحالي','تحديد الهدف','اختيار تجربة أولى','قياس النتيجة']
    return {'agents':agents,'steps':plan,'company':company.get('name',''),'request':request}

def generate_research_report(company: Dict, request: str, live: Dict | None = None) -> Dict:
    name=company.get('name','الشركة'); desc=company.get('description',''); c=completeness(desc); plan=build_execution_plan(company,request)
    live=live or {}; results=live.get('results', [])
    source_insights=[]
    for x in results[:5]:
        source_insights.append({'title':x.get('title',''),'url':x.get('url',''),'insight':x.get('content','')[:500]})
    recommendations=[]
    if results:
        recommendations=[
            'قارن أول 3 مصادر من حيث العرض والسعر والرسالة قبل اتخاذ قرار.',
            'حوّل أبرز فجوة متكررة إلى تجربة واحدة لمدة 7 أيام.',
            'حدد مقياس نجاح واحداً قبل تنفيذ أي إنفاق أو تواصل خارجي.'
        ]
    else:
        recommendations=['ثبّت السوق والجمهور والعرض أولاً.','شغّل البحث الحي للحصول على أدلة ومصادر قبل اتخاذ قرار سوقي.','ابدأ بتجربة صغيرة قابلة للقياس بدلاً من حملة كبيرة.']
    return {
      'title': f'تقرير انطلاق — {name}', 'confidence': c['score'],
      'executive_summary': f'تم تحليل طلب {name}. الهدف هو تحويل البحث إلى قرار وتجربة قابلة للقياس، مع تجنب الإنفاق أو التواصل الخارجي قبل التحقق.',
      'what_we_know': c['checks'], 'selected_agents': plan['agents'], 'execution_plan': plan['steps'],
      'recommendations': recommendations,
      'first_experiment': 'اختبار واحد منخفض التكلفة لمدة 7 أيام مع مقياس نجاح واضح، ثم قرار الاستمرار أو التعديل.',
      'questions': [k for k,v in c['checks'].items() if not v],
      'live_connected': bool(live.get('connected')), 'source_count': len(source_insights), 'sources': source_insights,
      'note': 'المصادر المعروضة هنا تأتي من البحث الحي فقط عند اتصال مزود البحث؛ النظام لا يخترع مصادر.'
    }


def build_first_execution(company: Dict, request: str) -> Dict:
    name = company.get('name','الشركة')
    desc = company.get('description','').strip() or 'نشاط تجاري يحتاج إلى تحديد الجمهور والعرض والسوق.'
    return {
        'objective': request or 'زيادة فرص النمو بأقل تكلفة ممكنة',
        'company': name,
        'context': desc[:1200],
        'deliverables': [
            {'type':'marketing_plan','title':'خطة تسويق أولية 7 أيام','items':[
                'اليوم 1: تحديد العرض الأقوى والجمهور الأكثر احتمالاً للشراء.',
                'اليومان 2-3: نشر محتوى تعليمي/مشكلة-حل واختبار أكثر من زاوية.',
                'اليومان 4-5: متابعة التفاعل والأسئلة وتحويلها إلى فرص.',
                'اليومان 6-7: مراجعة النتائج واختيار التجربة التالية.'
            ]},
            {'type':'content_pack','title':'حزمة محتوى أولية','items':[
                f'منشور 1: المشكلة التي يحلها {name} ولماذا تهم العميل.',
                f'منشور 2: مقارنة بين الحل التقليدي والحل الذي تقدمه {name}.',
                f'منشور 3: سؤال/دعوة للتواصل تكشف حاجة العميل قبل البيع.'
            ]},
            {'type':'kpi','title':'مؤشرات النجاح','items':['عدد الاستفسارات المؤهلة','نسبة التحول إلى محادثة/طلب','متوسط قيمة الطلب أو الهدف التجاري المناسب','أكثر محتوى/عرض جذباً للاهتمام']},
            {'type':'next_step','title':'الخطوة التالية','items':['نفّذ أول تجربة بدون إنفاق إعلاني.','سجّل النتيجة.','دع النظام يقارن النتيجة بالخطة ويقترح التجربة التالية.']}
        ]
    }

def build_content_pack(company: Dict, audience: str='العملاء المحتملون') -> Dict:
    name=company.get('name','الشركة'); desc=company.get('description','')[:800]
    return {
      'brand':name,'audience':audience,
      'posts':[
        {'title':'مشكلة العميل','copy':f'هل تواجه مشكلة متكررة في هذا المجال؟ {desc}\n\nاكتب لنا ما الذي يزعجك وسنساعدك على معرفة الخطوة المناسبة.'},
        {'title':'قيمة واضحة','copy':f'بدلاً من البدء بعرض طويل، دعنا نبدأ من المشكلة. {name} يركز على فهم احتياجك ثم تقديم الحل الأنسب.'},
        {'title':'دعوة للتجربة','copy':f'إذا كنت تبحث عن حل عملي، أرسل لنا مشكلتك في رسالة واحدة. سنبدأ بتحليلها وتحديد أول خطوة.'}
      ]
    }
