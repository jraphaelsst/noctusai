"""Unit tests for the Mailing segmentation service (M3 — ai-expansion Phase 8)."""
import pytest
from unittest.mock import AsyncMock, patch


class TestBuildContactText:

    def test_with_full_fields(self):
        from app.services.segmentation_service import _build_contact_text
        text = _build_contact_text({
            "id": "x",
            "email": "a@b.com",
            "nome": "Ana",
            "empresa": "ACME",
            "tags": ["vip", "br"],
            "custom_fields": {"plan": "pro"},
        })
        assert "nome=Ana" in text
        assert "empresa=ACME" in text
        assert "vip" in text
        assert "plan:pro" in text

    def test_falls_back_to_email_only(self):
        from app.services.segmentation_service import _build_contact_text
        text = _build_contact_text({"id": "x", "email": "a@b.com"})
        assert text == "email=a@b.com"


class TestGreedyCluster:

    def test_separates_distant_vectors(self):
        from app.services.segmentation_service import _greedy_cluster
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.99, 0.01, 0.0],   # close to #0
            [0.0, 1.0, 0.0],     # very far from #0
            [0.0, 0.99, 0.01],   # close to #2
        ]
        assignments = _greedy_cluster(embeddings, threshold=0.85, max_segments=8)
        assert assignments[0] == assignments[1]
        assert assignments[2] == assignments[3]
        assert assignments[0] != assignments[2]

    def test_max_segments_caps_creation(self):
        from app.services.segmentation_service import _greedy_cluster
        # 5 mutually orthogonal-ish vectors but max_segments=2 → must collapse.
        embeddings = [[1, 0], [0, 1], [-1, 0], [0, -1], [0.5, 0.5]]
        assignments = _greedy_cluster(embeddings, threshold=0.99, max_segments=2)
        assert len(set(assignments)) <= 2


class TestSegmentContacts:

    @pytest.mark.asyncio
    async def test_happy_path_returns_one_output_per_contact(self):
        from app.services import segmentation_service

        # Two distinct embedding clusters.
        emb_responses = [
            [1.0, 0.0, 0.0],
            [0.99, 0.05, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.98, 0.02],
        ]
        canned_label = "LABEL: Clientes ativos\nCHIP: ATIVOS"

        with patch(
            "app.services.segmentation_service.generate_embedding",
            new_callable=AsyncMock,
            side_effect=emb_responses,
        ), patch(
            "app.services.segmentation_service.chat_completion",
            new_callable=AsyncMock,
            return_value=canned_label,
        ):
            outputs = await segmentation_service.segment_contacts(
                contacts=[
                    {"id": "c1", "email": "a@x", "tags": ["vip"]},
                    {"id": "c2", "email": "b@x", "tags": ["vip"]},
                    {"id": "c3", "email": "c@x", "tags": ["churn"]},
                    {"id": "c4", "email": "d@x", "tags": ["churn"]},
                ],
                threshold=0.85,
                max_segments=4,
            )
        assert len(outputs) == 4
        for o in outputs:
            assert o["kind"] == "classification"
            assert o["chip"] == "ATIVOS"
            assert o["label"] == "Clientes ativos"
            assert o["prompt_version"] == "mailing-segment@v1"
            assert "_contact_id" in o
            assert "cluster" in o["metadata"]

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_empty_outputs(self):
        from app.services import segmentation_service
        with patch(
            "app.services.segmentation_service.generate_embedding",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM not configured"),
        ), patch(
            "app.services.segmentation_service.chat_completion",
            new_callable=AsyncMock,
        ) as chat_mock:
            outputs = await segmentation_service.segment_contacts(
                contacts=[{"id": "c1", "email": "a@x"}],
            )
        assert len(outputs) == 1
        assert outputs[0]["label"] == "indisponível"
        # No naming call when embeddings unavailable.
        chat_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_naming_failure_falls_back_to_segment_n(self):
        from app.services import segmentation_service
        with patch(
            "app.services.segmentation_service.generate_embedding",
            new_callable=AsyncMock,
            return_value=[1.0, 0.0],
        ), patch(
            "app.services.segmentation_service.chat_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down for naming"),
        ):
            outputs = await segmentation_service.segment_contacts(
                contacts=[
                    {"id": "c1", "email": "a@x"},
                    {"id": "c2", "email": "b@x"},
                ],
            )
        assert len(outputs) == 2
        assert outputs[0]["label"] == "Segmento 1"
        assert outputs[0]["chip"] == "SEG 1"

    @pytest.mark.asyncio
    async def test_empty_contact_list_short_circuits(self):
        from app.services import segmentation_service
        with patch(
            "app.services.segmentation_service.generate_embedding",
            new_callable=AsyncMock,
        ) as emb_mock, patch(
            "app.services.segmentation_service.chat_completion",
            new_callable=AsyncMock,
        ) as chat_mock:
            outputs = await segmentation_service.segment_contacts(contacts=[])
        assert outputs == []
        emb_mock.assert_not_called()
        chat_mock.assert_not_called()
