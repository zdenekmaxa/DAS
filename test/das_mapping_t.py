#!/usr/bin/env python
#pylint: disable-msg=C0301,C0103

"""
Unit test for DAS mappingdb class
"""

import os
import time
import unittest
from DAS.utils.das_config import das_readconfig
from DAS.utils.logger import PrintManager
from DAS.utils.utils import deepcopy
from DAS.core.das_mapping_db import DASMapping

from pymongo.connection import Connection

class testDASMapping(unittest.TestCase):
    """
    A test class for the DAS mappingdb class
    """
    def setUp(self):
        """
        set up DAS core module
        """
        debug    = 0
        self.db  = 'test_mapping.db'
        config   = deepcopy(das_readconfig())
        dburi    = config['mongodb']['dburi']
        logger   = PrintManager('TestDASMapping', verbose=debug)
        config['logger']  = logger
        config['verbose'] = debug
        dbname   = 'test_mapping'
        collname = 'db'
        config['mappingdb'] = dict(dburi=dburi, dbname=dbname, collname=collname)
        # add some maps to mapping db
        conn = Connection(dburi)
        conn.drop_database(dbname)
        coll = conn[dbname][collname]
        self.pmap = {"presentation": {"block":[{"ui": "Block name", "das": "block.name"}, 
        {"ui": "Block size", "das": "block.size"}]}}
        coll.insert(self.pmap)

        self.mgr = DASMapping(config)

    def tearDown(self):
        """Invoke after each test"""
        self.mgr.delete_db()

    def test_api(self):                          
        """test methods for api table"""
        self.mgr.delete_db()
        self.mgr.create_db()

        apiversion = 'DBS_2_0_8'
        url     = 'http://a.com'
        dformat = 'JSON'
        expire  = 100

        api = 'listRuns'
        params = { 'apiversion':apiversion, 'path' : 'required', 'api':api}
        rec = {'system' : 'dbs', 'urn':api, 'format':dformat, 'url':url,
            'params': params, 'expire':expire, "wild_card": "*",
            'daskeys' : [dict(key='run', map='run.run_number', pattern='')],
            'das2api' : [
                    dict(api_param='path', das_key='dataset', pattern=""),
            ]
        }
        self.mgr.add(rec)
        res = self.mgr.check_dasmap('dbs', api, 'run.bfield')
        self.assertEqual(False, res)
        res = self.mgr.check_dasmap('dbs', api, 'run.run_number')
        self.assertEqual(True, res)
        smap = {api: {'url':url, 'expire':expire, 'keys': ['run'], 
                'format': dformat, "wild_card":"*", 'cert':None, 'ckey': None,
                'params': {'path': 'required', 'api': api, 
                           'apiversion': 'DBS_2_0_8'}
                     }
        }

        rec = {'system':'dbs', 'urn': 'listBlocks', 'format':dformat,
          'url':url, 'expire': expire,
          'params' : {'apiversion': apiversion, 'api': 'listBlocks',
                      'block_name':'*', 'storage_element_name':'*',
                      'user_type':'NORMAL'},
          'daskeys': [
                 {'key':'block', 'map':'block.name', 'pattern':''},
                 ],
          'das2api': [
                 {'api_param':'storage_element_name', 
                  'das_key':'site', 
                  'pattern':"re.compile('([a-zA-Z0-9]+\.){2}')"},
                 {'api_param':'storage_element_name', 
                  'das_key':'site.se', 
                  'pattern':"re.compile('([a-zA-Z0-9]+\.){2}')"},
                 {'api_param':'block_name', 
                  'das_key':'block', 
                  'pattern':""},
                 {'api_param':'block_name', 
                  'das_key':'block.name', 
                  'pattern':""},
                 ]
        } 
        self.mgr.add(rec)


        system = 'dbs'
        api = 'listBlocks'
        daskey = 'block'
        primkey = 'block.name'
        api_input = 'block_name'

        res = self.mgr.list_systems()
        self.assertEqual(['dbs'], res)

        res = self.mgr.list_apis()
#        self.assertEqual([api], res)
        res.sort()
        self.assertEqual(['listBlocks', 'listRuns'], res)

        res = self.mgr.lookup_keys(system, daskey)
        self.assertEqual([primkey], res)

        value = ''
        res = self.mgr.das2api(system, daskey, value)
        self.assertEqual([api_input], res)

        # adding another params which default is None
        res = self.mgr.das2api(system, daskey, value, api)
        self.assertEqual([api_input], res)

        res = self.mgr.api2das(system, api_input)
        self.assertEqual([daskey, primkey], res)

        # adding notations
        notations = {'system':system, 
            'notations':[
                    {'notation':'storage_element_name', 'map':'se', 'api':''},
                    {'notation':'number_of_events', 'map':'nevents', 'api':''},
                        ]
        }
        self.mgr.add(notations)

        res = self.mgr.notation2das(system, 'number_of_events')
        self.assertEqual('nevents', res)

        # API keys
        res = self.mgr.api2daskey(system, api)
        self.assertEqual([daskey], res)

        # build service map
        smap.update({api: {'url':url, 'expire':expire, 'cert':None, 'ckey': None,
                'keys': ['block'], 'format':dformat, "wild_card": "*",
                'params': {'storage_element_name': '*', 'api':api, 
                           'block_name': '*', 'user_type': 'NORMAL', 
                           'apiversion': 'DBS_2_0_8'}
                     }
        })
        res = self.mgr.servicemap(system)
        self.assertEqual(smap, res)

    def test_presentation(self):                          
        """test presentation method"""
        self.mgr.create_db()
#        rec = {'presentation':{'block':['block.name', 'block.size'], 'size':['size.name']}}
#        self.mgr.add(rec)
        expect = self.pmap['presentation']['block']
        result = self.mgr.presentation('block')
        self.assertEqual(expect, result)

    def test_notations(self):                          
        """test notations method"""
        self.mgr.create_db()
        system = "test"
        rec = {'notations': [
        {"notation": "site.resource_element.cms_name", "map": "site.name", "api": ""},
        {"notation": "site.resource_pledge.cms_name", "map": "site.name", "api": ""},
        {"notation": "admin.contacts.cms_name", "map":"site.name", "api":""}
        ], "system": system}
        self.mgr.add(rec)
        expect = rec['notations']
        result = self.mgr.notations(system)[system]
        self.assertEqual(expect, result)

#
# main
#
if __name__ == '__main__':
    unittest.main()

