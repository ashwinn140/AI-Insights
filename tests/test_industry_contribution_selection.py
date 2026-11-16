from pathlib import Path
import unittest


class IndustryContributionSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).parents[1] / "app" / "classifications.html").read_text()

    def test_default_industry_is_only_chosen_on_first_load(self):
        self.assertIn("industrySelectionInitialized=false", self.html)
        self.assertIn("if(!industrySelectionInitialized){selectedTrendIndustry=ranked.find(item=>item.name!=='Unclassified')?.name||'';industrySelectionInitialized=true;}", self.html)

    def test_clicking_selected_contribution_or_table_row_clears_selection(self):
        self.assertGreaterEqual(self.html.count("selectedTrendIndustry=selectedTrendIndustry===item.name?'':item.name"), 2)

    def test_clearing_selection_resets_vertical_and_contributor_panels(self):
        self.assertIn("function clearIndustrySelectionDisplay()", self.html)
        self.assertIn("clearIndustrySelectionDisplay();", self.html)
        self.assertIn("Choose an industry to see its contributors and underlying records.", self.html)


if __name__ == "__main__":
    unittest.main()
