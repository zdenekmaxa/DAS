#!/usr/bin/env python
#pylint: disable-msg=c0301,c0103

"""
unit test for logger module
"""

import os
import unittest
from DAS.utils.logger import DASLogger

class testDASLogger(unittest.TestCase):
    """
    A test class for the DAS logger module
    """
    def setUp(self):
        """
        set up DAS core module
        """
        debug = 0
        self.logfile = '/tmp/das.log'
        self.daslogger = DASLogger()

    def remove(self):
        """
        Removes DAS log file
        """
        if  os.path.isfile(self.logfile):
            os.remove(self.logfile)
        self.daslogger = DASLogger()

    def logcontent(self):
        """
        Return DAS log content
        """
        lines = open(self.logfile, 'r').read()
        return lines

    def test_logger(self):                          
        """test DAS logger methods"""
        self.remove()
        self.daslogger.info('test')
        result = self.logcontent()
        expect = ''
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(0)
        self.daslogger.info('test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = ''
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(1)
        self.daslogger.info('test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = '- DAS - INFO - test'
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(2)
        self.daslogger.info('test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = '- DAS - INFO - test'
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(1)
        self.daslogger.debug('test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = ''
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(2)
        self.daslogger.debug('test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = '- DAS - DEBUG - test'
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(0)
        self.daslogger.error('error test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = '- DAS - ERROR - error test'
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(2)
        self.daslogger.error('error test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = '- DAS - ERROR - error test'
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(0)
        self.daslogger.warning('test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = '- DAS - WARNING - test'
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(0)
        self.daslogger.exception('test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = '- DAS - ERROR - test'
        self.assertEqual(expect, result)

        self.remove()
        self.daslogger.level(0)
        self.daslogger.critical('test')
        result = ' '.join(self.logcontent().split()[2:])
        expect = '- DAS - CRITICAL - test'
        self.assertEqual(expect, result)

#
# main
#
if __name__ == '__main__':
    unittest.main()