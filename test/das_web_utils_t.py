#!/usr/bin/env python
#pylint: disable-msg=C0301,C0103

"""
Unit test for DAS wew utils module
"""

import json
import plistlib
import unittest

from pymongo.connection import Connection

from DAS.web.utils import wrap2dasxml, wrap2dasjson, json2html, quote
from DAS.web.utils import free_text_parser

class testDASWebUtils(unittest.TestCase):
    """
    A test class for the DAS web utils module
    """
    def setUp(self):
        """
        set up DAS core module
        """
        debug = 0

    def testDASXML(self):
        """test quote function"""
        data = 1
        result = quote(data)
        expect = '1'
        self.assertEqual(expect, result)
        
        data = '1'
        result = quote(data)
        expect = '1'
        self.assertEqual(expect, result)
        
        data = 'vk test'
        result = quote(data)
        expect = 'vk%20test'
        self.assertEqual(expect, result)
        
    def testDASXML(self):
        """test wrap2dasxml function"""
        data = {'test': {'foo':1}}
        expect = wrap2dasxml(data)
        result = plistlib.writePlistToString(data)
        self.assertEqual(expect, result)

    def testDASJSON(self):
        """test wrap2dasjson function"""
        data = {'test': {'foo': 1}}
        expect = wrap2dasjson(data)
        result = json.dumps(data)
        self.assertEqual(expect, result)

    def testJSON2HTML(self):
        """test json2html function"""
        data = {'test': {'foo': 1}}
        expect = json2html(data)
        result = '{\n <code class="key">"test"</code>: {\n    <code class="key">"foo"</code>: <code class="number">1</code>\n   }\n}'
        self.assertEqual(expect, result)

    def test_free_text_parser(self):
        """test free_text_parser function"""
        pairs = [("Zee CMSSW_4_*", "dataset dataset=*Zee* release=CMSSW_4_*"),
                 ("Zee mc", "dataset dataset=*Zee* datatype=mc"),
                 ("160915 CMSSW_4_*", "run run=160915 release=CMSSW_4_*"),
                 ("/abc.root CMSSW_2_0*", "file file=/abc.root release=CMSSW_2_0*"),
                 ("4_1 Zee", "dataset release=CMSSW_4_1* dataset=*Zee*"),
                 ("Zee /a/b/c#123", "dataset dataset=*Zee* block=/a/b/c#123"),
                 ("MC CMSSW_4_* /Zee", "dataset datatype=MC release=CMSSW_4_* dataset=/Zee*"),
                 ("gen-sim-reco", "tier tier=*gen-sim-reco*"),
                 ("raw-digi", "tier tier=*raw-digi*")]
        daskeys=['dataset', 'datatype', 'run', 'release', 'block', 'file']
        for uinput, dasquery in pairs:
            result = free_text_parser(uinput, daskeys)
            self.assertEqual(dasquery, result)
#
# main
#
if __name__ == '__main__':
    unittest.main()


