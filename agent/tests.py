from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from agent.zorin.workflow_nodes import (
    _resolve_followup_context,
    _route_open_task_to_other,
    routing_validator_node,
    task_router_node,
)
from agent.zorin.object_store import SessionObjectStore
from agent.zorin.info_manager import _postprocess_numeric_constraints


class WorkflowRoutingGuardsTests(SimpleTestCase):
    def test_structured_recommendation_query_does_not_resolve_previous_product_context(self):
        history = [
            {
                "role": "assistant",
                "metadata": {
                    "winner": {"name": "Gildan 5000", "short_code": "USG5000"},
                },
            }
        ]
        criteria = {
            "location_preference": "China",
            "max_price": 10.0,
            "max_lead_time": 5,
        }
        query = (
            "Tôi bắt đầu bán tại thị trường Trung Quốc, tôi muốn bán sản phẩm áo thun "
            "với chi phí khoảng $10, ship dưới 5 ngày, thì chọn partner nào để cung cấp đa dạng màu và SKU nào?"
        )

        with patch("agent.zorin.workflow_nodes._get_followup_resolver") as get_resolver:
            result = _resolve_followup_context(
                query=query,
                intent="recommend_product",
                criteria=criteria,
                history=history,
            )

        self.assertEqual(result, criteria)
        get_resolver.assert_not_called()

    def test_deictic_followup_still_resolves_from_history(self):
        history = [
            {
                "role": "assistant",
                "metadata": {
                    "winner": {"name": "Gildan 5000", "short_code": "USG5000"},
                },
            }
        ]
        resolver = Mock()
        resolver.resolve.return_value = {
            "should_resolve": True,
            "selected_indices": [1],
            "reason": "Follow-up refers to the previous product.",
        }

        with patch("agent.zorin.workflow_nodes._get_followup_resolver", return_value=resolver):
            result = _resolve_followup_context(
                query="Mẫu này có những partner nào?",
                intent="recommend_product",
                criteria={},
                history=history,
            )

        resolver.resolve.assert_called_once()
        self.assertEqual(result.get("skus"), ["USG5000"])
        self.assertEqual(result.get("product_names"), ["Gildan 5000"])
        self.assertTrue(result.get("resolved_from_history"))

    def test_structured_recommendation_query_does_not_route_to_other(self):
        criteria = {
            "location_preference": "China",
            "max_price": 10.0,
            "max_lead_time": 5,
        }
        query = (
            "Tôi bắt đầu bán tại thị trường Trung Quốc, tôi muốn bán sản phẩm áo thun "
            "với chi phí khoảng $10, ship dưới 5 ngày, thì chọn partner nào để cung cấp đa dạng màu và SKU nào?"
        )

        with patch("agent.zorin.workflow_nodes._get_other_task_manager") as get_manager:
            result = _route_open_task_to_other(
                query=query,
                intent="recommend_product",
                criteria=criteria,
                history=[],
            )

        self.assertEqual(result, criteria)
        get_manager.assert_not_called()


class ConstraintExtractionTests(SimpleTestCase):
    def test_postprocess_numeric_constraints_extracts_base_cost_and_roi(self):
        criteria = _postprocess_numeric_constraints(
            "Tôi muốn bán T-shirt cho thị trường Mỹ, giá vốn dưới $8, ROI trên 40%, margin trên 25%",
            {},
        )

        self.assertEqual(criteria["base_cost_max"], 8.0)
        self.assertEqual(criteria["target_roi_min"], 40.0)
        self.assertEqual(criteria["target_margin_min"], 25.0)
        self.assertTrue(criteria["budget_concern"])


class SessionObjectStoreTests(SimpleTestCase):
    def test_store_roundtrip_returns_copy(self):
        store = SessionObjectStore(ttl_seconds=60)
        snapshot = {"returned_objects": [{"source": "winner", "product": {"short_code": "USG5000"}}]}

        store.save_snapshot("session-1", snapshot)
        loaded = store.get_snapshot("session-1")
        loaded["returned_objects"][0]["product"]["short_code"] = "MUTATED"
        loaded_again = store.get_snapshot("session-1")

        self.assertEqual(loaded_again["returned_objects"][0]["product"]["short_code"], "USG5000")


class ReflectionReplanTests(SimpleTestCase):
    def test_task_router_honors_replanned_task_without_banlist(self):
        result = task_router_node({
            "intent": "other",
            "extracted_criteria": {"location_preference": "China"},
            "query": "T-shirt China under $10 ship under 5 days, which partner and SKU?",
            "conversation_history": [],
            "replanned_task": "recommend_product",
            "replanned_route": "data_agent",
        })

        self.assertEqual(result["task"], "recommend_product")
        self.assertEqual(result["zorin_route"], "data_agent")
        self.assertEqual(result["replanned_task"], "")
        self.assertNotIn("banned_tasks", result)

    def test_routing_validator_replans_instead_of_banning_task(self):
        state = {
            "query": "Tôi muốn bán T-shirt cho thị trường Trung Quốc, chi phí khoảng $10, ship dưới 5 ngày.",
            "intent": "recommend_product",
            "task": "other",
            "zorin_route": "data_agent",
            "extracted_criteria": {"location_preference": "China", "base_cost_max": 10.0, "max_lead_time": 5},
            "conversation_history": [],
            "missing_fields": [],
            "retry_count": 0,
            "max_retry_count": 3,
            "validation_reports": [],
            "reflection_trace": [],
        }

        with patch("agent.zorin.workflow_nodes._get_flow_validator") as get_validator:
            validator = Mock()
            validator.validate_routing.return_value = {
                "is_valid": False,
                "reason": "Task other does not match a structured recommendation query.",
                "missing_information": [],
            }
            validator.replan_task.return_value = {
                "task": "recommend_product",
                "route": "data_agent",
                "reason": "Structured hard-constraint query should be executed as recommend_product.",
            }
            get_validator.return_value = validator

            result = routing_validator_node(state)

        self.assertEqual(result["validator_next"], "data_agent")
        self.assertEqual(result["replanned_task"], "recommend_product")
        self.assertEqual(result["replanned_route"], "data_agent")
        self.assertEqual(result["retry_count"], 1)
        self.assertTrue(result["reflection_trace"])
        self.assertNotIn("banned_tasks", result)
