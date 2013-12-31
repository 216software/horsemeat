# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import unittest

from horsemeat import configwrapper

class SubclassConfigWrapper(configwrapper.ConfigWrapper):
    pass


class TestSetDefault(unittest.TestCase):

    def test1(self):

        cw1 = configwrapper.ConfigWrapper({})
        cw1.set_as_default()

        cw2 = configwrapper.ConfigWrapper.get_default()

        self.assertIs(cw1, cw2)

    def test2(self):

        cw1 = SubclassConfigWrapper({})
        cw1.set_as_default()

        cw2 = configwrapper.ConfigWrapper.get_default()

        self.assertIs(cw1, cw2)

    def tearDown(self):

        configwrapper.ConfigWrapper.default_instance = None
        SubclassConfigWrapper.default_instance = None

if __name__ == "__main__":
    unittest.main()
