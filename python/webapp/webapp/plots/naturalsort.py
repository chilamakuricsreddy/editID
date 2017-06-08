import re

# See https://nedbatchelder.com/blog/200712/human_sorting.html

def alphanum_key(s):
    return [int(c) if c.isdigit() else c for c in re.split('([0-9]+)', s)] 

def natural_sort(l):
    """ Sort the given list in the way that humans expect.
    """
    l.sort(key=alphanum_key)