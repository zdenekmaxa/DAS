#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-

"""
DAS Query Language code. It consists of MongoParser who communicate with
DAS Analytics and DAS Mapping DBs to fetch registered DAS keys and store
DAS-QL to MongoDB-QL conversion. We use several helper functions to
tests integrity of DAS-QL queries, conversion routine from DAS-QL
syntax to MongoDB one.
"""

__revision__ = "$Id: qlparser.py,v 1.39 2010/02/22 21:01:25 valya Exp $"
__version__ = "$Revision: 1.39 $"
__author__ = "Valentin Kuznetsov"

import re
import time
import types
import datetime
import traceback

from itertools import groupby
from DAS.utils.utils import oneway_permutations, unique_list, add2dict
from DAS.utils.utils import getarg, genkey, adjust_value

import DAS.utils.jsonwrapper as json

DAS_OPERATORS = ['!=', '<=', '<', '>=', '>', '=', 
                 ' between ', ' nin ', ' in ', ' last ']
#                 ' not like ', ' like ', 
#                 ' between ', ' not in ', ' in ', ' last ']
MONGO_MAP = {
    '>':'$gt',
    '<':'$lt',
    '>=':'$gte',
    '<=':'$lte',
    'in':'$in',
    '!=':'$ne',
    'nin':'$nin',
}
def convert2date(value):
    """
    Convert input value to date range format expected by DAS.
    """
    msg = "Unsupported syntax for value of last operator"
    pat = re.compile('^[0-9][0-9](h|m)$')
    if  not pat.match(value):
        raise Exception(msg)
    oper = ' = '
    if  value.find('h') != -1:
        hour = int(value.split('h')[0])
        if  hour > 24:
            raise Exception('Wrong hour %s' % value)
        date1 = time.time() - hour*60*60
        date2 = time.time()
    elif value.find('m') != -1:
        minute = int(value.split('m')[0])
        if  minute > 60:
            raise Exception('Wrong minutes %s' % value)
        date1 = time.time() - minute*60
        date2 = time.time()
    else:
        raise Exception('Unsupported value for last operator')
    value = [date1, date2]
    return value

def das_dateformat(value):
    """Check if provided value in expected DAS date format."""
    pat = re.compile('[0-2]0[0-9][0-9][0-1][0-9][0-3][0-9]')
    if  pat.match(value): # we accept YYYYMMDD
        d = datetime.date(int(value[0:4]), # YYYY
                          int(value[4:6]), # MM
                          int(value[6:8])) # DD
        return time.mktime(d.timetuple())
    else:
        msg = 'Unacceptable date format'
        raise Exception(msg)

def mongo_exp(cond_list, lookup=False):
    """
    Convert DAS expression into MongoDB syntax. As input we take
    a dictionary of key, operator and value.
    """
    mongo_dict = {}
    for cond in cond_list:
        if  cond == '(' or cond == ')' or cond == 'and':
            continue
        key  = cond['key']
        val  = cond['value']
        oper = cond['op'].strip()
        if  type(val) is types.StringType and val.find('%') != -1:
            val = val.replace('%', '*')
        if  mongo_dict.has_key(key):
            existing_value = mongo_dict[key]
            if  type(existing_value) is types.DictType:
                if  existing_value.has_key('$all'):
                    val = existing_value['$all'] + [val]
                    mongo_dict[key] = {'$all' : val}
                else:
                    existing_value.update({MONGO_MAP[oper]:val})
                    mongo_dict[key] = existing_value
            else:
                val = [existing_value, val]
                mongo_dict[key] = {'$all' : val}
        else:
            if  MONGO_MAP.has_key(oper):
                if  mongo_dict.has_key(key):
                    mongo_value = mongo_dict[key]
                    mongo_value[MONGO_MAP[oper]] = val
                    mongo_dict[key] = mongo_value
                else:
                    mongo_dict[key] = {MONGO_MAP[oper] : val}
            elif oper == 'like':
                if  lookup:
                    # for expressions: *val* use pattern .*val.*
                    pat = re.compile(val.replace('*', '.*'))
                    mongo_dict[key] = pat
                else:
                    mongo_dict[key] = val
            elif oper == 'not like':
                # TODO, reverse the following:
                msg = 'Operator not like is not supported yet'
                raise Exception(msg)
                # for expressions: *val* use pattern .*val.*
#                pat = re.compile(val.replace('*', '.*'))
#                mongo_dict[key] = pat
            elif oper == '=':
                mongo_dict[key] = val
            elif oper == 'between':
                mongo_dict[key] = {'$in' : [i for i in range(val[0], val[1])]}
            elif oper == 'last':
                mongo_dict[key] = val
            else:
                msg = 'Not supported operator %s' % oper
                raise Exception(msg)
    return mongo_dict

def find_index(qlist, tag):
    """Find index of tag in a list qlist"""
    try:
        return qlist.index(tag)
    except:
        return -1

def getnextcond(uinput):
    """
    Find out next where clause condition. It only understand conditions
    between and and or boolean operators
    """
    obj_and = 'and'
    obj_or  = 'or'
    qlist   = [name.strip() for name, group in groupby(uinput.split())]
    idx_and = find_index(qlist, 'and')
    idx_or  = find_index(qlist, 'or')
    idx_between = find_index(qlist, 'between')
    if  idx_and - idx_between == 2 and idx_between != -1:
        idx_and = find_index(qlist[idx_and+1:], 'and')
    if  idx_or  - idx_between == 2 and idx_between != -1:
        idx_or  = find_index(qlist[idx_or+1:], 'or')
    res = None, None, None
    if  idx_and == -1 and idx_or == -1:
        res = None, None, uinput
    if  idx_and != -1 and idx_or != -1:
        if  idx_and < idx_or:
            res = ' '.join(qlist[0:idx_and]), obj_and, \
                  ' '.join(qlist[idx_and+1:len(qlist)])
        else:
            res = ' '.join(qlist[0:idx_or]), obj_or, \
                  ' '.join(qlist[idx_or+1:len(qlist)])
    if  idx_and != -1 and idx_or == -1:
        res = ' '.join(qlist[0:idx_and]), obj_and, \
              ' '.join(qlist[idx_and+1:len(qlist)])
    if  idx_and == -1 and idx_or != -1:
        res = ' '.join(qlist[0:idx_or]), obj_or, \
              ' '.join(qlist[idx_or+1:len(qlist)])
    return res

def getconditions(uinput):
    """
    Find out where clause conditions and store them in output dictionary
    """
    sublist = uinput.split(' where ')
    rdict   = {}
    if  len(sublist)>1:
        substr = ' '.join(sublist[1:])
        counter = 0
        while 1:
            cond, oper, rest = getnextcond(substr)
            substr = rest
            if  not cond:
                break
            rdict['q%s' % counter] = cond
            counter += 1
        if  substr:
            rdict['q%s' % counter] = substr
    return rdict

def findbracketobj(uinput, dbs_func=True):
    """
    Find out bracket object, e.g. ((test or test) or test)
    """
    if  dbs_func:
        if  uinput.find('count(') != -1 or uinput.find('sum(') != -1:
            return
    left = uinput.find('(')
    robj = ''
    if  left != -1:
        rcount = 0
        for char in uinput[left:]:
            robj += char
            if  char == '(':
                rcount += 1
            if  char == ')':
                rcount -= 1
            if  char == ')' and not rcount:
                break
        if  rcount:
            msg = "Object '%s' has un-equal number of left & right brackets" \
                % uinput
            raise Exception(msg)
    return robj
        
class MongoParser(object):
    """
    DAS Mongo query parser. 
    """
    def __init__(self, config):
        self.map = config['dasmapping']
        self.analytics = config['dasanalytics']
        self.daskeys = self.map.daskeys()
        self.operators = DAS_OPERATORS

        if  not self.map.check_maps():
            msg = "No DAS maps found in MappingDB"
            raise Exception(msg)

    def decompose(self, query):
        """Extract selection keys and conditions from input query"""
        skeys = getarg(query, 'fields', [])
        cond  = getarg(query, 'spec', {})
        return skeys, cond

    def requestquery(self, query, add_to_analytics=True):
        """
        Query analyzer which form request query to DAS from a free text-based form.
        Return MongoDB request query.
        """
        mapreduce = []
        if  query and type(query) is types.StringType:
            if  query.find("|") != -1:
                split_results = query.split("|")
                query = split_results[0]
                mapreduce = [i.strip() for i in split_results[1:]]
            query = query.strip()
            if  query[0] == "{" and query[-1] == "}":
                mongo_query = json.loads(query)
                if  mongo_query.keys() != ['fields', 'spec']:
                    raise Exception("Invalid MongoDB query %s" % query)
                if  add_to_analytics:
                    self.analytics.add_query(query, mongo_query)
                return mongo_query
        findbracketobj(query) # check brackets in a query
        skeys = []
        query = query.strip()
        query = query.replace(",", " ")
        def fix_operator(query, pos):
            """Add spaces around DAS operators in a query"""
            idx_pos  = len(query)
            oper_pos = ""
            for oper in self.operators:
                idx = query[pos:len(query)].find(oper)
                if  idx != -1 and idx < idx_pos and idx > pos:
                    idx_pos = idx
                    oper_pos = oper
            if  idx_pos >= len(query):
                return None, None
            if  idx_pos != -1:
                idx = idx_pos
                oper = oper_pos
                newpos = pos + idx + len(oper)
                rest = query[pos+idx+len(oper):len(query)]
                newquery = query[:pos+idx] + ' ' + oper + ' ' + rest
                return newquery, newpos+2
            return None, None
        pos   = 0
        ccc   = 0
        while True:
            copy = query
            query, pos = fix_operator(query, pos)
            if  not query:
                query = copy
                break
            ccc += 1
            if  ccc > 100: # just pre-caution to avoid infinitive loop
                break
        slist = query.split()
        idx   = 0
        daskeys = ['system', 'date'] # two reserved words
        for val in self.daskeys.values():
            for item in val:
                daskeys.append(item)
        condlist = []
        # strip operators while we will match words against them
        operators = [o.strip() for o in self.operators]
        while True:
            if  idx >= len(slist):
                break
            word = slist[idx].strip()
            if  word in daskeys: # look-up for selection keys
                try:
                    next_word = slist[idx+1]
                    if  next_word not in self.operators and word not in skeys:
                        skeys.append(word)
                except:
                    pass
                if  word == slist[-1] and word not in skeys: # last word
                    skeys.append(word)
            elif word in operators: # look-up conditions
                oper = word
                prev_word = slist[idx-1]
                next_word = slist[idx+1]
                if  word in ['in', 'nin']:
                    first = next_word
                    if  first.find('[') == -1:
                        raise Exception('No open bracket [ found in query expression')
                    arr = []
                    found_last = False
                    for item in slist[idx+1:]:
                        if  item.find(']') != -1:
                            found_last = True
                        val = item.replace('[', '').replace(']', '')
                        if  val:
                            arr.append(val)
                    if  not found_last:
                        raise Exception('No closed bracket ] found in query expression')
                    value = arr
                elif word == 'last':
                    value = convert2date(next_word)
                    cdict = dict(key='date', op='in', value=value)
                    condlist.append(cdict)
                    value = None
                else:
                    value = next_word
                if  prev_word == 'date':
                    if  word != 'last': # we already converted date
                        if  type(value) is types.StringType:
                            value = [das_dateformat(value), time.time()]
                        elif type(value) is types.ListType:
                            try:
                                value1 = das_dateformat(value[0])
                                value2 = das_dateformat(value[1])
                                value  = [value1, value2]
                            except:
                                msg = "Unable to parse %s" % value
                                raise Exception(msg)
                    cdict = dict(key='date', op='in', value=value)
                    condlist.append(cdict)
                    value = None
                idx += 1
                if  not value:
                    continue
                key = prev_word
                value = adjust_value(value)
                for system in self.map.list_systems():
                    for api, mapkey in self.map.find_mapkey(system, key):
                        prim_key = self.map.primary_key(system, api)
                        lkeys = self.map.lookup_keys(system, key, 
                                    api=api, value=value)
                        add = False
                        if  skeys:
                            if  prim_key in skeys:
                                add = True
                        else:
                            if  key == prim_key:
                                add = True
                        if  add:
                            for nkey in lkeys:
                                if  nkey != 'date':
                                    cdict = dict(key=nkey, op=oper, value=value)
                                    if  cdict not in condlist:
                                        condlist.append(cdict)
#                    try:
#                        lkeys = self.map.lookup_keys(system, key, 
#                                                     value=value)
#                        for nkey in lkeys:
#                            if  nkey != 'date':
#                                cdict = dict(key=nkey, op=oper, value=value)
#                                if  cdict not in condlist:
#                                    condlist.append(cdict)
#                    except:
#                        pass
            else:
                if  word not in skeys:
                    skeys.append(word)
            idx += 1
        spec = mongo_exp(condlist)
        # loop over skeys and add '*' value for each key into spec
        for key in skeys:
            insert = 0
            for system in self.map.list_systems():
                try:
                    mapkeys = self.map.find_mapkey(system, key)
                    for urn, mapkey in mapkeys:
                        entity = mapkey.split('.')[0]
                        if  not spec.has_key(mapkey) and key == entity:
                            spec[mapkey] = '*'
                            insert = 1
#                    lkeys = self.map.lookup_keys(system, key)
#                    for nkey in lkeys:
#                        if  not spec.has_key(nkey):
#                            spec[nkey] = '*'
#                            insert = 1
                except:
                    pass
            if  not insert:
                spec[key] = '*'
        mongo_query = dict(fields=None, spec=spec)
        # add mapreduce if it exists
        if  mapreduce:
            mongo_query['mapreduce'] = mapreduce
        if  add_to_analytics:
            self.analytics.add_query(query, mongo_query)
        return mongo_query

    def services(self, query):
        """Find out DAS services to use for provided query"""
        skeys, cond = self.decompose(query)
        if  not skeys:
            skeys = []
        if  type(skeys) is types.StringType:
            skeys = [skeys]
        slist = []
        # look-up services from Mapping DB
        for key in skeys + [i for i in cond.keys()]:
            for service, keys in self.daskeys.items():
                daskeys = self.map.find_daskey(service, key)
                if  set(keys) & set(daskeys) and service not in slist:
                    slist.append(service)
        return slist

    def service_apis_map(self, query):
        """
        Find out which APIs correspond to provided query.
        Return a map of found services and their apis.
        """
        skeys, cond = self.decompose(query)
        if  not skeys:
            skeys = []
        if  type(skeys) is types.StringType:
            skeys = [skeys]
        adict = {}
        mapkeys = [key for key in cond.keys()]
        services = [srv for srv in self.map.list_systems()]
        for srv in services:
            alist = self.map.list_apis(srv)
            for api in alist:
                daskeys = self.map.api_info(api)['daskeys']
                maps = [r['map'] for r in daskeys]
                if  set(mapkeys) & set(maps) == set(mapkeys): 
                    if  adict.has_key(srv):
                        new_list = adict[srv] + [api]
                        adict[srv] = list( set(new_list) )
                    else:
                        adict[srv] = [api]
        return adict

    def params(self, query):
        """
        Return dictionary of parameters to be used in DAS Core:
        selection keys, conditions and services.
        """
        skeys, cond = self.decompose(query)
        services = []
        for srv in self.services(query):
            if  srv not in services:
                services.append(srv)
        return dict(selkeys=skeys, conditions=cond, services=services)

