from ..common import global_vars as gv


## Convert string (case insensitive) to boolean.
# @param s str or bytes object to convert.
# @return bool value.
# @exception ValueError Raised if s cannot be converted to boolean.
def str_to_bool(s):
    if isinstance(s, bytes):
        s = s.decode(gv.ENCODING)
    if s.lower() == "true":
        return True
    elif s.lower() == "false":
        return False
    else:
        raise ValueError("Cannot convert '{}' to bool".format(s))


## Convert boolean to string.
# @param b bool to convert.
# @return str value.
def bool_to_str(b):
    return "True" if b else "False"
