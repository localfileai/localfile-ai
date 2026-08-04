"""승인 후 파일 변경(기능④) 테스트 — 실제 임시 폴더에서 파일을 만들어 검증한다.

안전장치가 본체인 모듈이라 테스트도 안전장치 중심이다:
경로 탈출, 충돌, 권한 에러 격리, dry_run 무변경, undo 역순 복원.
"""

import shutil

import pytest

from app.contracts.ai import ApplyItem, ApplyRequest
from app.fileops import apply as fileops


@pytest.fixture()
def history_dir(tmp_path, monkeypatch):
    """테스트마다 독립된 이력 폴더. 실제 apply_history를 오염시키지 않는다."""
    path = tmp_path / "history"
    monkeypatch.setattr(fileops, "HISTORY_DIR", path)
    return path


@pytest.fixture()
def root(tmp_path):
    folder = tmp_path / "정리대상"
    folder.mkdir()
    (folder / "os_lecture.pdf").write_text("강의자료", encoding="utf-8")
    (folder / "hw3.docx").write_text("과제", encoding="utf-8")
    return folder


def item(source, folder, name) -> ApplyItem:
    return ApplyItem(source_path=str(source), target_folder=folder, target_filename=name)


class TestApply:
    def test_이동과_개명이_실제로_일어난다(self, root, history_dir):
        result = fileops.apply_changes(str(root), [
            item(root / "os_lecture.pdf", "강의자료/운영체제", "운영체제_1주차_강의.pdf")])

        assert result.moved == 1 and result.failed == 0
        assert (root / "강의자료/운영체제/운영체제_1주차_강의.pdf").is_file()
        assert not (root / "os_lecture.pdf").exists()
        assert result.history_id  # 이력이 남았다

    def test_dry_run은_파일을_건드리지_않는다(self, root, history_dir):
        result = fileops.apply_changes(str(root), [
            item(root / "os_lecture.pdf", "강의자료", "강의.pdf")], dry_run=True)

        assert result.dry_run and result.items[0].status == "valid"
        assert (root / "os_lecture.pdf").exists()       # 원본 그대로
        assert not (root / "강의자료").exists()          # 폴더도 안 만든다
        assert result.history_id == ""                   # 이력도 없다

    def test_대상에_같은_이름이_있으면_건너뛴다(self, root, history_dir):
        target_dir = root / "과제"
        target_dir.mkdir()
        (target_dir / "hw3.docx").write_text("기존 파일", encoding="utf-8")

        result = fileops.apply_changes(str(root), [
            item(root / "hw3.docx", "과제", "hw3.docx")])

        assert result.items[0].status == "skipped"
        assert "conflict" in result.items[0].reason
        assert (target_dir / "hw3.docx").read_text(encoding="utf-8") == "기존 파일"
        assert (root / "hw3.docx").exists()  # 원본 유지

    def test_root_밖으로_나가는_경로는_실패한다(self, root, history_dir):
        # 계약 검증(FileSuggestion)과 별개로 실행 계층도 자체 방어해야 한다.
        outside = ApplyItem.model_construct(
            source_path=str(root / "hw3.docx"),
            target_folder="../탈출", target_filename="hw3.docx")
        result = fileops.apply_changes(str(root), [outside])

        assert result.items[0].status == "failed"
        assert "unsafe_path" in result.items[0].reason
        assert (root / "hw3.docx").exists()

    def test_원본이_root_밖이어도_실패한다(self, root, tmp_path, history_dir):
        stray = tmp_path / "밖의파일.pdf"
        stray.write_text("x", encoding="utf-8")
        result = fileops.apply_changes(str(root), [item(stray, "폴더", "밖의파일.pdf")])

        assert result.items[0].status == "failed"
        assert "unsafe_path" in result.items[0].reason

    def test_확장자를_바꾸는_개명은_거부한다(self, root, history_dir):
        result = fileops.apply_changes(str(root), [
            item(root / "hw3.docx", "과제", "hw3.pdf")])
        assert result.items[0].status == "failed"
        assert "extension_mismatch" in result.items[0].reason

    def test_권한_에러는_그_항목만_실패하고_나머지는_진행된다(self, root, history_dir,
                                                              monkeypatch):
        # 기획안 4주차 '파일 권한 에러 방지' — Windows에서 열려 있는 파일 상황 재현
        original_move = shutil.move

        def move_with_lock(src, dst):
            if "hw3" in src:
                raise PermissionError("파일이 다른 프로세스에서 사용 중입니다")
            return original_move(src, dst)

        monkeypatch.setattr(fileops.shutil, "move", move_with_lock)
        result = fileops.apply_changes(str(root), [
            item(root / "hw3.docx", "과제", "hw3.docx"),
            item(root / "os_lecture.pdf", "강의자료", "os_lecture.pdf")])

        assert result.failed == 1 and result.moved == 1
        by_status = {r.status for r in result.items}
        assert by_status == {"failed", "moved"}
        assert (root / "강의자료/os_lecture.pdf").is_file()

    def test_없는_원본은_실패한다(self, root, history_dir):
        result = fileops.apply_changes(str(root), [
            item(root / "ghost.pdf", "폴더", "ghost.pdf")])
        assert result.items[0].status == "failed"
        assert "source_missing" in result.items[0].reason

    def test_root가_없으면_ValueError(self, tmp_path, history_dir):
        with pytest.raises(ValueError):
            fileops.apply_changes(str(tmp_path / "없는폴더"), [
                item(tmp_path / "a.pdf", "b", "a.pdf")])


class TestUndo:
    def test_이동을_역순으로_되돌린다(self, root, history_dir):
        fileops.apply_changes(str(root), [
            item(root / "os_lecture.pdf", "강의자료", "운영체제_강의.pdf"),
            item(root / "hw3.docx", "과제", "운영체제_과제3.docx")])

        outcome = fileops.undo()

        assert outcome["restored"] == 2 and not outcome["skipped"]
        assert (root / "os_lecture.pdf").is_file()
        assert (root / "hw3.docx").is_file()
        assert not (root / "강의자료/운영체제_강의.pdf").exists()

    def test_원래_자리에_다른_파일이_생겼으면_건너뛴다(self, root, history_dir):
        fileops.apply_changes(str(root), [
            item(root / "hw3.docx", "과제", "과제3.docx")])
        (root / "hw3.docx").write_text("새로 생긴 다른 파일", encoding="utf-8")

        outcome = fileops.undo()

        assert outcome["restored"] == 0
        assert outcome["skipped"][0]["reason"] == "original_slot_occupied"
        assert (root / "과제/과제3.docx").is_file()  # 옮긴 파일은 그대로

    def test_같은_작업은_두_번_되돌릴_수_없다(self, root, history_dir):
        fileops.apply_changes(str(root), [
            item(root / "hw3.docx", "과제", "과제3.docx")])
        fileops.undo()
        with pytest.raises(ValueError):
            fileops.undo()

    def test_이력이_없으면_ValueError(self, history_dir):
        with pytest.raises(ValueError):
            fileops.undo()


class TestContract:
    def test_승인_없이는_요청_자체가_거부된다(self, root):
        with pytest.raises(Exception):
            ApplyRequest(approved=False, root=str(root), items=[
                item(root / "hw3.docx", "과제", "hw3.docx")])


class TestApi:
    """라우트 등록·상태 코드 확인. 파일 로직 자체는 위 유닛 테스트가 담당한다."""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient

        from app import create_app
        return TestClient(create_app())

    def test_apply_후_history와_undo까지_한_바퀴(self, client, root, history_dir):
        payload = {
            "approved": True, "root": str(root),
            "items": [{"source_path": str(root / "hw3.docx"),
                       "target_folder": "과제", "target_filename": "과제3.docx"}],
        }
        response = client.post("/apply", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["moved"] == 1 and body["history_id"]

        history = client.get("/apply/history").json()["history"]
        assert history[0]["id"] == body["history_id"]

        undone = client.post("/apply/undo").json()
        assert undone["restored"] == 1
        assert (root / "hw3.docx").is_file()

    def test_없는_root는_400(self, client, tmp_path, history_dir):
        response = client.post("/apply", json={
            "approved": True, "root": str(tmp_path / "없음"),
            "items": [{"source_path": "a.pdf", "target_folder": "b",
                       "target_filename": "a.pdf"}]})
        assert response.status_code == 400

    def test_승인_없는_요청은_422(self, client, root):
        response = client.post("/apply", json={
            "approved": False, "root": str(root),
            "items": [{"source_path": "a.pdf", "target_folder": "b",
                       "target_filename": "a.pdf"}]})
        assert response.status_code == 422
