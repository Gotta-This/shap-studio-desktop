"""Current weather and city preferences, with bounded requests and offline cache."""
from datetime import datetime,timezone
from pathlib import Path
import json,math,os,ssl,tempfile,time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import certifi

DEFAULT_LOCATION = dict(name='焦作市',label='河南省 · 焦作市',latitude=35.23925,longitude=113.23914)

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.weather-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)

def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'ResearchDataTools/3','Accept':'application/json'}),timeout=12,context=ssl.create_default_context(cafile=certifi.where())) as response:
        data=json.loads(response.read(2*1024*1024))
    if data.get('error'):raise ValueError('天气服务暂时不可用')
    return data

def location(value):
    name=str(value.get('name','')).strip();lat=float(value['latitude']);lon=float(value['longitude'])
    if not name or len(name)>100 or not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('请选择有效城市')
    return dict(name=name,label=str(value.get('label') or name)[:200],latitude=lat,longitude=lon)

def search(query):
    query=str(query).strip()
    if not 2<=len(query)<=80:raise ValueError('请输入至少两个字的城市名称')
    if DEFAULT_LOCATION and query in ('焦作','焦作市','河南焦作','河南省焦作市'):return [location(DEFAULT_LOCATION)]
    data=fetch('https://geocoding-api.open-meteo.com/v1/search?'+urlencode(dict(name=query,count=6,language='zh',format='json')))
    return [location(dict(r,label=' · '.join(dict.fromkeys(str(r[k]) for k in ('name','admin1','country') if r.get(k))))) for r in data.get('results',[])]

def choose(profile,value):
    value=location(value);write(profile/'weather.json',value);(profile/'weather-cache.json').unlink(missing_ok=True);return value

def describe(code,day=True):
    if code==0:return ('晴','☀️' if day else '🌙')
    if code in (1,2):return ('多云','🌤️' if day else '☁️')
    if code==3:return ('阴','☁️')
    if code in (45,48):return ('雾','🌫️')
    if code in (71,73,75,77,85,86):return ('雪','❄️')
    if code in (95,96,99):return ('雷雨','⛈️')
    if code in (51,53,55,56,57,61,63,65,66,67,80,81,82):return ('雨','🌧️')
    return ('天气变化中','🌡️')

def current(profile,force=False,default_location=None):
    settings=profile/'weather.json'
    if not settings.exists():
        if default_location:choose(profile,default_location)
        else:return dict(configured=False)
    city=location(json.loads(settings.read_text(encoding='utf-8')));cache_file=profile/'weather-cache.json';cached=None
    if cache_file.exists():
        try:
            candidate=json.loads(cache_file.read_text(encoding='utf-8'))
            if candidate.get('location')==city:cached=candidate
        except (ValueError,OSError):pass
    if cached and not force and time.time()-cached['timestamp']<900:return dict(cached,stale=False)
    try:
        data=fetch('https://api.open-meteo.com/v1/forecast?'+urlencode(dict(latitude=city['latitude'],longitude=city['longitude'],current='temperature_2m,weather_code,is_day',temperature_unit='celsius',timezone='auto')))
        value=data['current'];temperature=float(value['temperature_2m'])
        if not math.isfinite(temperature):raise ValueError('气温数据暂不可用')
        text,emoji=describe(int(value['weather_code']),bool(value.get('is_day',1)))
        result=dict(configured=True,location=city,temperature=temperature,description=text,emoji=emoji,observed_at=value['time'],updated_at=datetime.now(timezone.utc).isoformat(),timestamp=time.time(),stale=False,source='Open-Meteo')
        write(cache_file,result);return result
    except Exception as error:
        if cached:return dict(cached,stale=True)
        raise ValueError('天气暂时无法更新，请稍后重试') from error
