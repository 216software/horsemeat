# vim: set expandtab ts=4 sw=4 filetype=python fileencoding=utf8:

import unittest

from horsemeat import configwrapper

class SubclassConfigWrapper(configwrapper.ConfigWrapper):

    @property
    def dispatcher_class(self):
        return None

class TestSetDefault(unittest.TestCase):

    def test1(self):

        cw1 = SubclassConfigWrapper({})
        cw1.set_as_default()

        cw2 = SubclassConfigWrapper.get_default()

        self.assertIs(cw1, cw2)

    def test2(self):

        cw1 = SubclassConfigWrapper({})
        cw1.set_as_default()

        cw2 = configwrapper.ConfigWrapper.get_default()

        self.assertIs(cw1, cw2)

    def tearDown(self):

        configwrapper.ConfigWrapper.default_instance = None
        SubclassConfigWrapper.default_instance = None

class Test1(unittest.TestCase):

    def test1(self):

        cw = SubclassConfigWrapper({})

        cw.j


if __name__ == "__main__":
    unittest.main()
