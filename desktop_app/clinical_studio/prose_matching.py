"""Shared source matching, independent of GUI frameworks."""
import re
from .prose_table_engine import normalized,canonical,read_docx_text,parse_document,PAIR,QUANTILE,RANGE

def metric_key(name):
    name=normalized(name)[0]
    name=re.sub(r'\((?:岁|月|分|kg/m2|mmHg)\)$','',name)
    return canonical(name)


def matching_document(path,names):
    text=read_docx_text(path)
    # Keep source paragraphs with group data, excluding methods/results elsewhere in Word.
    # Every selected paragraph is retained in full; unresolved content is shown for review.
    paragraphs=[]
    for paragraph in text.splitlines():
        clean=normalized(paragraph)[0]
        if any(g in clean for g in names) and (PAIR.search(clean) or QUANTILE.search(clean) or RANGE.search(clean) or re.search(r'(?:男|女)(?:性)?\d+例',clean) or re.search(r'(?:'+ '|'.join(re.escape(n) for n in names)+r')(?:共|纳入|为)?\d+例',clean)):
            paragraphs.append(paragraph)
    if not paragraphs:return None
    document=parse_document('\n'.join(paragraphs),names)
    if not document['studies'] or not document['studies'][0]['variables']:return None
    return document
