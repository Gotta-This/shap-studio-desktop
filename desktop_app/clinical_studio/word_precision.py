"""Precision defaults for recognition; explicit per-row edits stay authoritative."""
def mean_precision(field,mode):
    source=field.setdefault('_source_digits',field.get('digits',2))
    previous=field.get('_default_digits',field.get('digits',2))
    if field.get('digits',2)!=previous:return  # Explicitly edited in a preview.
    field['digits']=0 if mode=='zero' else source
    field['_default_digits']=field['digits']


def fields_precision(fields,mode):
    for field in fields:
        if field.get('kind','mean_sd')=='mean_sd':mean_precision(field,mode)
    return fields


def prose_precision(document,mode):
    if document:
        for study in document.get('studies',[]):
            for variable in study.get('variables',[]):
                if variable['kind']=='mean_sd':
                    for cell in variable['cells'].values():mean_precision(cell,mode)
    return document


def scan_precision(scan,mode):
    fields_precision(scan['fields'],mode);prose_precision(scan.get('prose_document'),mode)
    return scan
