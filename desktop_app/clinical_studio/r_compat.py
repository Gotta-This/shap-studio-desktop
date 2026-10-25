"""R >= 3.6 default set.seed() / sample() compatibility for category vectors.

R uses MT19937 with its own LCG initialization and integer rejection sampling.
Python's MT19937 is given that state directly; Python's seed/shuffle are unused.
Reference: https://stat.ethz.ch/R-manual/R-devel/library/base/html/Random.html
Validated against actual R execution in verification/r-category/reference.json.
"""
import random


def sample_categories(values, seed):
    if str(seed).strip()=='':
        seed=random.SystemRandom().randrange(2147483648)
    try:seed=int(str(seed).strip())
    except ValueError as exc:raise ValueError('与 R set.seed 一致，随机种子须为整数。') from exc
    if not -2147483647<=seed<=2147483647:
        raise ValueError('随机种子须在 -2147483647～2147483647 之间。')
    state=[]
    for i in range(50+625):
        seed=(69069*seed+1)&0xffffffff
        if i>=51:state.append(seed)
    generator=random.Random()
    generator.setstate((3,tuple(state+[624]),None))
    remaining=list(values);result=[]
    while remaining:
        size=len(remaining);bits=(size-1).bit_length();mask=(1<<bits)-1
        while True:
            candidate=0
            for _ in range(0,bits+1,16):
                candidate=(candidate<<16)+(generator.getrandbits(32)>>16)
            candidate &=mask
            if candidate<size:break
        result.append(remaining[candidate])
        remaining[candidate]=remaining[-1];remaining.pop()
    return result
