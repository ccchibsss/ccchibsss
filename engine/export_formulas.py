"""Independent catalogue Excel formula generation. No eval or browser formulas."""
import math
import re

ROUND_FIELDS = dict(zip(
    'revenue cogs acquiring lastMile logistics scDelivery packaging storage returnStorage penalties nonStd lateShip listing returns tax perUnitNet'.split(),
    'effPrice costMult agencyFeePerSku buyerDeliveryUnit uLog uSc uPack storageUnit returnStorageUnit slaPenaltyPerUnit nonStdUnit lateShipUnit listingUnit uRet taxUnit netProfit'.split()))
PERCENT_FIELDS={'commission':'commPct','paymentTransfer':'acqPct','boost':'boostPct','cofin':'cofinPct'}
NET_FIELDS='revenue cogs commission specialFee acquiring paymentTransfer lastMile boost logistics scDelivery packaging storage processing returns returnStorage penalties listing tax cofin nonStd lateShip'.split()
TEMPLATES={
 'deficit':'{stock}-{minStock}',
 'shipReady':'IF(AND({stock}>0,{visible}="да",{stock}>={minStock}),"да","нет")',
 'status':'IF(OR({weight}<=0,{length}<=0,{width}<=0,{height}<=0),"Заблокировано системой",IF({excluded}="да","Исключён",IF({deletePending}="да","На удаление",IF(AND({markRequired}="да",{markCompliant}="нет"),"Ошибка маркировки",IF({visible}="нет",IF(OR({visibleReason}="virtual_stock_low",{visibleReason}="min_stock_threshold"),"Скрыт (мало остатка)","Скрыт (витрина)"),IF({deficit}<0,"Дефицит",IF({shipReady}="да","Готов к отгрузке","Норма")))))))',
 'specialFee':'IF({cheapFbsFlag}="да",ROUND(ROUND({effPrice}*{cheapFbsRate}/100,2),2),0)',
 'processing':'ROUND(({uTransitPack}+{prUnit}),2)',
 'costPerUnit':'ROUND({effPrice}-{netProfit},2)',
 'margin':'IFERROR(ROUND(IF({revenue}>0,{netProfit}/{revenue}*100,IFERROR({perUnitNet}/{price}*100,0)),1),0)',
 'roi':'IFERROR(ROUND(IF({cogs}>0,{netProfit}/{cogs}*100,IFERROR({perUnitNet}/{cost}*100,0)),1),0)',
 'costMult':'ROUND(MAX(0,{cost})*{multUsed},2)',
 'priceByMarkup':'ROUND({costMult}*(1+{markupPct}/100),2)',
 'markupOnCost':'IFERROR(IF({tgtPrice}>0,ROUND(({tgtPrice}/{costMult}-1)*100,1),""),"")',
 'markupMargin':'IFERROR(ROUND(({price}-{costMult})/{costMult}*100,1),0)',
 'markupProfit':'IFERROR(ROUND({netProfit}/{cogs}*100,1),0)',
}
FORMULA_KEYS=frozenset(TEMPLATES)|ROUND_FIELDS.keys()|PERCENT_FIELDS.keys()|{'volume','netProfit'}


def formula(key,row,refs,dim_unit='cm'):
    """Missing selected dependency means a cached-value-only cell."""
    class Refs(dict):
        def __missing__(self,k):return refs[k]+str(row)
    r=Refs()
    try:
        if key in ROUND_FIELDS:raw='ROUND('+r[ROUND_FIELDS[key]]+',2)'
        elif key in PERCENT_FIELDS:raw='ROUND(ROUND('+r['effPrice']+'*'+r[PERCENT_FIELDS[key]]+'/100,2),2)'
        elif key=='netProfit':raw='ROUND('+'-'.join(r[k] for k in NET_FIELDS if k not in ('specialFee','penalties') or k in refs)+',2)'
        elif key=='volume':raw=('IF({volumeExplicit}="да",{volumeInput},ROUND({length}*{width}*{height}/'+('1000000' if dim_unit=='mm' else '1000')+',4))').format_map(r)
        elif key in TEMPLATES:raw=TEMPLATES[key].format_map(r)
        else:return None
        return raw
    except KeyError:return None


def column_letter(index):
    text='';index+=1
    while index:index,n=divmod(index-1,26);text=chr(65+n)+text
    return text


def references(meta,sheets):
    refs={}
    for si,sheet in enumerate(sheets):
        name=sheet['name'].replace("'","''")
        for ci,index in enumerate(sheet['indices']):
            key=meta[index].get('key')
            if key=='article' and key in refs:continue
            refs[key]=('' if si==0 else "'"+name+"'!")+column_letter(ci)
    return refs


def cached_formula(key,row,refs,value,unavailable=False,dim_unit='cm'):
    if unavailable:return None
    raw=formula(key,row,refs,dim_unit)
    if raw and (len(raw)>8192 or re.search(r'[\x00-\x08\x0b-\x1f\x7f\[\]{};`|]',raw) or not re.fullmatch(r'''[0-9A-Za-zА-Яа-яЁё_$.,:!<>=+\-*/%()?'"\s]+''',raw)):return None
    if raw and isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and not raw.upper().startswith('IFERROR('):
        raw='IFERROR('+raw+',"")'
    return raw

INVALID_FIELDS=frozenset(['revenue', 'cogs', 'commission', 'specialFee', 'acquiring', 'paymentTransfer', 'lastMile', 'boost', 'cofin', 'logistics', 'scDelivery', 'packaging', 'storage', 'processing', 'returns', 'returnStorage', 'penalties', 'nonStd', 'lateShip', 'listing', 'tax', 'netProfit', 'perUnitNet', 'margin', 'roi', 'costPerUnit', 'fcProfit', 'breakEvenPrice', 'tgtPrice', 'priceToSet', 'priceForApi', 'profitWB', 'marginWB', 'beWB', 'tgtWB', 'profitOzon', 'marginOzon', 'beOzon', 'tgtOzon', 'profitYM', 'marginYM', 'beYM', 'tgtYM', 'profitMM', 'marginMM', 'profitAvito', 'marginAvito', 'beAvito', 'tgtAvito', 'profitDiff', 'effPrice', 'contribution', 'breakEvenUnits', 'fcSales', 'fcRevenue', 'markupProfit', 'uRet', 'uLog', 'uSc', 'uPack', 'uTransitPack', 'storageUnit', 'taxUnit', 'listingUnit', 'prUnit', 'buyerDeliveryUnit', 'returnStorageUnit', 'nonStdUnit', 'lateShipUnit', 'logWB', 'retWB', 'ozonIsKgt', 'ozonLiters', 'dropoffOzon', 'midMileOzon', 'lastMileOzon', 'logOzon', 'retOzon', 'handOverOzon', 'realFbsServiceOzon', 'nonStdOzon', 'lateShipOzon', 'shipDiscOzon', 'retStoreOzon'])
YM_FIELDS=frozenset('returnLogK returnPerKg returnFixed returnStorageDays returnStoragePerDay slaPenaltyPerUnit tariffLastMileP tariffCategoryPath tariffSource tariffQuality tariffQuoteAgeDays tariffQuoteReasons'.split())
MARKET_FIELDS={prefix+suffix:mp for suffix,mp in [('WB','WB'),('Ozon','OZON'),('YM','YM'),('MM','MM'),('Avito','AVITO')] for prefix in ['profit','margin','be','tgt']}


def marketplace(key,group):
    if key in YM_FIELDS:return 'YM'
    if group=='ozn' or re.match(r'^ozon_',key,re.I) or re.search(r'^ozon[A-Z]|Ozon$',key):return 'OZON'
    for suffix,mp in [('WB','WB'),('YM','YM'),('MM','MM'),('Avito','AVITO')]:
        if key.endswith(suffix):return mp
    if key.startswith('cheapFbs'):return 'YM'
    return ''


def unavailable(p,key,group='calc'):
    from enrichment_formula import truth
    if truth(p.get('modelReviewRequired')) and group=='calc':return True
    if (truth(p.get('noBuyInconsistent')) or truth(p.get('modelReviewRequired'))) and key in INVALID_FIELDS:return True
    mp=MARKET_FIELDS.get(key)
    markets=p.get('mp') or {}
    if mp:
        result=markets.get(mp)
        if truth(p.get('noBuyInconsistent')) or truth(p.get('modelReviewRequired')) or result is None or truth(result.get('returnRateInvalid')) or truth(result.get('inputUnavailable')) or result.get('comparisonEligible') is False:return True
    selected=mp or (marketplace(key,group) if group=='calc' else '')
    result=markets.get(selected) or {}
    if selected and (truth(result.get('inputUnavailable')) or result.get('comparisonEligible') is False):return True
    if truth(p.get('priceInputsIncomplete')) and key in ('priceForApi','priceToSet','breakEvenPrice','tgtPrice'):return True
    return truth(p.get('missingTariffBlocked')) and not selected and key in INVALID_FIELDS


def prepare_options(meta,sheets,options):
    if not isinstance(options,dict) or type(options.get('enabled')) is not bool or options.get('dim_unit','cm') not in ('cm','mm'):
        raise ValueError('Неверные настройки Excel-формул')
    if not isinstance(meta,list) or any(not isinstance(m,dict) or not isinstance(m.get('key'),str) for m in meta):
        raise ValueError('Неверные описания колонок формул')
    for m in meta:
        if m.get('server_formula') and m['key'] not in FORMULA_KEYS:raise ValueError('Формула не поддерживается движком: '+m['key'])
    if not options['enabled']:return {}
    if not isinstance(sheets,list) or not 1<=len(sheets)<=10:raise ValueError('Неверные листы формул')
    for sheet in sheets:
        if not isinstance(sheet,dict) or not isinstance(sheet.get('name'),str) or not sheet['name'] or len(sheet['name'])>31 or re.search(r'[\[\]:*?/\\]',sheet['name']):raise ValueError('Неверное имя листа формул')
        indices=sheet.get('indices')
        if not isinstance(indices,list) or any(type(i) is not int or not 0<=i<len(meta) for i in indices) or len(set(indices))!=len(indices):raise ValueError('Неверные колонки листа формул')
    return references(meta,sheets)
