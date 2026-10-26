import asyncio

from telegram_menu import MENU_COMMANDS, sync_command_menu


def test_menu_payload_and_rejection():
    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def json(self):
            return {"ok": self.status == 200}

    class Session:
        response = Response()

        def post(self, url, *, json, timeout):
            assert url.endswith("/setMyCommands")
            assert [item["command"] for item in json["commands"]] == [
                "news", "important", "digest", "tracks", "updates", "status", "help"
            ]
            assert json["commands"] == MENU_COMMANDS
            return self.response

    session = Session()
    assert asyncio.run(sync_command_menu(session))
    session.response.status = 400
    assert not asyncio.run(sync_command_menu(session))
