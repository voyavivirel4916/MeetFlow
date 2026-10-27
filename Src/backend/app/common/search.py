from app.common.responses import ApiError


def search_text(value):
    """Bound literal title searches; SQL wildcard characters are data."""
    try:
        valid=isinstance(value,str) and len(value)<=100 and '\x00' not in value
        if valid:value.encode('utf-8')
    except UnicodeError:valid=False
    if not valid:
        raise ApiError(422,'VALIDATION_ERROR','搜索内容最多100个有效字符。',
                       {'fields':[{'location':['query','q'],'type':'value_error'}]})
    return value.strip()
