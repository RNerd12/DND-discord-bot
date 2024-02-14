from datetime import datetime, timezone
from typing import Any, Union
import discord
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from google.cloud.firestore_v1.collection import CollectionReference


class FirebaseClient:
    def __init__(self, creds_path: str):
        self.cred = credentials.Certificate(creds_path)
        self.app = firebase_admin.initialize_app(self.cred)
        self.db = firestore.client()

    def get_collection(self, collection_name: str) -> CollectionReference:
        return self.db.collection(collection_name)

    def log_players(
        self,
        collection: CollectionReference,
        players: list[Union[discord.Member, discord.User]],
    ) -> int:
        count = 0
        for player in players:
            doc_ref = collection.document(str(player.id))
            if not doc_ref.get().exists:
                doc_ref.set(
                    {
                        "player_name": player.name,
                        "player_joined_date": player.joined_at.astimezone(timezone.utc),
                        "sessions_played": 0,
                        "latest_session": player.joined_at.astimezone(timezone.utc),
                        "sessions_dmed": 0,
                        "latest_session_dmed": player.joined_at.astimezone(
                            timezone.utc
                        ),
                    }
                )
                count += 1
        return count

    def log_session(
        self,
        collection: CollectionReference,
        players: list[discord.Member],
        gm: Union[discord.User, discord.Member],
        time: str,
    ):
        session_time = None
        if time == "now":
            session_time = datetime.now(timezone.utc)

        if not session_time:
            try:
                session_time = datetime.utcfromtimestamp(int(time)).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

        if not session_time:
            try:
                session_time = datetime.fromisoformat(time).replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        if not session_time:
            raise ValueError(f"Unable to parse time `{time}`.")

        players.append(gm)
        self.log_players(collection, players)
        doc_ref = collection.document(str(gm.id))
        doc_dict = doc_ref.get().to_dict()
        sessions_dmed = doc_dict["sessions_dmed"]
        latest_session_dmed = max(
            session_time.astimezone(timezone.utc),
            doc_dict["latest_session_dmed"].astimezone(timezone.utc),
        )
        doc_ref.update(
            {
                "sessions_dmed": sessions_dmed + 1,
                "latest_session_dmed": latest_session_dmed,
            }
        )
        for player in players:
            doc_ref = collection.document(str(player.id))
            doc_data = doc_ref.get().to_dict()
            sessions = doc_data["sessions_played"]
            latest_session_time = max(
                session_time.astimezone(timezone.utc),
                doc_data["latest_session"].astimezone(timezone.utc),
            )
            doc_ref.update(
                {"sessions_played": sessions + 1, "latest_session": latest_session_time}
            )

    def get_inactive_players(self, collection: CollectionReference, players: list):
        inactive_players = []
        cur_date = datetime.now(timezone.utc)
        for player in players:
            doc_ref = collection.document(str(player.id))
            activity = cur_date - doc_ref.get().to_dict()["latest_session"]
            if activity.days > 60:
                inactive_players.append(player)
        return inactive_players

    def get_inactive_gms(self, collection: CollectionReference, gms: list):
        inactive_gms = []
        cur_date = datetime.now(timezone.utc)
        for gm in gms:
            doc_ref = collection.document(str(gm.id))
            activity = cur_date - doc_ref.get().to_dict()["latest_session_dmed"]
            if activity.days > 60:
                inactive_gms.append(gm)
        return inactive_gms

    def set_preference(self, json_data: dict[str, Any], collection_name: str):
        collection_ref = self.db.collection(collection_name)
        for key, value in json_data.items():
            document_ref = collection_ref.document(key)
            document_ref.set(value)

    def get_preference(self, collection_name: str) -> dict[str, dict]:
        collection_ref = self.db.collection(collection_name)
        data = {}
        for doc in collection_ref.stream():
            data[doc.id] = doc.to_dict()
        return data
