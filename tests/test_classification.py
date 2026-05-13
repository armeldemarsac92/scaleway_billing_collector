from decimal import Decimal
from unittest import TestCase

from billing_collector.domain.classification import BillingLineClassifier


class BillingLineClassifierTests(TestCase):
    def setUp(self):
        self.classifier = BillingLineClassifier()

    def test_classifies_support_gold_as_subscription_plan(self):
        classification = self.classifier.classify(
            category_name="Subscription",
            product_name="Support Level",
            resource_name="Gold",
            sku="/subscription/support/gold",
            unit="plan",
            value=Decimal("209.26"),
        )

        self.assertEqual(classification.line_type, "subscription")
        self.assertEqual(classification.usage_type, "plan")
        self.assertFalse(classification.burn_rate_eligible)

    def test_classifies_acceleration_agreement_as_contract(self):
        classification = self.classifier.classify(
            category_name="Contracts",
            product_name="Element E1",
            resource_name="ref Number : 062024-a7ec9296",
            sku="/billing/acceleration-agreement/element-e1",
            unit="EUR",
            value=Decimal("3971.75"),
        )

        self.assertEqual(classification.line_type, "contract")
        self.assertEqual(classification.usage_type, "monetary")
        self.assertFalse(classification.burn_rate_eligible)

    def test_classifies_runtime_resource_usage_as_burn_rate_eligible(self):
        classification = self.classifier.classify(
            category_name="Compute",
            product_name="DEV1-M",
            resource_name="DEV1-M - fr-par-1",
            sku="/compute/dev1_m/run_par1",
            unit="minute",
            value=Decimal("12.50"),
        )

        self.assertEqual(classification.line_type, "resource_usage")
        self.assertEqual(classification.usage_type, "runtime")
        self.assertTrue(classification.burn_rate_eligible)

    def test_classifies_storage_capacity_as_resource_usage_without_burn_rate(self):
        classification = self.classifier.classify(
            category_name="Storage",
            product_name="Block Storage Volume",
            resource_name="Block Storage Low Latency 5k IOPS - PAR1",
            sku="/storage/block/volume-low-latency-5k/fr-par-1",
            unit="gigabyte_hour",
            value=Decimal("111.54"),
        )

        self.assertEqual(classification.line_type, "resource_usage")
        self.assertEqual(classification.usage_type, "capacity")
        self.assertFalse(classification.burn_rate_eligible)

    def test_classifies_offer_deduction_as_credit(self):
        classification = self.classifier.classify(
            category_name="Serverless",
            product_name="Serverless Function Free Tier",
            resource_name="Offer deducted - Serverless Function Free Tier World Wide",
            sku="/offer/deducted/paas/faas/offer",
            unit="currency",
            value=Decimal("-0.02"),
        )

        self.assertEqual(classification.line_type, "credit")
        self.assertEqual(classification.usage_type, "currency")
        self.assertFalse(classification.burn_rate_eligible)

    def test_classifies_zero_value_free_tier_plan_as_marker(self):
        classification = self.classifier.classify(
            category_name="AI",
            product_name="Generative APIs Free Tier",
            resource_name="First 1M tokens for free",
            sku="/ai/generative_apis/consumption/offer",
            unit="plan",
            value=Decimal("0"),
        )

        self.assertEqual(classification.line_type, "free_tier_marker")
        self.assertEqual(classification.usage_type, "plan")
        self.assertFalse(classification.burn_rate_eligible)
