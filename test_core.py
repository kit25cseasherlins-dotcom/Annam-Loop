import os, time, unittest
os.environ["DEMO_SECONDS"] = "1"
import core

class Flow(unittest.TestCase):
    def setUp(self): core.LISTINGS.clear()

    def test_unknown_food_rejected(self):
        self.assertFalse(core.log_surplus("A", "Saibaba Colony", "xyzfood", 5)["ok"])

    def test_claim_flow(self):
        os.environ["DEMO_SECONDS"] = "60"
        r = core.log_surplus("Canteen", "Saibaba Colony", "biryani", 20)["listing"]
        self.assertEqual(core.find_nearby_surplus("saibaba colony")["count"], 1)
        self.assertTrue(core.claim_food(r["id"], "Student")["ok"])
        self.assertFalse(core.claim_food(r["id"], "Other")["ok"])
        self.assertEqual(core.get_impact_stats()["rescued_kg"], 8.0)

    def test_expiry_to_biogas(self):
        os.environ["DEMO_SECONDS"] = "1"
        core.log_surplus("Mess", "Peelamedu", "sambar", 10, "kg")
        time.sleep(1.2)
        self.assertEqual(core.find_nearby_surplus("Peelamedu")["count"], 0)
        w = core.get_waste_by_region("Peelamedu")
        self.assertEqual(w["total_kg"], 10.0)
        print(w["spoken_message"])
        self.assertEqual(core.accept_waste_pickup("Peelamedu", "BioGas Co")["total_kg"], 10.0)
        self.assertEqual(core.get_waste_by_region("Peelamedu")["count"], 0)

if __name__ == "__main__":
    unittest.main()
