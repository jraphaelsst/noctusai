"""``/api/studio/agents/{key}/learnings`` (Agent Packages §H1/§H2) — push with
row_sha dedupe, review by an admin user only, org + kind isolation."""
from __future__ import annotations

import pytest

from app.stores.agent_packages import learning_row_sha
from tests.routers.conftest import DEFAULT_USER_ID, seed_org_role
from tests.studio.pkg.conftest import OTHER_ORG

URL = "/api/studio/agents/mobile-dev/learnings"


def row(data="2026-10-03", texto="Nunca confiar no AsyncStorage para tokens.", tipo="pitfall", **kw):
    return {"data": data, "tipo": tipo, "texto": texto, "evidencia": "PR #12", "status": "novo", **kw}


def push(pkg, rows, *, project="limiar-app", scopes=("learnings:write",), url=URL):
    body = {"project_slug": project, "rows": rows}
    if scopes is None:
        return pkg.post(url, json=body)
    with pkg.as_token(*scopes):
        return pkg.post(url, json=body)


@pytest.fixture
def advisor(pkg):
    pkg.advisor()
    return pkg


class TestAuthBoundary:
    def test_push_without_credential_is_401(self, advisor):
        assert advisor.rt.client.raw().post(URL, json={"project_slug": "x", "rows": [row()]}).status_code == 401

    @pytest.mark.parametrize("scopes", [(), ("packages:read",), ("project-knowledge:write",), ("learnings:read",)])
    def test_push_with_the_wrong_scope_is_403_scope_missing(self, advisor, scopes):
        resp = push(advisor, [row()], scopes=scopes)
        assert resp.status_code == 403
        assert resp.json()["code"] == "scope_missing"

    def test_list_needs_learnings_read_for_a_token(self, advisor):
        with advisor.as_token("learnings:write"):
            resp = advisor.get(URL)
        assert resp.status_code == 403 and resp.json()["code"] == "scope_missing"
        with advisor.as_token("learnings:read"):
            assert advisor.get(URL).status_code == 200

    def test_list_without_credential_is_401(self, advisor):
        assert advisor.rt.client.raw().get(URL).status_code == 401

    def test_review_is_admin_user_only_a_token_is_403_user_required(self, advisor):
        new = push(advisor, [row()]).json()["novos"][0]["id"]
        with advisor.as_token("learnings:write", "learnings:read", "packages:read", "project-knowledge:write"):
            resp = advisor.patch(f"{URL}/{new}", json={"status": "aceito", "nota": "revisado pelo dono"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "user_required"

    def test_review_without_credential_is_401(self, advisor):
        assert advisor.rt.client.raw().patch(f"{URL}/{advisor.rt.user_id}", json={"status": "aceito", "nota": "revisado pelo dono"}).status_code == 401

    def test_review_by_a_non_admin_member_is_403_role_missing(self, advisor):
        new = push(advisor, [row()]).json()["novos"][0]["id"]
        seed_org_role(advisor.rt.client, role="member")
        resp = advisor.patch(f"{URL}/{new}", json={"status": "aceito", "nota": "revisado pelo dono"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_missing"

    def test_token_of_another_org_is_404(self, advisor):
        with advisor.as_token("learnings:write", org_id=OTHER_ORG):
            resp = advisor.post(URL, json={"project_slug": "limiar-app", "rows": [row()]})
        assert resp.status_code == 404

    def test_runtime_agent_is_404(self, pkg):
        pkg.rt.make_agent("isa")
        resp = push(pkg, [row()], url="/api/studio/agents/isa/learnings")
        assert resp.status_code == 404
        assert resp.json()["code"] == "agent_not_found"


class TestPush:
    def test_new_rows_are_stored_with_the_h1_identity(self, advisor):
        resp = push(advisor, [row(), row(texto="Preferir expo-secure-store.", tipo="prática")])
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert (out["recebidas"], out["novas"], out["duplicadas"]) == (3 - 1, 2, 0)
        assert {n["row_sha"] for n in out["novos"]} == {
            learning_row_sha("2026-10-03", "Nunca confiar no AsyncStorage para tokens."),
            learning_row_sha("2026-10-03", "Preferir expo-secure-store."),
        }
        listed = advisor.get(URL).json()["items"]
        assert {i["status"] for i in listed} == {"novo"}
        assert {i["project_slug"] for i in listed} == {"limiar-app"}

    def test_repush_dedupes_by_row_sha_and_returns_no_new_ids(self, advisor):
        first = push(advisor, [row()]).json()
        again = push(advisor, [row()]).json()
        assert first["novas"] == 1
        assert (again["novas"], again["duplicadas"], again["novos"]) == (0, 1, [])
        assert len(advisor.get(URL).json()["items"]) == 1

    def test_identity_ignores_whitespace_and_the_other_columns(self, advisor):
        push(advisor, [row()])
        same = row(texto="Nunca   confiar no\nAsyncStorage para tokens. ", tipo="armadilha", evidencia="outra", status="absorvido")
        out = push(advisor, [same]).json()
        assert (out["novas"], out["duplicadas"]) == (0, 1)

    def test_a_repeated_row_inside_one_push_is_stored_once(self, advisor):
        out = push(advisor, [row(), row()]).json()
        assert (out["recebidas"], out["novas"], out["duplicadas"]) == (2, 1, 1)

    def test_a_different_date_is_a_different_learning(self, advisor):
        out = push(advisor, [row(), row(data="2026-10-04")]).json()
        assert out["novas"] == 2

    def test_a_matching_client_row_sha_is_accepted_a_wrong_one_is_422(self, advisor):
        good = row()
        good["row_sha"] = learning_row_sha(good["data"], good["texto"])
        assert push(advisor, [good]).status_code == 200
        bad = row(texto="outro texto", row_sha="0" * 64)
        resp = push(advisor, [bad])
        assert resp.status_code == 422 and resp.json()["code"] == "row_sha_mismatch"

    def test_tipo_and_status_are_case_insensitive_h1_vocabulary(self, advisor):
        assert push(advisor, [row(tipo="Decision", status="Promoted")]).status_code == 200

    @pytest.mark.parametrize("patch", [
        {"tipo": "opinion"}, {"status": "aceito"}, {"texto": ""}, {"texto": "x" * 8001}, {"data": ""}, {"extra": 1},
    ])
    def test_invalid_rows_are_422(self, advisor, patch):
        assert push(advisor, [row(**patch)]).status_code == 422

    def test_empty_rows_and_bad_project_slug_are_422(self, advisor):
        assert push(advisor, []).status_code == 422
        assert push(advisor, [row()], project="Bad_Slug").status_code == 422

    def test_an_admin_user_may_push_without_a_token(self, advisor):
        assert push(advisor, [row()], scopes=None).status_code == 200


class TestListAndReview:
    def test_filter_by_project_and_status(self, advisor):
        push(advisor, [row()], project="limiar-app")
        push(advisor, [row(texto="Outro projeto.")], project="outro-app")
        assert len(advisor.get(URL, params={"project": "outro-app"}).json()["items"]) == 1
        assert advisor.get(URL, params={"status": "aceito"}).json()["items"] == []
        assert advisor.get(URL, params={"status": "bogus"}).status_code == 422

    def test_admin_marks_accepted_with_a_note_and_the_promote_tool_can_read_it(self, advisor):
        new = push(advisor, [row()]).json()["novos"][0]["id"]
        resp = advisor.patch(f"{URL}/{new}", json={"status": "aceito", "nota": "vale para o pacote"})
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert (out["status"], out["nota"], out["reviewed_by"]) == ("aceito", "vale para o pacote", str(DEFAULT_USER_ID))
        assert out["reviewed_at"] is not None
        with advisor.as_token("learnings:read"):
            accepted = advisor.get(URL, params={"status": "aceito"}).json()["items"]
        assert [i["id"] for i in accepted] == [new]

    def test_discard_and_the_content_never_changes(self, advisor):
        new = push(advisor, [row()]).json()["novos"][0]["id"]
        before = advisor.get(URL).json()["items"][0]
        out = advisor.patch(f"{URL}/{new}", json={"status": "descartado", "nota": "não se aplica ao pacote"}).json()
        assert out["status"] == "descartado"
        assert (out["texto"], out["data"], out["tipo"], out["row_sha"]) == (
            before["texto"], before["data"], before["tipo"], before["row_sha"])

    @pytest.mark.parametrize("body", [{"status": "novo", "nota": "ok ok"}, {"status": "promovido", "nota": "ok ok"}, {}, {"status": "aceito", "nota": "ok ok", "x": 1}])
    def test_review_status_is_aceito_or_descartado_only(self, advisor, body):
        new = push(advisor, [row()]).json()["novos"][0]["id"]
        assert advisor.patch(f"{URL}/{new}", json=body).status_code == 422

    @pytest.mark.parametrize("body", [{"status": "aceito"}, {"status": "aceito", "nota": ""}, {"status": "descartado", "nota": "   "}])
    def test_review_requires_a_note(self, advisor, body):
        # CONTRACT agent-packages §H2: the note is required server-side, not only in the UI.
        new = push(advisor, [row()]).json()["novos"][0]["id"]
        assert advisor.patch(f"{URL}/{new}", json=body).status_code == 422

    def test_unknown_learning_is_404(self, advisor):
        resp = advisor.patch(f"{URL}/{advisor.rt.user_id}", json={"status": "aceito", "nota": "revisado pelo dono"})
        assert resp.status_code == 404 and resp.json()["code"] == "learning_not_found"

    def test_a_learning_of_another_agent_is_404_not_403(self, pkg):
        pkg.advisor("mobile-dev")
        pkg.advisor("outro-advisor")
        new = push(pkg, [row()], url="/api/studio/agents/outro-advisor/learnings").json()["novos"][0]["id"]
        resp = pkg.patch(f"{URL}/{new}", json={"status": "aceito", "nota": "revisado pelo dono"})
        assert resp.status_code == 404
