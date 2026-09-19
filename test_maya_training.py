from pathlib import Path
from tempfile import TemporaryDirectory

from maya_training import (
    approve_training,
    approved_preferences,
    edit_training,
    reject_training,
    review_training,
    route_training_command,
    submit_training,
)


def run() -> None:
    with TemporaryDirectory() as directory:
        state = Path(directory) / "training.json"

        pending = submit_training(
            "When I ask a direct question, answer it first and avoid irrelevant background.",
            "preference",
            state,
        )
        assert pending["status"] == "pending_review"
        assert approved_preferences(state) == []
        assert len(review_training(state)) == 1

        duplicate = submit_training(
            "When I ask a direct question, answer it first and avoid irrelevant background.",
            "preference",
            state,
        )
        assert duplicate["duplicate"] is True
        assert len(review_training(state)) == 1

        edited = edit_training(
            pending["id"],
            "Answer the current question first; include context only when it helps.",
            state,
        )
        assert edited["status"] == "pending_review"
        approved = approve_training(pending["id"], state)
        assert approved["status"] == "approved"
        assert approved_preferences(state) == ["Answer the current question first; include context only when it helps."]
        assert review_training(state) == []

        rejected = submit_training("Do not make decisions for me or act without approval.", "preference", state)
        reject_training(rejected["id"], state)
        assert len(approved_preferences(state)) == 1

        route_state = Path(directory) / "route.json"
        response = route_training_command("training example: use approved signals and show uncertainty", route_state)
        assert response is not None
        assert "pending review" in response
        assert "approved memory" in response
        review = route_training_command("training review", route_state)
        assert review is not None and "train-" in review
        candidate_id = review.split("train-", 1)[1].split(":", 1)[0]
        candidate_id = "train-" + candidate_id
        approve_response = route_training_command(f"training approve {candidate_id}", route_state)
        assert approve_response is not None and "Approved training candidate" in approve_response

    print("maya_training_ok")


if __name__ == "__main__":
    run()
