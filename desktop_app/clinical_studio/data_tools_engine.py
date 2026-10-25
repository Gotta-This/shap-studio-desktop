"""Standalone data tools; no changes to the SHAP analysis generator."""
import math
import random
from collections import Counter


def _html_random(seed):
    """Same string seed and 32-bit generator as the original HTML tool."""
    mask = 0xffffffff
    h = 2166136261
    raw = str(seed).encode('utf-16-le', errors='surrogatepass')
    for i in range(0, len(raw), 2):
        h = ((h ^ int.from_bytes(raw[i:i+2], 'little')) * 16777619) & mask
    def draw():
        nonlocal h
        h = (h + 0x6D2B79F5) & mask
        t = ((h ^ (h >> 15)) * (h | 1)) & mask
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & mask)) & mask
        return ((t ^ (t >> 14)) & mask) / 4294967296
    return draw


def category_numbers(categories, seed='12'):
    result = []
    for value, count in categories:
        if not math.isfinite(value) or not isinstance(count, int) or count < 0:
            raise ValueError('数字须有效，数量须为非负整数。')
        if len(result) + count > 100000:
            raise ValueError('总数量须在 1～100,000 之间。')
        result.extend([value] * count)
    if not result:
        raise ValueError('总数量须在 1～100,000 之间。')
    draw = _html_random(seed) if seed != '' else random.SystemRandom().random
    for i in range(len(result)-1, 0, -1):
        j = math.floor(draw() * (i+1))
        result[i], result[j] = result[j], result[i]
    return result


def statistics(values):
    mean = math.fsum(values) / len(values)
    sd = math.sqrt(math.fsum((x-mean)**2 for x in values)/(len(values)-1)) if len(values)>1 else 0.
    return mean, sd


def numeric_numbers(n=70, mean=27.92, sd=14.87, digits=0, lower=None, upper=None, mode='target', seed=None):
    if not isinstance(n, int) or not 2 <= n <= 5000 or digits not in range(5):
        raise ValueError('例数须为 2～5000，小数位数须为 0～4。')
    if mode not in ('target', 'range'):
        raise ValueError('请选择生成模式。')
    if mode=='range' and (lower is None or upper is None):
        raise ValueError('按最大最小值模式需要填写两个边界。')
    if not all(math.isfinite(x) for x in (mean, sd)) or sd<0:
        raise ValueError('均数须有效，标准差须为非负数。')
    for bound in (lower, upper):
        if bound is not None and not math.isfinite(bound):
            raise ValueError('边界必须是有效数字或留空。')
    f=10**digits
    reach=max(sd*(n-1)/math.sqrt(n),1/f)
    low=lower if lower is not None else mean-reach-2/f
    high=upper if upper is not None else mean+reach+2/f
    lo,hi=math.ceil(low*f),math.floor(high*f)
    if lo>hi or max(abs(lo),abs(hi))>1e8:
        raise ValueError('请检查范围：须包含可用数值，缩放后绝对值不超过 1 亿。')
    if mode=='target':
        if not lo/f<=mean<=hi/f:
            raise ValueError('目标均数不在可用范围内。')
        if lower is not None and upper is not None:
            max_sd=math.sqrt(max(0,(hi/f-mean)*(mean-lo/f)*n/(n-1)))
            if sd>max_sd+1e-9:
                raise ValueError('目标标准差超出当前范围可实现的界限。')
    rng=random.Random(seed)
    if mode=='range':
        return [rng.randint(lo,hi)/f for _ in range(n)]
    m,s=mean*f,sd*f
    clamp=lambda x:max(lo,min(hi,math.floor(x+.5)))
    a=[clamp(rng.gauss(m,s)) for _ in range(n)]
    total=sum(a);sq=sum(x*x for x in a)
    ts=n*m;tq=(n-1)*s*s+n*m*m;scale=max(1,hi-lo)
    def score(total,sq):
        return ((total-ts)/n/scale)**2+((sq-tq)/(n*scale*scale))**2
    current=score(total,sq)
    for k in range(180000):
        if current<1e-20:
            break
        i=rng.randrange(n);old=a[i]
        if k%3==0:
            v=clamp(rng.uniform(lo,hi))
        else:
            v=clamp(old+rng.choice((-1,1))*max(1,math.floor(scale*(1-k/180000)*rng.random()*.15+.5)))
        nt=total+v-old;ns=sq+v*v-old*old;cost=score(nt,ns)
        if cost<current:
            a[i]=v;total=nt;sq=ns;current=cost
    return [x/f for x in a]


def format_values(values, mode='line', digits=None):
    def fmt(x):
        return f'{x:.{digits}f}' if digits is not None else (str(int(x)) if x==int(x) else str(x))
    strings=[fmt(x) for x in values]
    if mode=='r':
        return 'c('+', '.join(strings)+')'
    return {'line':'\n','comma':', ','space':' '}[mode].join(strings)


def category_summary(values):
    return ' · '.join(f'{v:g}：{n} 个（{n/len(values)*100:.1f}%）' for v,n in Counter(values).items())
