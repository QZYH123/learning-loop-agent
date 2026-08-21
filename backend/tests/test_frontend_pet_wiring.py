from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PET_JS = (ROOT / "frontend/js/pet.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
API_JS = (ROOT / "frontend/js/api.js").read_text(encoding="utf-8")
CSS = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_pet_api_wrappers_exist():
    assert "'/api/pet'" in API_JS
    assert "'/api/pet/pat'" in API_JS
    assert "getPet()" in API_JS
    assert "updatePet(patch)" in API_JS


def test_app_boots_pet_and_notifies_learning_events():
    assert "initPet()" in APP_JS
    for event in ["'chat'", "'attempt-completed'", "'exam-published'"]:
        assert f"petNotify({event})" in APP_JS
    # 答题反馈按对错分流
    assert "petNotify(feedback?.correct === true ? 'correct' : 'feedback')" in APP_JS


def test_pet_module_is_self_contained_and_fails_silently():
    # 后端不可用时静默隐藏，不影响应用启动
    assert "state.failed = true" in PET_JS
    # 交互面：摸摸、二维拖拽、名片、吸附收纳、改名
    for token in ["patPet", "position_x", "position_y", "pet-card", "hidden: true", "commitRename", "dockEdge"]:
        assert token in PET_JS


def test_pet_styles_respect_theme_motion_and_print():
    assert "--bubble-user" in CSS.split("桌宠")[1]  # 身体颜色随主题
    assert "is-reduced" in CSS  # prefers-reduced-motion
    assert "@media print { #pet-root { display: none; } }" in CSS
