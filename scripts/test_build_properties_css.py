import unittest

import tinycss2

from build_properties_css import OUTPUT, build, subset


class PropertiesCssTests(unittest.TestCase):
    def render(self, css):
        return subset(tinycss2.parse_stylesheet(css), {'cid-present'})

    def test_only_absent_section_anchors_are_removed(self):
        css = ('.cid-absent:hover .child {color:red}'
               '.cid-present:hover .child {color:blue}'
               '.global {color:green}'
               ':is(.cid-absent,.global) {display:block}')
        result = self.render(css)
        self.assertNotIn('color:red', result)
        for value in ['color:blue', 'color:green', ':is(.cid-absent,.global)']:
            self.assertIn(value, result)

    def test_mixed_selector_lists_are_kept(self):
        self.assertIn('color:red', self.render('.cid-absent, .global {color:red}'))
        self.assertNotIn('color:red', self.render('.cid-absent, .cid-other {color:red}'))

    def test_responsive_and_menu_states_survive(self):
        result = self.render('@media(max-width:991px){'
                             '.cid-absent {color:red}'
                             '.cid-present .opened {color:blue}}')
        self.assertIn('@media', result)
        self.assertIn('.opened', result)
        self.assertNotIn('color:red', result)
        self.assertEqual('', self.render('@media(print){.cid-absent{color:red}}'))

    def test_duplicate_rules_keep_last_cascade_position(self):
        result = self.render('.a{color:red}.b{color:blue}.a{color:red}')
        self.assertEqual('.b{color:blue}\n.a{color:red}', result)

    def test_ancillary_rules_are_preserved(self):
        self.assertIn('@keyframes', self.render('@keyframes spin{to{transform:rotate(1turn)}}'))

    def test_generated_asset_is_current(self):
        self.assertEqual(OUTPUT.read_bytes(), build())


if __name__ == '__main__':
    unittest.main()
